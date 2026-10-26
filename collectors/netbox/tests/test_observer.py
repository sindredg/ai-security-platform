"""The observer key's forced command, and the root command behind it.

Each runs from a copy in which sudo, env, and python3 are stubs that print
what they were asked to run, so the test sees what each word leads to.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LIVE = "-n /usr/local/sbin/aisec-observe-netbox"
COPY_ENV = (
    "AISEC_NETBOX_URL=https://10.50.1.4:8443 "
    "AISEC_NETBOX_CERT=/etc/aisec/netbox-rehearsal/tls.crt "
    "AISEC_NETBOX_TOKENS=/etc/aisec/netbox-rehearsal/tokens"
)
OBSERVED = "-I /usr/local/lib/aisec/netbox_access.py observed"


class Observer(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for name in ("sudo", "env", "python3"):
            stub = self.tmp / name
            stub.write_text(f'#!/bin/sh\necho "{name} $*"\n')
            stub.chmod(0o755)
        for name in ("aisec-observe", "aisec-observe-netbox"):
            text = (HERE / name).read_text()
            for tool in ("sudo", "env", "python3"):
                text = text.replace(f"/usr/bin/{tool} ", f"{self.tmp}/{tool} ")
            (self.tmp / name).write_text(text)

    def run_script(self, name, *args, original=None):
        env = {"PATH": "/usr/bin:/bin"}
        if original is not None:
            env["SSH_ORIGINAL_COMMAND"] = original
        return subprocess.run(  # noqa: S603 - the copy of a script under test
            ["/bin/sh", str(self.tmp / name), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_the_observer_takes_rehearsal_and_nothing_else(self):
        for original, want in (
            (None, f"sudo {LIVE}"),
            ("", f"sudo {LIVE}"),
            ("id", f"sudo {LIVE}"),
            ("rehearsal", f"sudo {LIVE} rehearsal"),
            ("rehearsal id", f"sudo {LIVE}"),
            ("rehearsal\nid", f"sudo {LIVE}"),
            ("Rehearsal", f"sudo {LIVE}"),
        ):
            with self.subTest(original=original):
                done = self.run_script("aisec-observe", original=original)
                self.assertEqual((done.returncode, done.stdout.strip()), (0, want))

    def test_the_root_command_runs_one_half_for_each_word(self):
        done = self.run_script("aisec-observe-netbox")
        self.assertEqual(
            (done.returncode, done.stdout.strip()), (0, f"python3 {OBSERVED}")
        )
        done = self.run_script("aisec-observe-netbox", "rehearsal")
        self.assertEqual(
            (done.returncode, done.stdout.strip()),
            (0, f"env {COPY_ENV} {self.tmp}/python3 {OBSERVED}"),
        )
        for word in ("configured", "rehearsal extra", ""):
            with self.subTest(word=word):
                args = word.split(" ") if word else ["", "x"]
                done = self.run_script("aisec-observe-netbox", *args)
                self.assertEqual((done.returncode, done.stdout), (2, ""))


if __name__ == "__main__":
    unittest.main()
