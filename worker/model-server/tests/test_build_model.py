"""build-model.sh against a stage the feed key can still write (ADR 0026, T44).

The script checks every staged file, then unpacks the llama.cpp archive and
runs its server as root. The stage is the feed account's, so these tests run
the script as root in a user namespace on a stage of small dummy files, with a
sha256sum that swaps the staged archive for one whose server leaves a mark,
right after the check has read it. The script is stopped before the model
build, which needs systemd and an account.
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
BUILD = "b0"
ARCHIVE = f"llama/llama-{BUILD}-bin-ubuntu-arm64.tar.gz"


# CI sets this, so the tests that need a user namespace fail there instead of
# being skipped.
REQUIRED = os.environ.get("AISEC_REQUIRE_UNSHARE") == "1"


def unshare_works():
    if shutil.which("unshare") is None:
        return False
    done = subprocess.run(["unshare", "-r", "true"], capture_output=True, check=False)
    return done.returncode == 0


def server_archive(path, script):
    with tarfile.open(path, "w:gz") as tar:
        data = script.encode()
        info = tarfile.TarInfo(f"llama-{BUILD}/llama-server")
        info.size = len(data)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(data))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@unittest.skipUnless(
    unshare_works() or REQUIRED, "needs unprivileged user namespaces for root"
)
class BuildModel(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.scripts = self.tmp / "scripts"
        (self.scripts / "models").mkdir(parents=True)
        shutil.copy(HERE / "build-model.sh", self.scripts)
        self.opt = self.tmp / "opt"
        self.mark = self.tmp / "ran-the-swapped-server"
        self.stage = self.tmp / "stage"
        (self.stage / "llama").mkdir(parents=True)
        (self.stage / "m").mkdir()
        self.good = self.tmp / "good.tar.gz"
        server_archive(self.good, "#!/bin/sh\necho 'version: good'\n")
        self.evil = self.tmp / "evil.tar.gz"
        server_archive(self.evil, f"#!/bin/sh\ntouch {self.mark}\n")
        shutil.copy(self.good, self.stage / ARCHIVE)
        (self.stage / "m" / "config.json").write_text("{}\n")
        (self.stage / "converter-src.tar").write_bytes(b"src")
        (self.scripts / "artifacts.tsv").write_text(
            f"{sha256(self.good)}\t{ARCHIVE}\turl\n"
        )
        (self.scripts / "models" / "m.tsv").write_text(
            f"{sha256(self.stage / 'm' / 'config.json')}\tm/config.json\turl\n"
        )
        (self.scripts / "pins.env").write_text(
            f"LLAMA_BUILD={BUILD}\n"
            f"CONVERTER_SRC_SHA256={sha256(self.stage / 'converter-src.tar')}\n"
            "MODEL_NAME=m\nMODEL_QUANT=Q4_K_M\n"
            f"LLAMA_DIR={self.opt}/llama.cpp/llama-{BUILD}\n"
            f"MODEL_DIR={self.opt}/models\nMODEL_FILE={self.opt}/models/m.gguf\n"
        )
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        # libgomp is there, and the build stops where it would add an account.
        self.stub("ldconfig", "echo 'libgomp.so.1 (libc6) => /usr/lib/libgomp.so.1'")
        self.stub("dpkg-query", "echo 'libgomp1 0'")
        self.stub("useradd", "echo 'stopped before the build' >&2; exit 3")

    def stub(self, name, body):
        path = self.bin / name
        path.write_text(f"#!/bin/bash\n{body}\n")
        path.chmod(0o755)

    def swap_after_check(self):
        real = shutil.which("sha256sum")
        target = self.stage / ARCHIVE
        self.stub(
            "sha256sum",
            f'{real} "$@"; rc=$?\ncp -f {self.evil} {target}.new && mv -f {target}.new {target}\nexit $rc',
        )

    def run_build(self):
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "TMPDIR": str(self.tmp)}
        return subprocess.run(
            [
                "unshare",
                "-r",
                "bash",
                str(self.scripts / "build-model.sh"),
                str(self.stage),
            ],
            capture_output=True,
            env=env,
            timeout=60,
            check=False,
        )

    def test_the_checked_server_is_the_one_that_runs(self):
        done = self.run_build()
        self.assertIn(b"version: good", done.stdout, done.stderr.decode())
        self.assertIn(b"stopped before the build", done.stderr)

    def test_an_archive_swapped_after_the_check_does_not_run(self):
        self.swap_after_check()
        done = self.run_build()
        self.assertFalse(self.mark.exists(), "root ran a server nobody checked")
        self.assertIn(b"version: good", done.stdout, done.stderr.decode())

    def test_a_staged_link_is_refused_before_anything_runs(self):
        (self.stage / "m" / "config.json").unlink()
        os.symlink(self.tmp / "elsewhere", self.stage / "m" / "config.json")
        (self.tmp / "elsewhere").write_text("{}\n")
        done = self.run_build()
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn(b"== llama.cpp", done.stdout)

    def test_no_copy_of_the_stage_is_left_behind(self):
        self.run_build()
        self.assertEqual(
            sorted(p.name for p in self.tmp.glob("aisec-model-stage.*")), []
        )


if __name__ == "__main__":
    unittest.main()
