"""Copies the tool service's audit lines into an append-only file on the host.

ADR 0019. The kubelet deletes a pod's log with the pod, so this runs every two
seconds, and the deploy runs one pass before the old pod goes. It runs as
`aisec-audit-copy`, reads the pod logs through a default ACL, and appends to a
root-owned file with the append-only attribute. It cannot rewrite what it wrote.

The lines come from a service that reads what a compromised worker sends. A
line that is not one JSON object on standard output is not copied. A marker
line takes its place, so nothing disappears without a trace.

A pass fails, and the health file is not touched, when no log file of the
service is found, when a file cannot be read, or when a timestamp from the
runtime does not parse. Each means the layout changed, and silence would look
like a quiet day.
"""

import argparse
import datetime
import glob
import gzip
import json
import os
import sys
import time
from pathlib import Path

PODS = "/var/log/pods/tool-services_tool-service-*/tool-service/*.log*"
OUT = Path("/var/log/aisec/tool-audit.jsonl")
STATE = Path("/var/lib/aisec-audit-copy")
CAP = 2 * 1024**3
INTERVAL = 2
FULL = 3


class Failed(Exception):
    """The pass failed. Nothing was appended, and the next pass tries again."""


class Full(Exception):
    """The file reached its cap. The copier stops and stays stopped."""


def nanoseconds(stamp):
    """The runtime's RFC 3339 time as an int. Go drops trailing zeros, and the
    whole fraction when it is zero."""
    whole, dot, fraction = stamp.removesuffix("Z").partition(".")
    digits = fraction.isdigit() and len(fraction) <= 9
    if not stamp.endswith("Z") or (dot and not digits):
        raise Failed(f"unexpected timestamp {stamp[:40]!r}")
    try:
        moment = datetime.datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S")
    except ValueError as error:
        raise Failed(f"unexpected timestamp {stamp[:40]!r}") from error
    seconds = int(moment.replace(tzinfo=datetime.UTC).timestamp())
    return seconds * 10**9 + int(fraction.ljust(9, "0") or 0)


def marker(reason, stamp, size):
    line = {"event": "copy", "decision": "refused", "reason": reason}
    line |= {"runtime_ts": stamp, "bytes": size}
    return json.dumps(line, separators=(",", ":")).encode()


def parse(raw):
    """One runtime line to (time, line to append)."""
    parts = raw.split(b" ", 3)
    if len(parts) != 4:
        raise Failed("a line without the runtime's prefix")
    stamp, stream, tag, content = (parts[0].decode("ascii", "replace"), *parts[1:])
    when = nanoseconds(stamp)
    if stream != b"stdout" or tag != b"F":
        return when, marker("not a whole line on standard output", stamp, len(content))
    try:
        if isinstance(json.loads(content), dict):
            return when, content
    except (ValueError, RecursionError):
        pass
    return when, marker("not a JSON object", stamp, len(content))


def read(path):
    opener = gzip.open if path.endswith(".gz") else open
    try:
        with opener(path, "rb") as source:
            return source.read().splitlines()
    except (OSError, EOFError) as error:
        raise Failed(f"cannot read {path}: {error}") from error


def collect(after):
    """Lines newer than `after`, oldest first, each once."""
    files = glob.glob(PODS)
    if not files:
        raise Failed("no log file of the tool service")
    found = set()
    for path in files:
        try:
            if os.stat(path).st_mtime_ns <= after:
                continue
        except OSError as error:
            raise Failed(f"cannot stat {path}: {error}") from error
        found |= {line for line in map(parse, read(path)) if line[0] > after}
    return sorted(found)


def append(lines):
    data = b"".join(line + b"\n" for line in lines)
    try:
        out = os.open(OUT, os.O_WRONLY | os.O_APPEND)
    except OSError as error:
        raise Failed(f"cannot open {OUT}: {error}") from error
    try:
        if os.fstat(out).st_size + len(data) > CAP:
            os.write(out, marker("the file reached its cap", "", len(data)) + b"\n")
            raise Full(f"{OUT} reached {CAP} bytes")
        os.write(out, data)
        os.fsync(out)
    finally:
        os.close(out)


def save(name, text):
    temporary = STATE / f".{name}"
    temporary.write_text(text)
    os.replace(temporary, STATE / name)


def one_pass():
    position = STATE / "position"
    try:
        after = int(position.read_text()) if position.exists() else 0
    except ValueError as error:
        raise Failed(f"unreadable position: {error}") from error
    found = collect(after)
    if found:
        append([line for _, line in found])
        save("position", str(found[-1][0]))
    save("ok", f"{time.time():.0f}\n")
    return len(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="one pass, then exit")
    once = parser.parse_args().once
    last_error = None
    while True:
        try:
            copied = one_pass()
            last_error = None
            if once:
                print(f"copied {copied} lines")
                return 0
        except Full as error:
            print(error, file=sys.stderr)
            return FULL
        except Failed as error:
            # The same failure every two seconds would flood the journal.
            if str(error) != last_error:
                print(f"pass failed: {error}", file=sys.stderr)
            last_error = str(error)
            if once:
                return 1
        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
