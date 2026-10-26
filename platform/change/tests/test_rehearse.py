"""The rehearsal of a fix on the copy (ADR 0044).

ssh and the collector's interpreter are stubs that write what they were asked
and answer from files, as the collect command's tests do. The copy's client
is a fake that holds the copy's own permission IDs, which differ from the
live NetBox's.
"""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "collectors" / "netbox"))
sys.path.insert(0, str(HERE))

import netbox_change
import rehearse

REPORTS = json.loads(
    (REPO / "collectors" / "netbox" / "tests" / "reports.json").read_text()
)
SEED_SHA = "a" * 64
FAKE_SSH = """#!{python} -I
import os, sys
d = os.environ["FAKE_DIR"]
target = [a for a in sys.argv[1:] if "@" in a][0]
rest = sys.argv[sys.argv.index(target) + 1 :]
with open(d + "/events", "a") as f:
    f.write(" ".join([target.split("@")[0], *rest]) + "\\n")
if target.startswith("aisec-rehearse@"):
    sys.stdout.write(open(d + "/reset.out").read())
else:
    sys.stdin.read()
    sys.stdout.write(open(d + "/observed.out").read())
"""
FAKE_PYTHON = """#!{python} -I
import os, sys
d = os.environ["FAKE_DIR"]
sys.stdin.read()
with open(d + "/events", "a") as f:
    names = ("AISEC_NETBOX_URL", "AISEC_NETBOX_CERT", "AISEC_NETBOX_TOKENS")
    f.write(" ".join(["configured", *[os.environ.get(n, "-") for n in names], *sys.argv[1:]]) + "\\n")
sys.stdout.write(open(d + "/configured.out").read())
"""


def within(report):
    """The report with every account within, as after a fix."""
    report = copy.deepcopy(report)
    for account in report["accounts"].values():
        account["verdict"], account["reasons"] = "within", []
    return report


class FakeCopy:
    """The copy's NetBox, with its own IDs for the seed's permissions."""

    def __init__(self, events):
        self.events = events
        self.users = {31: "inventory-reader", 32: "inventory-reader-control"}
        self.permissions = {
            21: {"name": "inventory-reader: tenant-a inventory", "users": [31]},
            22: {"name": "inventory-reader: inventory", "users": [31]},
        }
        self.patches = []

    def reset_seen(self):
        if not self.events.exists() or "aisec-rehearse" not in self.events.read_text():
            raise AssertionError("the copy was changed before its reset")

    def list(self, path, **query):
        self.reset_seen()
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
        found = [
            {"id": i, "username": n}
            for i, n in self.users.items()
            if n == query["username"]
        ]
        return 200, found

    def call(self, method, path, body=None):
        self.reset_seen()
        self.patches.append((method, path, body))
        return 200, {}


CHANGES = [
    {
        "account": "inventory-reader",
        "permission_id": 2,
        "permission": "inventory-reader: inventory",
    }
]


class Rehearse(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.events = self.tmp / "events"
        for name, text in (("ssh", FAKE_SSH), ("python3", FAKE_PYTHON)):
            path = self.tmp / name
            path.write_text(text.format(python=sys.executable))
            path.chmod(0o755)
        copy_dir = self.tmp / "copy"
        (copy_dir / "reset").mkdir(parents=True)
        (copy_dir / "reset" / "seed.sha256").write_text(SEED_SHA + "\n")
        self.write("reset.out", f"{SEED_SHA}\n")
        self.write("configured.out", json.dumps(within(REPORTS["configured"])))
        self.write("observed.out", json.dumps(within(REPORTS["observed"])))
        self.copy = FakeCopy(self.events)
        for patch in (
            mock.patch.object(rehearse, "SSH", str(self.tmp / "ssh")),
            mock.patch.object(rehearse, "PYTHON", str(self.tmp / "python3")),
            mock.patch.object(rehearse, "COPY", copy_dir),
            mock.patch.object(netbox_change, "client", lambda *a: self.copy),
            mock.patch.dict(os.environ, {"FAKE_DIR": str(self.tmp)}),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, name, text):
        (self.tmp / name).write_text(text)

    def test_a_rehearsal_resets_first_and_applies_by_name(self):
        result = rehearse.rehearse(CHANGES, REPORTS["contract"])
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["reset"], SEED_SHA)
        self.assertEqual(
            result["applied"],
            [{"permission": "inventory-reader: inventory", "id": 22, "users": []}],
        )
        # The copy's ID, not the live NetBox's 2.
        self.assertEqual(
            self.copy.patches, [("PATCH", "/api/users/permissions/22/", {"users": []})]
        )
        events = self.events.read_text().splitlines()
        self.assertEqual(events[0], "aisec-rehearse")
        self.assertIn("aisec-observe rehearsal", events)
        configured = [e for e in events if e.startswith("configured ")]
        self.assertEqual(len(configured), 1)
        self.assertIn(f"{self.tmp}/copy/tokens", configured[0])
        self.assertEqual(
            result["verdicts"],
            {
                name: {"configured": "within", "observed": "within"}
                for name in REPORTS["contract"]["accounts"]
            },
        )

    def test_the_copy_is_reset_after_the_halves_too(self):
        # So the copy rests at the seed between rehearsals, as Q.3 reads it.
        result = rehearse.rehearse(CHANGES, REPORTS["contract"])
        events = self.events.read_text().splitlines()
        self.assertEqual((events[0], events[-1]), ("aisec-rehearse", "aisec-rehearse"))
        self.assertEqual(result["reset_after"], SEED_SHA)

    def test_a_report_not_in_shape_fails_the_rehearsal(self):
        self.write("observed.out", '{"check": "observed", "accounts": {}}')
        result = rehearse.rehearse(CHANGES, REPORTS["contract"])
        self.assertFalse(result["passed"])
        self.assertIn("not the contract's accounts", result["reason"])

    def test_any_account_not_within_fails_it(self):
        still = within(REPORTS["configured"])
        still["accounts"]["inventory-reader"]["verdict"] = "excess"
        self.write("configured.out", json.dumps(still))
        result = rehearse.rehearse(CHANGES, REPORTS["contract"])
        self.assertFalse(result["passed"])
        self.assertEqual(
            result["verdicts"]["inventory-reader"],
            {"configured": "excess", "observed": "within"},
        )

    def test_a_reset_to_another_dump_fails_before_any_change(self):
        self.write("reset.out", "b" * 64 + "\n")
        result = rehearse.rehearse(CHANGES, REPORTS["contract"])
        self.assertFalse(result["passed"])
        self.assertIn("not the seed's dump", result["reason"])
        self.assertEqual(self.copy.patches, [])

    def test_a_change_for_an_account_the_copy_does_not_assign_fails(self):
        changes = [dict(CHANGES[0], account="inventory-reader-control")]
        result = rehearse.rehearse(changes, REPORTS["contract"])
        self.assertFalse(result["passed"])
        self.assertIn("does not hold it on the copy", result["reason"])
        self.assertEqual(self.copy.patches, [])


if __name__ == "__main__":
    unittest.main()
