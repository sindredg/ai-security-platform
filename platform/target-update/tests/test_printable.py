"""The update run's filter on what a target prints (threat model: a compromised
target is the expected state).

The target decides every byte of its session's output. The run copies it to the
operator's terminal and puts the target's two result lines in the journal, so
control and format characters are replaced first, as dispatch does for the
model's text (ADR 0030).
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "aisec-target-update-run"

# What a compromised target can print: a title change, a clipboard write
# (OSC 52), a carriage return that rewrites the line, a screen clear, the C1
# form of CSI, a right-to-left override, and a byte that is not UTF-8.
HOSTILE = (
    b"security_updates_pending=0 \x1b]0;t\x07\x1b]52;c;dGVzdA==\x07\r\n"
    b"reboot_required=no \x1b[2J\xc2\x9b31m\xe2\x80\xaeok\xff\n"
)
CONTROLS = re.compile(
    r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]"
)


def printable_function():
    """The filter exactly as the script defines it."""
    text = SCRIPT.read_text()
    match = re.search(r"^printable\(\) \{\n.*?^\}\n", text, re.DOTALL | re.MULTILINE)
    if not match:
        raise AssertionError("the script defines no printable() function")
    return match.group(0)


# CI sets this, so the tests that need a user namespace fail there instead of
# being skipped.
REQUIRED = os.environ.get("AISEC_REQUIRE_UNSHARE") == "1"


def unshare_works():
    if shutil.which("unshare") is None:
        return False
    return (
        subprocess.run(
            ["unshare", "-r", "true"], capture_output=True, check=False
        ).returncode
        == 0
    )


class Printable(unittest.TestCase):
    def run_filter(self, data):
        script = printable_function() + "printable\n"
        done = subprocess.run(
            ["bash", "-c", script], input=data, capture_output=True, check=True
        )
        return done.stdout.decode("utf-8")

    def test_control_and_format_characters_are_replaced(self):
        out = self.run_filter(HOSTILE)
        self.assertIsNone(CONTROLS.search(out), repr(out))
        self.assertNotIn("\x1b", out)
        self.assertIn(chr(0xFFFD), out)

    def test_text_newlines_and_tabs_are_kept(self):
        out = self.run_filter(
            b"Get:1 http://azure.archive.ubuntu.com resolute\tInRelease\n0 upgraded\n"
        )
        self.assertEqual(
            out,
            "Get:1 http://azure.archive.ubuntu.com resolute\tInRelease\n0 upgraded\n",
        )

    def test_a_line_without_an_end_is_passed_on(self):
        self.assertEqual(self.run_filter(b"no newline"), "no newline")


@unittest.skipUnless(
    unshare_works() or REQUIRED, "needs unprivileged user namespaces for the root check"
)
class TheRun(unittest.TestCase):
    """The whole run, as root in a user namespace, against a stub ssh that
    prints what a compromised target would, and a stub logger."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (self.tmp / "target-output").write_bytes(HOSTILE)
        (bin_dir / "ssh").write_text(
            f"#!/bin/bash\ncat {self.tmp}/target-output\nprintf '\\033[2Jstderr\\n' >&2\nexit 0\n"
        )
        (bin_dir / "logger").write_text(
            f'#!/bin/bash\nprintf "%s\\n" "$*" >> {self.tmp}/journal\n'
        )
        for name in ("ssh", "logger"):
            (bin_dir / name).chmod(0o755)
        self.env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "TMPDIR": str(self.tmp)}

    def test_nothing_the_target_printed_reaches_the_terminal_or_the_journal_raw(self):
        done = subprocess.run(
            ["unshare", "-r", "bash", str(SCRIPT), "lab"],
            capture_output=True,
            check=False,
            env=self.env,
            timeout=30,
        )
        out = done.stdout.decode("utf-8", "replace")
        err = done.stderr.decode("utf-8", "replace")
        journal = (self.tmp / "journal").read_bytes().decode("utf-8", "replace")
        self.assertEqual(done.returncode, 0, err)
        for name, text in (("stdout", out), ("stderr", err), ("journal", journal)):
            self.assertIsNone(CONTROLS.search(text), f"{name}: {text!r}")
        self.assertIn("end target=lab status=0 security_updates_pending=0", journal)


if __name__ == "__main__":
    unittest.main()
