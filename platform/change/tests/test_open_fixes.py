"""The open fix pull requests check, on the operator's machine (ADR 0053).

The pull requests come as JSON on standard input, as the GitHub API lists
them; nothing is fetched.
"""

import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import open_fixes

CHANGE = {
    "account": "inventory-reader",
    "permission_id": 2,
    "permission": "inventory-reader: inventory",
}
BUNDLE = {"job": "nb-2", "policy": {"allowed": True, "changes": [CHANGE]}}
ROW = "| `inventory-reader` | excess, excess | excess | remove `inventory-reader: inventory` (ID 2) |"


def pull(number, body, ref="fix/netbox-nb-1"):
    return {"number": number, "head": {"ref": ref}, "title": "fix: x", "body": body}


class OpenFixes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bundle = self.tmp / "proposal.json"
        self.bundle.write_text(json.dumps(BUNDLE))

    def run_check(self, pulls, argv=None):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            code = open_fixes.main(
                argv or ["open_fixes.py", str(self.bundle)],
                stdin=io.StringIO(json.dumps(pulls)),
            )
        return code, out.getvalue()

    def test_no_open_pull_request_passes(self):
        code, out = self.run_check([])
        self.assertEqual(code, 0)
        self.assertIn("no open pull request with this fix", out)

    def test_an_open_pull_request_with_the_same_fix_fails(self):
        code, out = self.run_check([pull(14, f"## A fix\n\n{ROW}\n")])
        self.assertEqual(code, 1)
        self.assertIn(
            "#14 fix/netbox-nb-1: `inventory-reader` loses permission 2 there", out
        )

    def test_another_permission_or_account_passes(self):
        rows = [
            ROW.replace("(ID 2)", "(ID 1)"),
            ROW.replace("`inventory-reader`", "`inventory-reader-control`"),
        ]
        code, out = self.run_check([pull(14, "\n".join(rows))])
        self.assertEqual(code, 0)
        self.assertIn("1 open pull request read", out)

    def test_a_body_in_another_shape_is_not_matched(self):
        body = "remove `inventory-reader: inventory` (ID 2) for inventory-reader"
        code, _ = self.run_check([pull(15, body)])
        self.assertEqual(code, 0)

    def test_the_usage_needs_the_bundle_and_a_list(self):
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(
                open_fixes.main(["open_fixes.py"], stdin=io.StringIO("[]")), 2
            )
            self.assertEqual(
                open_fixes.main(
                    ["open_fixes.py", str(self.bundle)], stdin=io.StringIO('{"a": 1}')
                ),
                2,
            )


if __name__ == "__main__":
    unittest.main()
