"""The dispatch step (ADR 0012, ADR 0030).

Runs in a workflow pod in `orchestration`, as the dispatch account, from the
dispatch image. Two modes:

    dispatch.py dispatch JOB MAX_TURNS SECONDS TASK
    dispatch.py revoke JOB

dispatch makes a job token, registers the job with the tool service by the
token's digest, opens an SSH session to the worker's job account, writes one
job line, keeps the session's input open, and reads one result line. It checks
the result's size and fields, writes it to the step's output file, prints the
agent's transcript and answer to the step's log, and exits 0 only for a
completed job that called a tool, after which the model server's slot was
erased. A stop of the step closes the session's input, which the worker takes
as a cancel.

revoke ends the job at the tool service. The workflow's exit handler runs it
on success, failure, and stop.

The token exists in this process's memory, at the tool service as a digest,
and on the worker for the length of the job. It is never an argument, an
environment variable, or a file here. Standard library only.
"""

import hashlib
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
SSH = os.environ.get("AISEC_SSH", "/usr/bin/ssh")
WORKER = "aisec-job@10.40.0.36"

TARGET = "synthetic"
TOOLS = ["get_evidence"]
JOB_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
# The ranges the job program on the worker accepts. Checked here first, so a
# job the worker would refuse is never registered.
TURNS = range(1, 21)
SECONDS = range(60, 1201)
RESULT_BYTES = 65536
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
    "tool_calls": int,
    "tool_errors": int,
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


def register(job, seconds, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    body = {
        "job": job,
        "target": TARGET,
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
    return result


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


def dispatch(job, max_turns, seconds, task):
    token = secrets.token_hex(32)
    register(job, seconds, token)
    line = json.dumps(
        {
            "job": job,
            "token": token,
            "task": task,
            "max_turns": max_turns,
            "seconds": seconds,
        }
    ).encode()
    session = Session(private_key())

    def stopped(signum, frame):
        session.close()
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, stopped)
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


def main(argv):
    try:
        if len(argv) == 6 and argv[1] == "dispatch":
            _, _, job, max_turns, seconds, task = argv
            if not JOB_ID.fullmatch(job):
                raise Failed("not a job ID")
            if not (max_turns.isdigit() and int(max_turns) in TURNS):
                raise Failed("max turns out of range")
            if not (seconds.isdigit() and int(seconds) in SECONDS):
                raise Failed("seconds out of range")
            dispatch(job, int(max_turns), int(seconds), task)
        elif len(argv) == 3 and argv[1] == "revoke":
            status, text = tool_service("DELETE", REGISTER_URL + "/" + argv[2])
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
