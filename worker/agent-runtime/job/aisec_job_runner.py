#!/usr/bin/python3 -I
"""The forced command of the dispatch key on the worker (ADR 0030).

sshd runs this as aisec-job instead of whatever the client asked for. It is
installed as /usr/local/sbin/aisec-job-runner. It
accepts an empty request or "run", reads one job line from standard input,
hands it to the job socket, and relays: the socket's answer to standard
output, and the end of standard input to the socket. The dispatch step keeps
its standard input open while the job runs, so an end of input means the
session is gone: a cancel. The job's unit stops the agent when it sees it.

The account has no other rights. systemd starts the job's sandboxed unit for
each connection to the socket, one at a time. Standard library only.
"""

import os
import select
import socket
import sys

SOCKET = "/run/aisec-job/agent.sock"
JOB_BYTES = 16384
RESULT_BYTES = 65536


def refuse(reason, code):
    print("refused: " + reason, file=sys.stderr)
    return code


def write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def read_job(fd):
    """One line, at most JOB_BYTES. Nothing may follow it before the result."""
    data = b""
    while b"\n" not in data:
        chunk = os.read(fd, 4096)
        if not chunk:
            return None, "input ended before the job line did"
        data += chunk
        if len(data) > JOB_BYTES + 1:
            return None, "job line too long"
    line, _, extra = data.partition(b"\n")
    if len(line) > JOB_BYTES:
        return None, "job line too long"
    if extra:
        return None, "input after the job line"
    return line + b"\n", None


def relay(conn, fd_in, fd_out):
    """Relay until the job closes the socket. Returns the bytes relayed out."""
    open_in, sent = True, 0
    while True:
        watch = [conn] + ([fd_in] if open_in else [])
        ready, _, _ = select.select(watch, [], [])
        if open_in and fd_in in ready and not os.read(fd_in, 4096):
            open_in = False
            conn.shutdown(socket.SHUT_WR)
        if conn in ready:
            data = conn.recv(65536)
            if not data:
                return sent
            sent += len(data)
            if sent > RESULT_BYTES:
                raise OverflowError("result too large")
            write_all(fd_out, data)


def main(path=SOCKET):
    request = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    if request not in ("", "run"):
        return refuse("not a job request", 2)
    line, reason = read_job(0)
    if line is None:
        return refuse(reason, 2)
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.connect(path)
    except OSError as error:
        return refuse(f"no job socket: {error.strerror}", 3)
    with conn:
        conn.sendall(line)
        try:
            sent = relay(conn, 0, 1)
        except OverflowError as error:
            return refuse(str(error), 4)
        except BrokenPipeError:
            # The session closed while the result was on its way.
            return 0
    if sent == 0:
        return refuse("the job ended without a result, or another job is running", 5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
