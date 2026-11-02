"""The editor for an allowed fix of NetBox's port rules (ADR 0056), on a copy
of exercise 2's seed in a temporary folder."""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import edit_rules

FIXTURE = json.loads(
    (REPO / "collectors" / "netbox" / "tests" / "network.json").read_text(
        encoding="utf-8"
    )
)
TEXT = json.dumps(FIXTURE["rules"], indent=2) + "\n"
REMOVED = [
    {
        "subnet": "netbox",
        "direction": "Inbound",
        "name": "allow-netbox-from-rehearsal",
        "priority": 1120,
    },
    {
        "subnet": "rehearsal",
        "direction": "Outbound",
        "name": "allow-netbox-from-rehearsal",
        "priority": 1120,
    },
]


def bundle(allowed=True, removed=REMOVED, sha256=None, passed=True, rule=True):
    change = {
        "account": "viewpoint-staging",
        "priority": 1120,
        "removed": removed,
        "commit": "c" * 40,
        "sha256": sha256 or hashlib.sha256(TEXT.encode()).hexdigest(),
    }
    if rule:
        change["rule"] = "allow-netbox-from-rehearsal"
    return {
        "policy": {"allowed": allowed, "reasons": [], "changes": [change]},
        "rehearsal": {"passed": passed},
    }


class Edit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.rules = self.tmp / "netbox-rules.json"
        self.rules.write_text(TEXT)

    def run_edit(self, found, text=None):
        if text is not None:
            self.rules.write_text(text)
        proposal = self.tmp / "proposal.json"
        proposal.write_text(json.dumps(found))
        return edit_rules.main(["edit_rules.py", str(self.rules), str(proposal)])

    def test_the_fix_removes_the_two_rules_and_nothing_else(self):
        self.assertEqual(self.run_edit(bundle()), 0)
        new = self.rules.read_text()
        old_lines, new_lines = TEXT.splitlines(), new.splitlines()
        # Two rules of eleven lines each, and the rehearsal subnet's list,
        # now empty, on one line.
        self.assertEqual(len(old_lines) - len(new_lines), 23)
        rules = json.loads(new)
        self.assertEqual([r["priority"] for r in rules["netbox"]], [1110])
        self.assertEqual(rules["rehearsal"], [])
        self.assertEqual(rules["consumer"], FIXTURE["rules"]["consumer"])
        changed = [line for line in new_lines if line not in old_lines]
        self.assertEqual(changed, ['  "rehearsal": []'])

    def test_refusals_leave_the_file_as_it_was(self):
        cases = {
            "not allowed": (bundle(allowed=False), None),
            "the judgment did not pass": (bundle(passed=False), None),
            "a change to permissions": (bundle(rule=False), None),
            "another file": (bundle(sha256="0" * 64), None),
            "another layout": (
                bundle(
                    sha256=hashlib.sha256(
                        json.dumps(FIXTURE["rules"]).encode()
                    ).hexdigest()
                ),
                json.dumps(FIXTURE["rules"]),
            ),
            "a rule that is not there": (
                bundle(removed=[dict(REMOVED[0], priority=1130)]),
                None,
            ),
        }
        for why, (found, text) in cases.items():
            with self.subTest(why):
                self.rules.write_text(text if text is not None else TEXT)
                before = self.rules.read_text()
                self.assertEqual(self.run_edit(found), 1, why)
                self.assertEqual(self.rules.read_text(), before)

    def test_an_edit_that_removes_another_rule_is_refused(self):
        # The check compares the new file with the old rules less the
        # bundle's keys, worked out apart from removed_from. A removed_from
        # that also drops the consumer's rule has to be caught there.
        real = edit_rules.removed_from

        def one_too_many(rules, removed):
            left = real(rules, removed)
            left["consumer"] = []
            return left

        edit_rules.removed_from = one_too_many
        self.addCleanup(setattr, edit_rules, "removed_from", real)
        self.assertEqual(self.run_edit(bundle()), 1)
        self.assertEqual(self.rules.read_text(), TEXT)

    def test_the_usage_needs_two_files(self):
        self.assertEqual(edit_rules.main(["edit_rules.py"]), 2)


if __name__ == "__main__":
    unittest.main()
