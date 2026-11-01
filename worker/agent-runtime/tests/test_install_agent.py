"""install-agent.sh against a stage the feed key can still write (ADR 0026, T44).

The feed account owns the stage, so whoever holds the feed key can replace a
staged file at any moment, also while root checks and unpacks it. These tests
run the script as root in a user namespace, with Goose's pins pointing at a
dummy archive, and a sha256sum that swaps the staged archive right after it
has read it, which is the race made certain.
"""

import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ARCHIVE = "goose-aarch64-unknown-linux-musl.tar.gz"


# CI sets this, so the tests that need a user namespace fail there instead of
# being skipped.
REQUIRED = os.environ.get("AISEC_REQUIRE_UNSHARE") == "1"


def unshare_works():
    if shutil.which("unshare") is None:
        return False
    done = subprocess.run(["unshare", "-r", "true"], capture_output=True, check=False)
    return done.returncode == 0


def archive(path, goose=None, link=None):
    """A tar.gz holding ./goose: a regular file with these bytes, or a link."""
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("./goose")
        if link is not None:
            info.type = tarfile.SYMTYPE
            info.linkname = link
            tar.addfile(info)
        else:
            info.size = len(goose)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(goose))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@unittest.skipUnless(
    unshare_works() or REQUIRED, "needs unprivileged user namespaces for root"
)
class InstallAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.scripts = self.tmp / "scripts"
        self.scripts.mkdir()
        shutil.copy(HERE / "install-agent.sh", self.scripts)
        fixture = self.scripts / "install-fixture.sh"
        fixture.write_text("#!/bin/bash\necho fixture\n")
        fixture.chmod(0o755)
        self.stage = self.tmp / "stage"
        (self.stage / "goose").mkdir(parents=True)
        self.goose_dir = self.tmp / "opt" / "goose-test"
        # A root-owned file outside every directory the script works in, whose
        # mode an archive with a ./goose link would change.
        self.victim = self.tmp / "victim"
        self.victim.write_text("secret\n")
        self.victim.chmod(0o600)
        self.good = self.tmp / "good.tar.gz"
        self.binary = b"#!/bin/sh\necho goose\n"
        archive(self.good, goose=self.binary)
        self.evil = self.tmp / "evil.tar.gz"
        archive(self.evil, link=str(self.victim))
        self.pin(self.good)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()

    def pin(self, path):
        (self.scripts / "artifacts.tsv").write_text(
            f"{sha256(path)}\tgoose/{ARCHIVE}\turl\n"
        )
        (self.scripts / "pins.env").write_text(
            f"GOOSE_ARCHIVE={ARCHIVE}\n"
            f"GOOSE_BINARY_SHA256={hashlib.sha256(self.binary).hexdigest()}\n"
            f"GOOSE_DIR={self.goose_dir}\n"
        )

    def stage_archive(self, source):
        shutil.copy(source, self.stage / "goose" / ARCHIVE)

    def swap_after_check(self):
        """A sha256sum that replaces the staged archive with the evil one once
        it has read it, as a feed key holder winning the race would."""
        real = shutil.which("sha256sum")
        stub = self.bin / "sha256sum"
        target = self.stage / "goose" / ARCHIVE
        stub.write_text(
            f'#!/bin/bash\n{real} "$@"; rc=$?\n'
            f"cp -f {self.evil} {target}.new && mv -f {target}.new {target}\nexit $rc\n"
        )
        stub.chmod(0o755)

    def run_install(self):
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "TMPDIR": str(self.tmp)}
        return subprocess.run(
            [
                "unshare",
                "-r",
                "bash",
                str(self.scripts / "install-agent.sh"),
                str(self.stage),
            ],
            capture_output=True,
            env=env,
            timeout=60,
            check=False,
        )

    def victim_untouched(self):
        self.assertEqual(self.victim.stat().st_mode & 0o777, 0o600)

    def test_a_good_archive_installs_goose(self):
        self.stage_archive(self.good)
        done = self.run_install()
        self.assertEqual(done.returncode, 0, done.stderr.decode())
        installed = self.goose_dir / "goose"
        self.assertFalse(installed.is_symlink())
        self.assertEqual(installed.read_bytes(), self.binary)
        self.assertEqual(installed.stat().st_mode & 0o777, 0o755)

    def test_an_archive_swapped_after_the_check_is_not_unpacked(self):
        self.stage_archive(self.good)
        self.swap_after_check()
        done = self.run_install()
        self.victim_untouched()
        installed = self.goose_dir / "goose"
        if installed.exists() or installed.is_symlink():
            self.assertFalse(installed.is_symlink())
            self.assertEqual(installed.read_bytes(), self.binary)
        self.assertEqual(done.returncode, 0, done.stderr.decode())

    def test_a_staged_link_instead_of_an_archive_is_refused(self):
        os.symlink(self.good, self.stage / "goose" / ARCHIVE)
        done = self.run_install()
        self.assertNotEqual(done.returncode, 0)
        self.assertFalse((self.goose_dir / "goose").exists())

    def test_a_pinned_archive_whose_goose_is_a_link_changes_nothing_outside(self):
        # Even an archive that matches its pin gets no root chown or chmod on
        # anything but a plain file it unpacked.
        self.pin(self.evil)
        self.stage_archive(self.evil)
        done = self.run_install()
        self.assertNotEqual(done.returncode, 0)
        self.victim_untouched()


if __name__ == "__main__":
    unittest.main()
