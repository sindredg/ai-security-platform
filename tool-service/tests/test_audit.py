"""The order of the audit lines. A copy with a hole in it has to show the hole."""

import json
import re
import subprocess
import sys
from pathlib import Path

from conftest import TOKEN_A

TWO_LINES = (
    "from aisec_tools.audit import audit; audit('a', 'allowed'); audit('b', 'refused')"
)


def fresh_process():
    root = Path(__file__).resolve().parent.parent
    run = [sys.executable, "-c", TWO_LINES]
    done = subprocess.run(run, cwd=root, capture_output=True, text=True, check=True)  # noqa: S603
    return [json.loads(line) for line in done.stdout.splitlines()]


def test_every_line_counts_up_by_one_within_one_start(two_jobs, lines):
    two_jobs.call(TOKEN_A)
    two_jobs.call(TOKEN_A, name="run_shell")
    two_jobs.call("not-a-token")
    written = lines()
    assert len(written) == 3
    assert len({line["start"] for line in written}) == 1
    assert re.fullmatch(r"[0-9a-f]{16}", written[0]["start"])
    numbers = [line["seq"] for line in written]
    assert numbers == list(range(numbers[0], numbers[0] + 3))


def test_a_new_process_counts_from_one_under_a_new_start():
    first, second = fresh_process(), fresh_process()
    assert [line["seq"] for line in first] == [1, 2]
    assert [line["seq"] for line in second] == [1, 2]
    assert first[0]["start"] == first[1]["start"]
    assert first[0]["start"] != second[0]["start"]
