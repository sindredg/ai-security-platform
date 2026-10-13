"""The size check has to be able to fail."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "count_lines.py"
SOURCE = '''"""A docstring
over two lines."""

# a comment
import os


def f():
    """Another docstring."""
    return os.sep  # counted once
'''


def run(tmp_path, limit):
    path = tmp_path / "sample.py"
    path.write_text(SOURCE)
    command = [sys.executable, "-B", str(SCRIPT), str(limit), str(path)]
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


def test_code_lines_are_counted_and_nothing_else(tmp_path):
    done = run(tmp_path, 3)
    assert done.returncode == 0
    assert "    3  total, limit 3" in done.stdout


def test_one_line_over_the_limit_fails(tmp_path):
    done = run(tmp_path, 2)
    assert done.returncode != 0
    assert "1 lines over the limit" in done.stderr


def test_no_files_is_a_failure_not_a_pass(tmp_path):
    command = [sys.executable, "-B", str(SCRIPT), "300"]
    done = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    assert done.returncode != 0
