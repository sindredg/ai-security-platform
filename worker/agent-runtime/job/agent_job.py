"""One agent job, inside its own sandboxed unit (ADR 0030).

systemd starts this once per connection to the job socket, with the connection
as standard input and output. The job runner on the other end relays an SSH
session from the dispatch step on the orchestrator.

Reads one JSON line, the job. Writes the agent's recipe with the job's token
into the unit's private /tmp, runs Goose against the model server and the tool
service, and writes one JSON line back, the result. An end of input before
Goose ends is a cancel: Goose is stopped, and nothing is written back. Either
way the model server's slot is erased afterwards, so the next job does not
start from this one's prompt (#32). Standard library only.

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
ANSWER_CHARS = 8000
STDERR_CHARS = 2000
TURNS = range(1, 21)
SECONDS = range(60, 1201)
JOB_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
TOKEN = re.compile(r"[0-9a-f]{64}")
FIELDS = {"job", "token", "task", "max_turns", "seconds"}

TOOL_URL = "https://tool-service.aisec.internal:30443/mcp"
TOOL_CERT = "/etc/aisec/tool-service.crt"
# The unit sets nothing here. The tests point it at a stub.
MODEL_URL = os.environ.get("AISEC_MODEL_URL", "http://127.0.0.1:8080")


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
    if not isinstance(job, dict) or set(job) != FIELDS:
        raise Refused("job line has the wrong fields")
    if not isinstance(job["job"], str) or not JOB_ID.fullmatch(job["job"]):
        raise Refused("job ID is not valid")
    if not isinstance(job["token"], str) or not TOKEN.fullmatch(job["token"]):
        raise Refused("token is not valid")
    if not isinstance(job["task"], str) or not 0 < len(job["task"]) <= TASK_CHARS:
        raise Refused("task is empty or too long")
    for field, allowed in (("max_turns", TURNS), ("seconds", SECONDS)):
        value = job[field]
        if type(value) is not int or value not in allowed:
            raise Refused(f"{field} is out of range")
    return job


def write_recipe(job, system, path):
    """The agent's recipe: the system text, the task, and one extension."""
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
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(recipe, f)


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


def summarize(transcript):
    """Counts and the last answer from Goose's JSON output."""
    calls, errors, answer = 0, 0, ""
    for message in transcript.get("messages", []):
        texts = []
        for part in message.get("content", []):
            kind = part.get("type")
            if kind == "toolRequest":
                calls += 1
            elif kind == "toolResponse":
                result = part.get("toolResult") or {}
                value = result.get("value") or {}
                if result.get("status") != "success" or value.get("isError"):
                    errors += 1
            elif kind == "text":
                texts.append(part.get("text") or "")
        if message.get("role") == "assistant":
            answer = "\n".join(texts)
    return calls, errors, answer


def erase_slot():
    """Empty the model server's one slot. Returns whether it answered 200."""
    request = urllib.request.Request(  # noqa: S310 - a fixed http URL
        MODEL_URL + "/slots/0?action=erase", data=b"", method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - the same
            return response.status == 200
    except OSError:
        return False


def result_line(job, outcome, code, started, out, err):
    token = job["token"]
    calls, errors, answer, agent_status, tokens = 0, 0, "", None, {}
    try:
        transcript = json.loads(Path(out).read_text())
        calls, errors, answer = summarize(transcript)
        metadata = transcript.get("metadata") or {}
        agent_status = metadata.get("status")
        tokens = {k: metadata.get(k) for k in ("input_tokens", "output_tokens")}
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    stderr = Path(err).read_text(errors="replace")[-STDERR_CHARS:]
    completed = outcome == "ended" and code == 0 and agent_status == "completed"
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
        "answer": answer[:ANSWER_CHARS].replace(token, "[token]"),
        "stderr_tail": stderr.replace(token, "[token]"),
        **tokens,
    }
    return json.dumps(result) + "\n"


def main():
    started = time.monotonic()
    goose = os.environ["AISEC_GOOSE"]
    system = Path(os.environ["AISEC_SYSTEM"]).read_text()
    work = Path(os.environ.get("AISEC_WORK", "/tmp/job"))  # noqa: S108 - the unit's private /tmp
    try:
        line, _ = read_line(0, JOB_BYTES)
        job = parse_job(line)
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
    erased = erase_slot()
    print(
        json.dumps({"job": job["job"], "outcome": outcome, "slot_erased": erased}),
        file=sys.stderr,
    )
    if outcome == "cancelled":
        return 0
    write_all(1, result_line(job, outcome, code, started, out, err).encode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
