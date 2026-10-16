"""Pulls the worker's journal into an append-only file on the orchestrator.

ADR 0019. A timer runs this every five minutes as `aisec-journal-pull`. It asks
the worker over SSH for the entries after the last cursor it kept. The key can
run nothing on the worker but the export, which accepts a cursor and nothing
else.

The worker is the machine the design assumes is compromised, so its answer is
hostile input on the trusted machine. One pull reads at most 16 MiB and lines
of at most 64 KiB. A line is copied as it is only when it is one JSON object
with a cursor in the journal's format. Anything else becomes a marker line.
The file stops at 2 GiB.

Standard error from the worker is not read. A worker could fill it until both
sides wait, and its text would land in this machine's journal. The exit status
says enough: 255 is SSH itself, 2 is the export refusing.

The same few lines that append and save state are in aisec_audit_copy.py. Each
runs with `python3 -I`, which keeps its own folder off the import path, so they
are not shared.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

WORKER = "aisec-logexport@10.40.0.36"
HOME = Path("/var/lib/aisec-journal-pull")
KNOWN_HOSTS = Path("/etc/aisec/journal-pull-known-hosts")
OUT = Path("/var/log/aisec/worker-journal.jsonl")
CAP = 2 * 1024**3
PULL_MAX = 16 * 1024**2
LINE_MAX = 64 * 1024
TIMEOUT = 120
FULL = 3
CURSOR = re.compile(
    r"s=[0-9a-f]{32};i=[0-9a-f]{1,16};b=[0-9a-f]{32};"
    r"m=[0-9a-f]{1,16};t=[0-9a-f]{1,16};x=[0-9a-f]{1,16}"
)


class Failed(Exception):
    """The pull failed. Nothing was appended, and the next pull tries again."""


class Full(Exception):
    """The file reached its cap. The puller stops and stays stopped."""


def ssh(cursor):
    return [
        "ssh", "-T", "-i", str(HOME / "id_ed25519"), "-o", "IdentitiesOnly=yes",
        "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "GlobalKnownHostsFile=none",
        "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
        WORKER, cursor,
    ]  # fmt: skip


def marker(reason, size):
    line = {"event": "copy", "decision": "refused", "reason": reason, "bytes": size}
    return json.dumps(line, separators=(",", ":")).encode()


def keep(raw):
    """One line from the worker to (its cursor or None, the line to append)."""
    if len(raw) > LINE_MAX:
        return None, marker("line too long", len(raw))
    try:
        entry = json.loads(raw)
    except (ValueError, RecursionError):
        return None, marker("not a JSON object", len(raw))
    if not isinstance(entry, dict):
        return None, marker("not a JSON object", len(raw))
    cursor = entry.get("__CURSOR")
    if not isinstance(cursor, str) or not CURSOR.fullmatch(cursor):
        return None, marker("no cursor in the journal's format", len(raw))
    return cursor, raw


def read(source):
    """Whole lines, up to PULL_MAX bytes in all, and whether it stopped there.

    A line longer than LINE_MAX keeps its first part, which keep() turns into
    a marker, and the rest is skipped. A line cut by the limit, or a last line
    with no end, is dropped. A worker that stops sending blocks this read: the
    unit's start timeout is what ends it.
    """
    lines, total = [], 0
    while total < PULL_MAX:
        raw = source.readline(min(LINE_MAX + 1, PULL_MAX - total))
        total += len(raw)
        if raw.endswith(b"\n"):
            lines.append(raw[:-1])
        elif total >= PULL_MAX:
            return lines, True
        elif len(raw) > LINE_MAX:
            lines.append(raw)
            while total < PULL_MAX and (rest := source.readline(LINE_MAX + 1)):
                total += len(rest)
                if rest.endswith(b"\n"):
                    break
        else:
            return lines, False
    return lines, True


def append(lines):
    data = b"".join(line + b"\n" for line in lines)
    try:
        out = os.open(OUT, os.O_WRONLY | os.O_APPEND)
    except OSError as error:
        raise Failed(f"cannot open {OUT}: {error}") from error
    try:
        if os.fstat(out).st_size + len(data) > CAP:
            os.write(out, marker("the file reached its cap", len(data)) + b"\n")
            raise Full(f"{OUT} reached {CAP} bytes")
        os.write(out, data)
        os.fsync(out)
    finally:
        os.close(out)


def save(name, text):
    temporary = HOME / f".{name}"
    temporary.write_text(text)
    os.replace(temporary, HOME / name)


def one_pull():
    position = HOME / "cursor"
    cursor = position.read_text().strip() if position.exists() else ""
    if cursor and not CURSOR.fullmatch(cursor):
        raise Failed("the saved cursor is not in the journal's format")
    with subprocess.Popen(  # noqa: S603 - a fixed command, and a checked cursor
        ssh(cursor), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    ) as worker:
        lines, cut = read(worker.stdout)
        if cut:
            worker.kill()
        try:
            status = worker.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired as error:
            worker.kill()
            raise Failed("ssh did not end") from error
        if not cut and status != 0:
            raise Failed(f"ssh ended with {status}. 255 is SSH itself, 2 a refusal")
    kept = [keep(line) for line in lines]
    if kept:
        append([line for _, line in kept])
    cursors = [found for found, _ in kept if found]
    if cursors:
        save("cursor", cursors[-1] + "\n")
    save("ok", f"{time.time():.0f}\n")
    return len(kept), cut


def main():
    try:
        count, cut = one_pull()
    except Full as error:
        print(error, file=sys.stderr)
        return FULL
    except Failed as error:
        print(f"pull failed: {error}", file=sys.stderr)
        return 1
    print(f"copied {count} lines" + (", stopped at the limit" if cut else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
