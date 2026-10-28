"""The dispatch step (ADR 0012, ADR 0030).

Runs in a workflow pod in `orchestration`, as the dispatch account, from the
dispatch image. Two modes:

    dispatch.py dispatch JOB TARGET MAX_TURNS SECONDS TASK
    dispatch.py revoke JOB

dispatch makes a job token, registers the job for its target with the tool
service by the token's digest, opens an SSH session to the worker's job account, writes one
job line, keeps the session's input open, and reads one result line. It checks
the result's size and fields, writes it to the step's output file, prints the
agent's transcript and answer to the step's log, and exits 0 only for a
completed job that called a tool, after which the model server's slot was
erased, and whose answer the comparison step can take: at most 8 KiB, with no
template syntax and no character Argo could not pass on. That answer goes to
an output file of its own. A job that did not complete may give no call
counts, since the worker cannot know them without the agent's transcript. A
stop of the step closes the session's input, which the worker takes as a
cancel.

revoke ends the job at the tool service. The workflow's exit handler runs it
on success, failure, and stop.

The token exists in this process's memory, at the tool service as a digest,
and on the worker for the length of the job. It is never an argument, an
environment variable, or a file here. Standard library only.
"""

import hashlib
import importlib.util
import json
import os
import re
import secrets
import select
import signal
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def load_compare():
    """The comparison step's reader of the checks' verdicts, from the file
    beside this one in the image. Loaded by path, since Python's isolated
    mode, which the tests run this file in, leaves its directory off the
    import path."""
    path = Path(__file__).with_name("compare.py")
    spec = importlib.util.spec_from_file_location("compare", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = load_compare()

# Fixed for the pod. The tests point them at stubs.
REGISTER_URL = os.environ.get(
    "AISEC_REGISTER_URL", "https://tool-service.tool-services.svc:8444/jobs"
)
CALLER_TOKEN = os.environ.get("AISEC_CALLER_TOKEN", "/var/run/secrets/aisec/token")
TOOL_CERT = os.environ.get("AISEC_TOOL_CERT", "/etc/aisec/tls.crt")
KEY = os.environ.get("AISEC_DISPATCH_KEY", "/etc/dispatch/id_ed25519")
KNOWN_HOSTS = os.environ.get("AISEC_KNOWN_HOSTS", "/etc/dispatch/known_hosts")
WORK = Path(os.environ.get("AISEC_WORK", "/run/dispatch"))
RESULT = Path(os.environ.get("AISEC_RESULT", "/tmp/result.json"))  # noqa: S108 - the pod's own emptyDir
ANSWER = Path(os.environ.get("AISEC_ANSWER", "/tmp/answer.txt"))  # noqa: S108 - the pod's own emptyDir
SSH = os.environ.get("AISEC_SSH", "/usr/bin/ssh")
WORKER = "aisec-job@10.40.0.36"

# The targets the tool service's policy lists. It refuses any other too.
TARGETS = ("synthetic", "netbox")
# The targets whose jobs answer in a schema that names the job's accounts
# (ADR 0051). The step reads the names from the checks' verdicts for the job,
# the file the comparison step reads, so the model is asked for the accounts
# the comparison checks and no others.
ANSWER_TARGETS = ("netbox",)
TOOLS = ["get_evidence"]
JOB_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
# The ranges the job program on the worker accepts. Checked here first, so a
# job the worker would refuse is never registered.
TURNS = range(1, 21)
SECONDS = range(60, 1201)
RESULT_BYTES = 65536
# The comparison step gets the answer as a workflow parameter (ADR 0041). Argo
# moves a pod's arguments, or its template, over 128 KiB into a config map,
# which its controller may not create here, and escapes <, >, and & six times
# over. The answer is in both, so it stays far below.
ANSWER_BYTES = 8192
# The token lives this much longer than the job, and the step waits this much
# longer for the result. The workflow's deadline sits between the two.
TOKEN_MARGIN = 300
WAIT_MARGIN = 120

RESULT_FIELDS = {
    "job": str,
    "status": str,
    "exit_code": (int, type(None)),
    "seconds": (int, float),
    "agent_status": (str, type(None)),
    # None when the job did not complete: Goose writes its transcript when it
    # ends, so a stopped job's calls are unknown on the worker (#200).
    "tool_calls": (int, type(None)),
    "tool_errors": (int, type(None)),
    "slot_erased": bool,
    "answer": str,
    "stderr_tail": str,
}
OPTIONAL_FIELDS = {
    "input_tokens": (int, type(None)),
    "output_tokens": (int, type(None)),
    "transcript": list,
}
# Each part of the transcript: who wrote it, its kind, and its text.
PART_FIELDS = {"role", "type", "text"}


class Failed(Exception):
    pass


def tool_service(method, url, body=None):
    """One registration call, as the dispatch account. Returns (status, body)."""
    caller = Path(CALLER_TOKEN).read_text().strip()
    context = (
        ssl.create_default_context(cafile=TOOL_CERT)
        if url.startswith("https:")
        else None
    )
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": "Bearer " + caller, "Content-Type": "application/json"}
    request = urllib.request.Request(url, data, headers, method=method)  # noqa: S310 - a fixed URL
    try:
        with urllib.request.urlopen(request, context=context, timeout=15) as response:  # noqa: S310 - the same
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def register(job, target, seconds, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    body = {
        "job": job,
        "target": target,
        "tools": TOOLS,
        "seconds": seconds + TOKEN_MARGIN,
        "token_sha256": digest,
    }
    status, text = tool_service("POST", REGISTER_URL, body)
    if status != 201:
        raise Failed(f"registration refused: {status} {text}")


def private_key():
    """ssh refuses a key that others can read. The secret's file is root's, so
    the key is copied into the pod's memory-backed directory, mode 600."""
    WORK.mkdir(mode=0o700, exist_ok=True)
    copy = WORK / "id_ed25519"
    copy.unlink(missing_ok=True)
    fd = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(Path(KEY).read_bytes())
    return copy


def check_result(line, job):
    try:
        result = json.loads(line)
    except ValueError as error:
        raise Failed("the result is not JSON") from error
    if not isinstance(result, dict):
        raise Failed("the result is not an object")
    if result.get("status") == "refused":
        raise Failed(f"the worker refused the job: {result.get('reason')!r}")
    extra = set(result) - set(RESULT_FIELDS) - set(OPTIONAL_FIELDS)
    if extra:
        raise Failed(f"the result has fields it should not: {sorted(extra)}")
    for field, kind in {**RESULT_FIELDS, **OPTIONAL_FIELDS}.items():
        if field not in result:
            if field in RESULT_FIELDS:
                raise Failed(f"the result has no {field}")
            continue
        value = result[field]
        if kind is bool:
            right = type(value) is bool
        else:
            right = not isinstance(value, bool) and isinstance(value, kind)
        if not right:
            raise Failed(f"the result's {field} has the wrong type")
    for part in result.get("transcript", []):
        if not isinstance(part, dict) or set(part) != PART_FIELDS:
            raise Failed("a transcript part has the wrong fields")
        if not all(isinstance(value, str) for value in part.values()):
            raise Failed("a transcript part has a value that is not text")
    if result["job"] != job:
        raise Failed("the result names another job")
    if result["status"] not in ("completed", "failed", "timeout"):
        raise Failed("the result's status is not one the worker gives")
    if result["status"] == "completed" and None in (
        result["tool_calls"],
        result["tool_errors"],
    ):
        raise Failed("a completed job's result has no call counts")
    return result


def unquotable(c):
    """Whether the step refuses the character in an answer it hands on. Argo
    quotes a parameter with Go's strconv.Quote and then requires valid JSON
    (util/template/simple_template.go and replace.go, read in v4.1.6). Go
    writes a control character other than \\b, \\t, \\n, \\f, and \\r, and
    DEL, as \\a, \\v, or \\xHH, and a character above U+FFFF that it does not
    print as \\U and eight digits, none of which JSON has. The step group
    would end on Argo's error instead of the comparison's. Which characters
    above U+FFFF Go prints depends on its Unicode tables, 15.0 in the Go that
    builds Argo v4.1.6, and Python's are newer, so every one is refused. An
    answer is plain text. A lone surrogate cannot be written to a file."""
    code = ord(c)
    if code < 0x20:
        return c not in "\b\t\n\f\r"
    return code == 0x7F or 0xD800 <= code <= 0xDFFF or code > 0xFFFF


def printable(text):
    """The worker's text for a terminal. Control and format characters become
    U+FFFD, so text the model shaped cannot send escape sequences to the
    operator's terminal through `argo logs`. Newlines and tabs stay."""
    return "".join(c if c.isprintable() or c in "\n\t" else "\ufffd" for c in text)


class Session:
    """The SSH session to the worker's job account."""

    def __init__(self, key):
        command = [
            SSH, "-i", str(key), "-T",
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes",
            "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=4",
            WORKER, "run",
        ]  # fmt: skip
        self.process = subprocess.Popen(  # noqa: S603 - a fixed command
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )

    def send(self, line):
        self.process.stdin.write(line)
        self.process.stdin.flush()

    def read_line(self, deadline):
        """One line from the worker, or Failed. Input stays open meanwhile."""
        fd, data = self.process.stdout.fileno(), b""
        while b"\n" not in data:
            left = deadline - time.monotonic()
            if left <= 0:
                raise Failed("no result before the deadline")
            ready, _, _ = select.select([fd], [], [], min(left, 1.0))
            if not ready:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                raise Failed("the session ended without a result")
            data += chunk
            if len(data) > RESULT_BYTES:
                raise Failed("the result is too large")
        return data.partition(b"\n")[0]

    def close(self, wait=15):
        """End the session's input, which is the cancel if the job still runs."""
        if self.process.stdin and not self.process.stdin.closed:
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self.process.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def accounts_for(job, target):
    """The names of the accounts a job answers for, sorted, from the checks'
    verdicts for the job, or None for a target without a schema. A NetBox job
    with no verdicts fails here, before it runs, with the stop the comparison
    step would give after it (#221)."""
    if target not in ANSWER_TARGETS:
        return None
    try:
        return sorted(compare.load_checks(compare.VERDICTS, job))
    except compare.Stop as stop:
        raise Failed(str(stop)) from None


def job_line(job, target, max_turns, seconds, task, token, accounts=None):
    """The line the worker reads. The target tells it how the answer ends
    (#215), and the accounts which names the answer's schema requires
    (#221). The names alone go: the checks' verdicts stay here."""
    line = {
        "job": job,
        "token": token,
        "task": task,
        "max_turns": max_turns,
        "seconds": seconds,
        "target": target,
    }
    if accounts is not None:
        line["accounts"] = accounts
    return json.dumps(line).encode()


def revoke(job):
    """Ends the job at the tool service. A job it does not hold is 200 too."""
    return tool_service("DELETE", REGISTER_URL + "/" + job)


def dispatch(job, target, max_turns, seconds, task):
    accounts = accounts_for(job, target)
    token = secrets.token_hex(32)
    session = None
    registered = False

    # A stop closes the session, which cancels the job on the worker, and
    # revokes the token itself: argo terminate skips the exit handler that
    # would (#174). The handler's second revoke is 200 at the service.
    def stopped(signum, frame):
        if session is not None:
            session.close()
        revoked = None
        if registered:
            try:
                revoked, _ = revoke(job)
            except (Failed, OSError) as error:
                print(f"revoke on stop failed: {error}", file=sys.stderr)
        print(json.dumps({"job": job, "stopped": signum, "revoked": revoked}))
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, stopped)
    register(job, target, seconds, token)
    registered = True
    line = job_line(job, target, max_turns, seconds, task, token, accounts)
    session = Session(private_key())
    try:
        session.send(line + b"\n")
        result = check_result(
            session.read_line(time.monotonic() + seconds + WAIT_MARGIN), job
        )
    finally:
        session.close()
    RESULT.write_text(json.dumps(result))
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("answer", "transcript")}
        )
    )
    for part in result.get("transcript", []):
        print(f"-- {printable(part['role'])} {printable(part['type'])}")
        print(printable(part["text"]))
    print("-- answer")
    print(printable(result["answer"]))
    # The next job erases the slot first and is refused if that fails too. The
    # operator hears of a slot left full here, from the job that left it.
    if not result["slot_erased"]:
        raise Failed("the model server's slot was not erased after the job")
    if result["status"] != "completed":
        raise Failed(f"the job ended {result['status']}")
    if result["tool_calls"] < 1:
        raise Failed("the agent called no tool")
    # Argo renders the parameter: it reads {{ as its own template syntax, and
    # {{= as an expression its controller evaluates.
    # First, since a lone surrogate would stop the encoding below.
    if any(unquotable(c) for c in result["answer"]):
        raise Failed("the answer has a character the step does not hand on")
    size = len(result["answer"].encode())
    if size > ANSWER_BYTES:
        raise Failed(
            f"the answer is {size} bytes, and the comparison reads at most "
            f"{ANSWER_BYTES}"
        )
    if "{{" in result["answer"]:
        raise Failed("the answer has template syntax, which Argo would read")
    ANSWER.write_text(result["answer"])


def main(argv):
    try:
        if len(argv) == 7 and argv[1] == "dispatch":
            _, _, job, target, max_turns, seconds, task = argv
            if not JOB_ID.fullmatch(job):
                raise Failed("not a job ID")
            if target not in TARGETS:
                raise Failed("not a target")
            if not (max_turns.isdigit() and int(max_turns) in TURNS):
                raise Failed("max turns out of range")
            if not (seconds.isdigit() and int(seconds) in SECONDS):
                raise Failed("seconds out of range")
            dispatch(job, target, int(max_turns), int(seconds), task)
        elif len(argv) == 3 and argv[1] == "revoke":
            status, text = revoke(argv[2])
            print(status, text)
            if status != 200:
                raise Failed("revoke refused")
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except Failed as error:
        print(f"failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
