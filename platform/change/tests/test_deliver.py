"""Delivery of an approved NetBox change (ADR 0046).

A temporary targets repository stands in for GitHub, with two SSH keys made
for the test: the approval key, and another. NetBox is a fake at the client's
level, and the checks after delivery are replaced. git and ssh-keygen are the
real ones.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "collectors" / "netbox"))
sys.path.insert(0, str(HERE))

import deliver
import netbox_change

SEED = {
    "objects": [
        {
            "path": "/api/users/permissions/",
            "key": "name",
            "items": [
                {"name": "reader: tenant-a", "users": ["reader"]},
                {"name": "reader: all", "users": ["reader"]},
                {"name": "control: tenant-a", "users": ["control"]},
            ],
        }
    ],
    "tokens": [],
}
CONTRACT = {"accounts": ["reader", "control"], "grants": [], "reads": [], "denials": []}
TOKEN = "nbt_" + "A" * 12 + "." + "b" * 40
WITHIN = {
    "reader": {"configured": "within", "observed": "within"},
    "control": {"configured": "within", "observed": "within"},
}


def run(*args, cwd, env=None):
    done = subprocess.run(  # noqa: S603 - git and ssh-keygen, the test's arguments
        args, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"{args}: {done.stderr}")
    return done.stdout.strip()


class FakeLive:
    """The live NetBox: assignments by permission name, and every PATCH."""

    def __init__(self, ledger):
        self.ledger = ledger
        self.users = {1: "reader", 2: "control", 3: "other"}
        self.permissions = {
            11: {"name": "reader: tenant-a", "users": [1]},
            12: {"name": "reader: all", "users": [1]},
            13: {"name": "control: tenant-a", "users": [2]},
        }
        self.patches = []
        self.ledger_at_patch = []

    def list(self, path, **query):
        if path == "/api/users/permissions/":
            return 200, [
                {
                    "id": i,
                    "name": p["name"],
                    "users": [{"id": u, "username": self.users[u]} for u in p["users"]],
                }
                for i, p in self.permissions.items()
                if p["name"] == query["name"]
            ]
        return 200, [
            {"id": i, "username": n}
            for i, n in self.users.items()
            if n == query["username"]
        ]

    def call(self, method, path, body=None):
        self.ledger_at_patch.append(
            self.ledger.read_text() if self.ledger.exists() else ""
        )
        self.patches.append((method, path, body))
        permission_id = int(path.rstrip("/").rsplit("/", 1)[1])
        self.permissions[permission_id]["users"] = list(body["users"])
        return 200, {}


class Deliver(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for key in ("approver", "other"):
            run(
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                key,
                "-f",
                key,
                cwd=self.tmp,
            )
        approvers = self.tmp / "approvers"
        approvers.write_text(
            f'aisec-approver namespaces="git" {(self.tmp / "approver.pub").read_text()}'
        )
        self.remote = self.tmp / "targets"
        (self.remote / "netbox").mkdir(parents=True)
        run("git", "init", "-q", "-b", "main", cwd=self.remote)
        self.write_seed(SEED)
        (self.remote / "netbox" / "contract.json").write_text(json.dumps(CONTRACT))
        self.main = self.commit("the seed")
        self.state = self.tmp / "delivery"
        self.live = FakeLive(self.state / "used")
        self.checked = []

        def fake_halves(contract):
            self.checked.append(contract)
            return self.verdicts

        self.verdicts = WITHIN
        self.tokens = []
        for patch in (
            mock.patch.object(deliver, "STATE", self.state),
            mock.patch.object(deliver, "APPROVERS", approvers),
            mock.patch.object(deliver, "REMOTE", str(self.remote)),
            mock.patch.object(deliver, "PROXY", ""),
            mock.patch.object(netbox_change, "client_for", self.client_for),
            mock.patch.object(deliver, "halves", fake_halves),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def client_for(self, url, cert, token):
        self.tokens.append(token)
        return self.live

    def git_env(self, when=None):
        env = {
            "PATH": os.environ["PATH"],
            "HOME": str(self.tmp),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        if when is not None:
            env["GIT_COMMITTER_DATE"] = f"{int(when)} +0000"
        return env

    def write_seed(self, seed):
        (self.remote / "netbox" / "seed.json").write_text(
            json.dumps(seed, indent=2) + "\n"
        )

    def commit(self, message):
        run("git", "add", "-A", cwd=self.remote, env=self.git_env())
        run(
            "git",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            message,
            cwd=self.remote,
            env=self.git_env(),
        )
        return run("git", "rev-parse", "HEAD", cwd=self.remote)

    def fix_branch(self, seed=None, extra=None):
        """A branch off main with one commit: the seed without reader in
        'reader: all', or the seed given, and another file if asked."""
        run(
            "git",
            "checkout",
            "-q",
            "-b",
            f"fix-{len(self.checked)}-{time.time_ns()}",
            "main",
            cwd=self.remote,
        )
        if seed is None:
            seed = json.loads(json.dumps(SEED))
            seed["objects"][0]["items"][1]["users"] = []
        self.write_seed(seed)
        if extra:
            (self.remote / extra).write_text("x\n")
        commit = self.commit("the fix")
        run("git", "checkout", "-q", "main", cwd=self.remote)
        return commit

    def tag(self, name, commit, key="approver", when=None, message="target: netbox"):
        run(
            "git",
            "-c",
            "gpg.format=ssh",
            "-c",
            f"user.signingkey={self.tmp / key}",
            "tag",
            "-s",
            name,
            "-m",
            message,
            commit,
            cwd=self.remote,
            env=self.git_env(time.time() if when is None else when),
        )
        return name

    def test_a_fix_is_delivered_and_checked(self):
        tag = self.tag("approve/netbox/nb-1", self.fix_branch())
        result = deliver.deliver(tag, TOKEN)
        self.assertEqual(result["mode"], "fix")
        self.assertTrue(result["passed"], result)
        self.assertEqual(
            self.live.patches, [("PATCH", "/api/users/permissions/12/", {"users": []})]
        )
        self.assertEqual(len(self.checked), 1)
        written = self.state / "results" / "approve_netbox_nb-1.json"
        self.assertEqual(json.loads(written.read_text())["commit"], result["commit"])

    def test_a_tag_signed_by_another_key_is_refused(self):
        tag = self.tag("approve/netbox/nb-1", self.fix_branch(), key="other")
        with self.assertRaisesRegex(deliver.Refused, "not the approval key"):
            deliver.deliver(tag, TOKEN)
        self.assertEqual(self.live.patches, [])

    def test_a_used_tag_is_refused(self):
        tag = self.tag("approve/netbox/nb-1", self.fix_branch())
        deliver.deliver(tag, TOKEN)
        with self.assertRaisesRegex(deliver.Refused, "used"):
            deliver.deliver(tag, TOKEN)

    def test_a_tag_older_than_a_day_is_refused(self):
        tag = self.tag(
            "approve/netbox/nb-1", self.fix_branch(), when=time.time() - 86400 - 60
        )
        with self.assertRaisesRegex(deliver.Refused, "older than"):
            deliver.deliver(tag, TOKEN)
        self.assertEqual(self.live.patches, [])

    def test_a_tag_from_the_future_is_refused(self):
        tag = self.tag(
            "approve/netbox/nb-1", self.fix_branch(), when=time.time() + 3600
        )
        with self.assertRaisesRegex(deliver.Refused, "ahead"):
            deliver.deliver(tag, TOKEN)

    def test_a_tag_for_another_target_is_refused(self):
        tag = self.tag("approve/netbox/nb-1", self.fix_branch(), message="target: lab")
        with self.assertRaisesRegex(deliver.Refused, "target: netbox"):
            deliver.deliver(tag, TOKEN)

    def test_a_fix_that_changes_another_file_is_refused(self):
        tag = self.tag("approve/netbox/nb-1", self.fix_branch(extra="README.md"))
        with self.assertRaisesRegex(deliver.Refused, "changes more than the seed"):
            deliver.deliver(tag, TOKEN)
        self.assertEqual(self.live.patches, [])

    def test_a_seed_change_that_adds_a_user_is_refused_in_fix_mode(self):
        seed = json.loads(json.dumps(SEED))
        seed["objects"][0]["items"][2]["users"] = ["control", "other"]
        tag = self.tag("approve/netbox/nb-1", self.fix_branch(seed=seed))
        with self.assertRaisesRegex(deliver.Refused, "removes nobody, or adds"):
            deliver.deliver(tag, TOKEN)
        self.assertEqual(self.live.patches, [])

    def test_drift_is_refused_and_nothing_applied(self):
        self.live.permissions[13]["users"] = [2, 3]
        tag = self.tag("approve/netbox/nb-1", self.fix_branch())
        with self.assertRaisesRegex(deliver.Refused, "control: tenant-a"):
            deliver.deliver(tag, TOKEN)
        self.assertEqual(self.live.patches, [])
        self.assertFalse((self.state / "used").exists())

    def test_restore_mode_applies_mains_seed(self):
        self.live.permissions[12]["users"] = []
        self.verdicts = dict(
            WITHIN, reader={"configured": "excess", "observed": "excess"}
        )
        tag = self.tag("approve/netbox/restore-20261027-1200", self.main)
        result = deliver.deliver(tag, TOKEN)
        self.assertEqual(result["mode"], "restore")
        self.assertEqual(
            self.live.patches, [("PATCH", "/api/users/permissions/12/", {"users": [1]})]
        )
        self.assertEqual(
            result["verdicts"]["reader"], {"configured": "excess", "observed": "excess"}
        )

    def test_the_ledger_is_written_before_the_change(self):
        tag = self.tag("approve/netbox/nb-1", self.fix_branch())
        deliver.deliver(tag, TOKEN)
        self.assertEqual(len(self.live.ledger_at_patch), 1)
        self.assertEqual(len(self.live.ledger_at_patch[0].split()), 1)

    def test_a_failed_check_after_delivery_stops_for_the_operator(self):
        self.verdicts = dict(
            WITHIN, reader={"configured": "excess", "observed": "within"}
        )
        tag = self.tag("approve/netbox/nb-1", self.fix_branch())
        result = deliver.deliver(tag, TOKEN)
        self.assertFalse(result["passed"])
        # No automatic rollback: the one change stays.
        self.assertEqual(len(self.live.patches), 1)

    def test_a_commit_that_is_not_on_main_or_a_child_of_it_is_refused(self):
        first = self.fix_branch()
        run("git", "checkout", "-q", "-b", "deeper", first, cwd=self.remote)
        (self.remote / "netbox" / "contract.json").write_text(
            json.dumps(CONTRACT) + "\n"
        )
        second = self.commit("another")
        run("git", "checkout", "-q", "main", cwd=self.remote)
        tag = self.tag("approve/netbox/nb-1", second)
        with self.assertRaisesRegex(
            deliver.Refused, "neither main's head nor a child of it"
        ):
            deliver.deliver(tag, TOKEN)

    def test_the_token_comes_from_standard_input(self):
        tag = self.tag("approve/netbox/nb-1", self.fix_branch())
        with mock.patch("sys.stdout", new=io.StringIO()):
            code = deliver.main(["deliver", tag], stdin=io.StringIO(TOKEN + "\n"))
        self.assertEqual(code, 0)
        self.assertEqual(self.tokens, [TOKEN])

    def test_no_token_on_standard_input_stops_before_the_fetch(self):
        tag = self.tag("approve/netbox/nb-1", self.fix_branch())
        for given in (
            "",
            "\n",
            "not-a-token\n",
            TOKEN + "x\n",
            TOKEN + "\n" + TOKEN + "\n",
        ):
            with (
                self.subTest(given=given),
                mock.patch.object(
                    deliver, "fetch", side_effect=AssertionError("fetched")
                ),
                mock.patch("sys.stderr", new=io.StringIO()),
            ):
                self.assertEqual(
                    deliver.main(["deliver", tag], stdin=io.StringIO(given)), 2
                )
        self.assertEqual(self.tokens, [])

    def test_a_terminal_is_not_read_for_a_token(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        with mock.patch("sys.stderr", new=io.StringIO()):
            code = deliver.main(
                ["deliver", "approve/netbox/nb-1"], stdin=Terminal(TOKEN)
            )
        self.assertEqual(code, 2)
        self.assertEqual(self.tokens, [])

    def test_the_token_is_written_nowhere(self):
        tag = self.tag("approve/netbox/nb-1", self.fix_branch())
        with mock.patch("sys.stdout", new=io.StringIO()):
            deliver.main(["deliver", tag], stdin=io.StringIO(TOKEN + "\n"))
        written = [p for p in self.state.rglob("*") if p.is_file()]
        self.assertTrue(written)
        for path in written:
            self.assertNotIn(TOKEN, path.read_text(errors="replace"), path)


if __name__ == "__main__":
    unittest.main()
