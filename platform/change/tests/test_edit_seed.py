"""The seed edit for a proposal's pull request (ADR 0045)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import edit_seed

SEED = """{
  "objects": [
    {
      "path": "/api/users/permissions/",
      "key": "name",
      "items": [
        {
          "name": "inventory-reader: tenant-a inventory",
          "enabled": true,
          "users": ["inventory-reader"]
        },
        {
          "name": "inventory-reader: inventory",
          "enabled": true,
          "users": ["inventory-reader"]
        },
        {
          "name": "shared: inventory",
          "enabled": true,
          "users": ["inventory-reader", "inventory-reader-control"]
        }
      ]
    }
  ],
  "tokens": []
}
"""


def bundle(*changes):
    return {
        "job": "nb-1",
        "policy": {
            "allowed": True,
            "reasons": [],
            "changes": [
                {"account": a, "permission_id": i, "permission": p}
                for a, i, p in changes
            ],
        },
    }


class EditSeed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.seed = self.tmp / "seed.json"
        self.seed.write_text(SEED)
        self.proposal = self.tmp / "proposal.json"

    def run_edit(self, document, seed_text=SEED):
        self.seed.write_text(seed_text)
        self.proposal.write_text(json.dumps(document))
        return edit_seed.main(["edit_seed.py", str(self.seed), str(self.proposal)])

    def test_the_seeds_fix_changes_one_line(self):
        code = self.run_edit(
            bundle(("inventory-reader", 2, "inventory-reader: inventory"))
        )
        self.assertEqual(code, 0)
        old, new = SEED.splitlines(), self.seed.read_text().splitlines()
        changed = [(a, b) for a, b in zip(old, new, strict=True) if a != b]
        self.assertEqual(
            changed,
            [('          "users": ["inventory-reader"]', '          "users": []')],
        )

    def test_one_of_two_users_goes_and_the_other_stays(self):
        code = self.run_edit(bundle(("inventory-reader", 3, "shared: inventory")))
        self.assertEqual(code, 0)
        self.assertIn('"users": ["inventory-reader-control"]', self.seed.read_text())

    def test_a_permission_not_in_the_seed_fails(self):
        code = self.run_edit(bundle(("inventory-reader", 9, "gone: inventory")))
        self.assertEqual(code, 1)
        self.assertEqual(self.seed.read_text(), SEED)

    def test_an_account_the_permission_does_not_name_fails(self):
        code = self.run_edit(bundle(("nobody", 2, "inventory-reader: inventory")))
        self.assertEqual(code, 1)
        self.assertEqual(self.seed.read_text(), SEED)

    def test_a_result_that_differs_elsewhere_fails(self):
        # A text edit that also changes another permission's users, as a bug in
        # it would. The parsed result has to show it before anything is written.
        edit = edit_seed.edit_text

        def also_elsewhere(text, changes):
            return edit(text, changes).replace(
                '["inventory-reader", "inventory-reader-control"]',
                '["inventory-reader-control"]',
            )

        with mock.patch.object(edit_seed, "edit_text", also_elsewhere):
            code = self.run_edit(
                bundle(("inventory-reader", 2, "inventory-reader: inventory"))
            )
        self.assertEqual(code, 1)
        self.assertEqual(self.seed.read_text(), SEED)

    def test_a_refused_proposal_is_not_applied(self):
        refused = bundle(("inventory-reader", 2, "inventory-reader: inventory"))
        refused["policy"]["allowed"] = False
        self.assertEqual(self.run_edit(refused), 1)
        self.assertEqual(self.seed.read_text(), SEED)


if __name__ == "__main__":
    unittest.main()
