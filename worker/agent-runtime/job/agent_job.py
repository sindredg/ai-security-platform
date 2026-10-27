"""One agent job, inside its own sandboxed unit (ADR 0030).

systemd starts this once per connection to the job socket, with the connection
as standard input and output. The job runner on the other end relays an SSH
session from the dispatch step on the orchestrator.

Reads one JSON line, the job. Writes the agent's recipe with the job's token
into the unit's private /tmp, runs Goose against the model server and the tool
service, and writes one JSON line back, the result, with the agent's
transcript in it. A NetBox job's answer is written from the final output
Goose checked against the answer's schema (ADR 0049). The transcript goes
only to the socket, never to the journal, which leaves the worker for the
workspace. An end of input before
Goose ends is a cancel: Goose is stopped, and nothing is written back.

The model server's slot is erased before the job, and the job is refused when
that fails: the erase after the last job may have failed, or never run because
its unit was stopped first (#157). It is erased again afterwards, whatever the
outcome, so the next job does not start from this one's prompt (#32). The
result says whether that second erase worked. Standard library only.

The tool service's address and certificate are fixed here, not taken from the
job line. The token goes in the recipe, never on a command line.
"""

import json
import os
import re
import select
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

JOB_BYTES = 16384
TASK_CHARS = 8000
# The result line, newline included, stays within the job runner's and the
# dispatch step's RESULT_BYTES. The text fields are cut by the size of their
# JSON form, which escapes each character outside ASCII to 6 or 12 bytes. The
# transcript gets what the rest of the line leaves.
RESULT_BYTES = 65536
ANSWER_BYTES = 16384
STDERR_BYTES = 4096
PART_BYTES = 8192
CUT_MARK_BYTES = 128
TURNS = range(1, 21)
SECONDS = range(60, 1201)
JOB_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
TOKEN = re.compile(r"[0-9a-f]{64}")
FIELDS = {"job", "token", "task", "max_turns", "seconds"}
# The job's target, which the dispatch step names since #215. A line from a
# dispatch image before it has none. The tool service's targets.
OPTIONAL = {"target"}
TARGETS = ("synthetic", "netbox")
# Goose renders the recipe file as a MiniJinja template before it parses
# it, so template syntax in the task would run, and its output could replace
# the recipe. It also runs a first message that starts with "!" as a shell
# command, and one that starts with "/" as a slash command, after white space.
# Python's strip removes every character Rust's does, and a few more. Read in
# Goose 1.55.0's source. In 1.56.0 the recipe code is the same, and the
# session code changed only to report status to a terminal.
TEMPLATE = re.compile(r"\{[{%#]")
COMMAND_PREFIXES = ("!", "/")

TOOL_URL = "https://tool-service.aisec.internal:30443/mcp"
TOOL_CERT = "/etc/aisec/tool-service.crt"
# The unit sets nothing here. The tests point it at a stub.
MODEL_URL = os.environ.get("AISEC_MODEL_URL", "http://127.0.0.1:8080")
# The server takes a cancel, and then the erase, only between prompt batches
# of up to 2048 tokens. On 2026-10-20 a batch of 1004 took 57.5 seconds. The
# dispatch step waits 120 seconds past the job's limit, so a timed-out job's
# result still arrives. After a longer batch the outcome line says false,
# whatever the server does with the erase later.
ERASE_SECONDS = 90
# Goose logs each request it sends the model, its tool list included, under
# $GOOSE_PATH_ROOT/state/logs, and keeps the last ten. The recipe names one
# extension. Goose adds its own load_skill to every request, and no setting
# takes it away (#139). Read in Goose 1.56.0's source:
# crates/goose/src/providers/utils.rs for the log, and
# crates/goose/src/agents/state_machine_builder.rs for load_skill. A job
# offered any other tool fails.
OFFERED = frozenset({"tools__get_evidence", "load_skill"})
# A NetBox job answers with a structured final output (ADR 0049). A recipe
# with a response schema makes Goose offer the model a tool of its own for
# the answer, check each call to it against the schema, hand the errors back,
# and ask for the call when a turn ends without one. The tool reaches nothing.
# Read in Goose 1.56.0's source: crates/goose/src/agents/final_output_tool.rs
# and crates/goose/src/agents/state_machine/ops_recipe.rs. The job program
# checks the accepted output against the same schema, and writes from it the
# verdict and proposal lines the comparison reads (ADR 0041, ADR 0043).
FINAL_OUTPUT = "recipe__final_output"
FINAL_OUTPUT_ACCEPTED = "Final output successfully collected."
# The answer the comparison reads is at most 8 KiB (dispatch.py). The lines
# after the analysis take far less.
ANALYSIS_CHARS = 2000
ACCOUNT_NAME = {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]{0,63}$"}
REFERENCES = {
    "type": "array",
    "minItems": 1,
    "maxItems": 8,
    "items": {"type": "string", "pattern": "^ev-[0-9]{4}$"},
}
VERDICTS = {
    "type": "object",
    "additionalProperties": False,
    "required": ["analysis", "verdicts", "proposals"],
    "properties": {
        "analysis": {
            "type": "string",
            "minLength": 1,
            "maxLength": ANALYSIS_CHARS,
            "description": "What the evidence shows for each account, citing "
            "it, and where it disagrees",
        },
        "verdicts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "description": "One for each account in the contract",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["account", "verdict", "evidence"],
                "properties": {
                    "account": ACCOUNT_NAME,
                    "verdict": {
                        "enum": ["excess", "missing", "within", "inconclusive"]
                    },
                    "evidence": REFERENCES,
                },
            },
        },
        "proposals": {
            "type": "array",
            "maxItems": 20,
            "description": "One for each account whose verdict is excess",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["account", "permission", "evidence"],
                "properties": {
                    "account": ACCOUNT_NAME,
                    "permission": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 999999999,
                        "description": "The id in ev-0002 of the permission to "
                        "take from the account",
                    },
                    "evidence": REFERENCES,
                },
            },
        },
    },
}
# The targets whose jobs answer in a schema, and the schema.
ANSWER_SCHEMAS = {"netbox": VERDICTS}


class Refused(Exception):
    pass


def write_all(fd, data):
    """os.write may write part of the data to a socket. Write all of it."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def read_line(fd, limit):
    """Read up to the first newline. Returns (line, extra bytes after it)."""
    data = b""
    while b"\n" not in data:
        chunk = os.read(fd, 4096)
        if not chunk:
            raise Refused("input ended before the job line did")
        data += chunk
        if len(data) > limit:
            raise Refused("job line too long")
    line, _, extra = data.partition(b"\n")
    if len(line) > limit:
        raise Refused("job line too long")
    return line, extra


def parse_job(line):
    """Check the job line. Returns the job, or raises Refused."""
    try:
        job = json.loads(line)
    except ValueError as error:
        raise Refused("job line is not JSON") from error
    if not isinstance(job, dict) or not FIELDS <= set(job) <= FIELDS | OPTIONAL:
        raise Refused("job line has the wrong fields")
    if "target" in job and job["target"] not in TARGETS:
        raise Refused("target is not known")
    if not isinstance(job["job"], str) or not JOB_ID.fullmatch(job["job"]):
        raise Refused("job ID is not valid")
    if not isinstance(job["token"], str) or not TOKEN.fullmatch(job["token"]):
        raise Refused("token is not valid")
    if not isinstance(job["task"], str) or not 0 < len(job["task"]) <= TASK_CHARS:
        raise Refused("task is empty or too long")
    if TEMPLATE.search(job["task"]):
        raise Refused("task has template syntax")
    if job["task"].lstrip().startswith(COMMAND_PREFIXES):
        raise Refused("task starts with a Goose command character")
    for field, allowed in (("max_turns", TURNS), ("seconds", SECONDS)):
        value = job[field]
        if type(value) is not int or value not in allowed:
            raise Refused(f"{field} is out of range")
    return job


def write_recipe(job, system, path):
    """The agent's recipe: the system text, the task, one extension, and for
    a target that answers in a schema, the schema."""
    recipe = {
        "version": "1.0.0",
        "title": "aisec job",
        "description": "One investigation, dispatched by the platform",
        "instructions": system,
        "prompt": job["task"],
        "extensions": [
            {
                "type": "streamable_http",
                "name": "tools",
                "description": "The platform's tool service",
                "uri": TOOL_URL,
                "headers": {"Authorization": "Bearer " + job["token"]},
                "timeout": 60,
            }
        ],
    }
    schema = ANSWER_SCHEMAS.get(job.get("target"))
    if schema:
        recipe["response"] = {"json_schema": schema}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        # Indented, so that no two braces meet: Goose renders the file as a
        # template, in which {{ and }} are its own.
        json.dump(recipe, f, indent=1)


def goose_env(work):
    """Goose's environment: nothing from the unit but what is set here."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(work),
        "XDG_CONFIG_HOME": str(work / "config"),
        "GOOSE_PATH_ROOT": str(work / "goose"),
        "GOOSE_DISABLE_KEYRING": "1",
        "GOOSE_TELEMETRY_ENABLED": "false",
        "GOOSE_DISABLE_SESSION_NAMING": "true",
        "GOOSE_MODE": "auto",
        "GOOSE_PROVIDER": "openai",
        "GOOSE_MODEL": "local",
        "GOOSE_CONTEXT_LIMIT": "8192",
        "OPENAI_HOST": MODEL_URL,
        "OPENAI_API_KEY": "none",
        # Replaces the system's trust store: the agent trusts the tool
        # service's pinned certificate and nothing else.
        "SSL_CERT_FILE": TOOL_CERT,
    }


def stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run_goose(command, env, deadline, fd_in, out, err):
    """Run Goose while watching the connection.

    Returns ("ended", exit code), ("timeout", None), or ("cancelled", None).
    Input after the job line is read and dropped. Only its end means a cancel.
    """
    with open(out, "wb") as stdout, open(err, "wb") as stderr:
        process = subprocess.Popen(  # noqa: S603 - a fixed command, checked integers
            command,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env=env,
            cwd=env["HOME"],
        )
    try:
        while True:
            if process.poll() is not None:
                return "ended", process.returncode
            if time.monotonic() >= deadline:
                stop(process)
                return "timeout", None
            ready, _, _ = select.select([fd_in], [], [], 0.5)
            if ready and not os.read(fd_in, 4096):
                stop(process)
                return "cancelled", None
    finally:
        stop(process)


def offered_tools(work):
    """The names of the tools Goose offered the model, over every request it
    logged. None when it logged none, or a log cannot be read. An empty log
    is a request still in Goose's buffer when Goose was stopped."""
    names, read = set(), False
    for path in (work / "goose" / "state" / "logs").glob("llm_request.*.jsonl"):
        try:
            with path.open() as f:
                line = f.readline()
            if not line:
                continue
            tools = json.loads(line)["input"].get("tools") or []
            names.update(str(tool["function"]["name"]) for tool in tools)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        read = True
    return names if read else None


def allowed_tools(job):
    """The tools a job may be offered: the final output's too, for a target
    that answers in a schema."""
    if job.get("target") in ANSWER_SCHEMAS:
        return OFFERED | {FINAL_OUTPUT}
    return OFFERED


def tools_problem(offered, allowed=OFFERED):
    """Why the tools Goose offered fail the job, or None."""
    if offered is None:
        return "no request to the model could be read, so the offered tools are unknown"
    extra = sorted(offered - allowed)
    if extra:
        return "the model was offered tools outside the recipe: " + ", ".join(extra)
    return None


def tool_name(part):
    return ((part.get("toolCall") or {}).get("value") or {}).get("name")


def summarize(transcript):
    """Counts and the last answer from Goose's JSON output. The counts leave
    out the final output's calls, which reach no service: they count the
    calls to the tool service and its errors."""
    calls, errors, answer, finals = 0, 0, "", set()
    for message in transcript.get("messages", []):
        texts = []
        for part in message.get("content", []):
            kind = part.get("type")
            if kind == "toolRequest":
                if tool_name(part) != FINAL_OUTPUT:
                    calls += 1
                elif part.get("id") is not None:
                    finals.add(part["id"])
            elif kind == "toolResponse":
                if part.get("id") in finals:
                    continue
                result = part.get("toolResult") or {}
                value = result.get("value") or {}
                if result.get("status") != "success" or value.get("isError"):
                    errors += 1
            elif kind == "text":
                texts.append(part.get("text") or "")
        if message.get("role") == "assistant":
            answer = "\n".join(texts)
    return calls, errors, answer


def accepted_output(transcript):
    """The arguments of the last final output Goose accepted, found as Goose
    finds them: the call whose response says it was collected. None when no
    call was accepted. Also the number of final output calls."""
    accepted, calls = set(), []
    for message in transcript.get("messages", []):
        for part in message.get("content", []):
            if part.get("type") == "toolRequest" and tool_name(part) == FINAL_OUTPUT:
                calls.append(
                    (part.get("id"), part["toolCall"]["value"].get("arguments"))
                )
            elif part.get("type") == "toolResponse":
                result = part.get("toolResult") or {}
                value = result.get("value") or {}
                texts = [
                    c.get("text")
                    for c in value.get("content") or []
                    if isinstance(c, dict)
                ]
                if (
                    result.get("status") == "success"
                    and value.get("isError") is not True
                    and FINAL_OUTPUT_ACCEPTED in texts
                ):
                    accepted.add(part.get("id"))
    for call_id, arguments in reversed(calls):
        if call_id is not None and call_id in accepted:
            return arguments, len(calls)
    return None, len(calls)


def fits(value, schema):
    """Whether value fits schema, for the keywords VERDICTS uses. Goose
    checked it first. This keeps the lines written from it to what the schema
    allows, whatever Goose's checker passed."""
    if "enum" in schema and value not in schema["enum"]:
        return False
    kind = schema.get("type")
    if kind == "object":
        properties = schema.get("properties", {})
        return (
            isinstance(value, dict)
            and (
                schema.get("additionalProperties", True)
                or set(value) <= set(properties)
            )
            and set(schema.get("required", [])) <= set(value)
            and all(fits(value[k], properties[k]) for k in value if k in properties)
        )
    if kind == "array":
        return (
            isinstance(value, list)
            and schema.get("minItems", 0)
            <= len(value)
            <= schema.get("maxItems", len(value))
            and all(fits(item, schema["items"]) for item in value)
        )
    if kind == "string":
        # The schema's patterns are anchored with ^ and $, which Goose's
        # checker reads as the whole text. Python's $ also matches before a
        # last newline, so fullmatch takes the pattern without them.
        pattern = schema.get("pattern")
        return (
            isinstance(value, str)
            and schema.get("minLength", 0)
            <= len(value)
            <= schema.get("maxLength", len(value))
            and (pattern is None or re.fullmatch(pattern[1:-1], value) is not None)
        )
    if kind == "integer":
        return type(value) is int and schema.get(
            "minimum", value
        ) <= value <= schema.get("maximum", value)
    return kind is None


def answer_lines(final):
    """The answer the comparison reads, from a final output that fits the
    schema: the analysis as one line, then a verdict line for each account
    and a proposal line for each proposal, in the model's order. The analysis
    line starts with a word the comparison does not read."""
    analysis = " ".join(final["analysis"].split())
    lines = [f"Analysis: {analysis}", ""]
    lines += [
        f"Verdict: {v['account']} {v['verdict']} {' '.join(v['evidence'])}"
        for v in final["verdicts"]
    ]
    lines += [
        f"Proposal: {p['account']} remove {p['permission']} {' '.join(p['evidence'])}"
        for p in final["proposals"]
    ]
    return "\n".join(lines) + "\n"


def cut(text, size):
    """The longest start of text whose JSON form takes at most size bytes."""
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(json.dumps(text[:middle])) <= size:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def tool_result_text(result):
    """The text a tool returned, or the error Goose recorded."""
    if result.get("status") != "success":
        return str(result.get("error") or json.dumps(result))
    value = result.get("value")
    content = value.get("content") if isinstance(value, dict) else value
    if isinstance(content, list) and all(isinstance(c, dict) for c in content):
        return "\n".join(str(c.get("text") or json.dumps(c)) for c in content)
    return json.dumps(value)


def flatten(transcript, system):
    """Each part of each message as role, type, and text, the recipe's
    instructions first. A part of a type not known here keeps its JSON."""
    parts = [{"role": "system", "type": "instructions", "text": system}]
    for message in transcript.get("messages", []):
        role = str(message.get("role"))
        for part in message.get("content", []):
            kind = str(part.get("type"))
            if kind == "text":
                text = str(part.get("text") or "")
            elif kind == "toolRequest":
                value = (part.get("toolCall") or {}).get("value") or {}
                text = json.dumps(
                    {"name": value.get("name"), "arguments": value.get("arguments")}
                )
            elif kind == "toolResponse":
                text = tool_result_text(part.get("toolResult") or {})
            else:
                text = json.dumps(part)
            parts.append({"role": role, "type": kind, "text": text})
    return parts


def fit(parts, token, room):
    """The parts, token taken out and each cut to PART_BYTES, in order, until
    their JSON list would pass room bytes. A last part says how many were left
    out."""
    kept, used = [], len("[]")
    for index, part in enumerate(parts):
        text = cut(part["text"].replace(token, "[token]"), PART_BYTES)
        size = len(json.dumps({**part, "text": text})) + len(", ")
        if used + size > room - CUT_MARK_BYTES:
            left = len(parts) - index
            kept.append(
                {"role": "platform", "type": "cut", "text": f"{left} parts left out"}
            )
            break
        kept.append({**part, "text": text})
        used += size
    return kept


def erase_slot():
    """Empty the model server's one slot. Returns whether it answered 200."""
    request = urllib.request.Request(  # noqa: S310 - a fixed http URL
        MODEL_URL + "/slots/0?action=erase", data=b"", method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=ERASE_SECONDS) as response:  # noqa: S310 - the same
            return response.status == 200
    except OSError:
        return False


def log_erase(job, step, erased):
    """One line to the journal, where G.10 reads the last slot_erased."""
    print(
        json.dumps({"job": job["job"], **step, "slot_erased": erased}), file=sys.stderr
    )


def result_line(job, system, outcome, code, started, out, err, erased, offered):
    """The token is taken out of each text before it is cut, so no part of it
    is left at a cut. A job Goose completed fails when it was offered a tool
    its target does not allow, or when its answer had to be cut to fit the
    result, with each reason at the end of the stderr tail. For a target that
    answers in a schema, the answer is written from the final output Goose
    accepted, when it fits the schema. Otherwise it is the model's last text,
    as for any other job, and the stderr tail says so."""
    token = job["token"]
    # Goose writes its transcript when it ends. Without one, as after a
    # timeout, its calls are unknown here, and the result says so with no
    # count (#200). The tool service's audit log holds them.
    calls, errors, answer, agent_status, tokens = None, None, "", None, {}
    final, final_calls = None, 0
    transcript, parts = {}, flatten({}, system)
    try:
        transcript = json.loads(Path(out).read_text())
        calls, errors, answer = summarize(transcript)
        metadata = transcript.get("metadata") or {}
        agent_status = metadata.get("status")
        tokens = {k: metadata.get(k) for k in ("input_tokens", "output_tokens")}
        final, final_calls = accepted_output(transcript)
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    try:
        parts = flatten(transcript, system)
    except (AttributeError, TypeError):
        pass
    stderr = Path(err).read_text(errors="replace").replace(token, "[token]")
    schema = ANSWER_SCHEMAS.get(job.get("target"))
    if schema and final is not None and fits(final, schema):
        answer = answer_lines(final)
        stderr += f"\nthe answer is the final output, after {final_calls} calls"
    elif schema:
        stderr += (
            f"\nno final output fits the answer's schema, of {final_calls} calls:"
            " the answer is the model's last text"
        )
    completed = outcome == "ended" and code == 0 and agent_status == "completed"
    problem = tools_problem(offered, allowed_tools(job))
    if completed and problem:
        completed = False
        stderr += "\n" + problem
    # A cut answer can lose its last lines, the verdicts the comparison reads.
    answer = answer.replace(token, "[token]")
    kept = cut(answer, ANSWER_BYTES)
    if completed and kept != answer:
        completed = False
        stderr += "\nthe answer was longer than a result carries, and was cut"
    result = {
        "job": job["job"],
        "status": "completed"
        if completed
        else ("timeout" if outcome == "timeout" else "failed"),
        "exit_code": code,
        "seconds": round(time.monotonic() - started, 1),
        "agent_status": agent_status,
        "tool_calls": calls,
        "tool_errors": errors,
        "slot_erased": erased,
        "answer": kept,
        "stderr_tail": cut(stderr[::-1], STDERR_BYTES)[::-1],
        **tokens,
    }
    room = RESULT_BYTES - len(json.dumps(result)) - len(', "transcript": \n')
    result["transcript"] = fit(parts, token, room)
    return json.dumps(result) + "\n"


def main():
    started = time.monotonic()
    goose = os.environ["AISEC_GOOSE"]
    system = Path(os.environ["AISEC_SYSTEM"]).read_text()
    work = Path(os.environ.get("AISEC_WORK", "/tmp/job"))  # noqa: S108 - the unit's private /tmp
    try:
        line, _ = read_line(0, JOB_BYTES)
        job = parse_job(line)
        erased = erase_slot()
        log_erase(job, {"erase": "before"}, erased)
        if not erased:
            raise Refused("the model server's slot could not be erased")
    except Refused as reason:
        write_all(
            1,
            (json.dumps({"status": "refused", "reason": str(reason)}) + "\n").encode(),
        )
        return 2

    work.mkdir(mode=0o700)
    for name in ("config", "goose"):
        (work / name).mkdir(mode=0o700)
    recipe = work / "recipe.json"
    write_recipe(job, system, recipe)
    command = [
        goose, "run", "--recipe", str(recipe), "--no-session", "--quiet",
        "--output-format", "json", "--max-turns", str(job["max_turns"]),
    ]  # fmt: skip
    out, err = work / "out.json", work / "err.txt"
    outcome, code = run_goose(
        command, goose_env(work), started + job["seconds"], 0, out, err
    )
    recipe.unlink()
    offered = offered_tools(work)
    print(
        json.dumps(
            {"job": job["job"], "offered": None if offered is None else sorted(offered)}
        ),
        file=sys.stderr,
    )
    erased = erase_slot()
    log_erase(job, {"outcome": outcome}, erased)
    if outcome == "cancelled":
        return 0
    write_all(
        1,
        result_line(
            job, system, outcome, code, started, out, err, erased, offered
        ).encode(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
