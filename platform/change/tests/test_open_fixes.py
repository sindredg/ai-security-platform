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
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "collectors" / "netbox"))
sys.path.insert(0, str(HERE))

import open_fixes
import propose

CHANGE = {
    "account": "inventory-reader",
    "permission_id": 2,
    "permission": "inventory-reader: inventory",
}
BUNDLE = {"job": "nb-2", "policy": {"allowed": True, "changes": [CHANGE]}}
ROW = "| `inventory-reader` | excess, excess | excess | remove `inventory-reader: inventory` (ID 2) |"


TARGETS = "owner/targets"


def pull(number, body, ref="fix/netbox-nb-1", head_repo=TARGETS):
    head = {"ref": ref, "repo": None if head_repo is None else {"full_name": head_repo}}
    return {
        "number": number,
        "head": head,
        "base": {"ref": "main", "repo": {"full_name": TARGETS}},
        "title": "fix: x",
        "body": body,
    }


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

    def test_a_pull_request_from_a_fork_does_not_count(self):
        # The targets repository is public, so anyone can open a pull request
        # from a fork with the same rows in its body. Only a branch of the
        # targets repository itself, which takes write access, holds a fix.
        code, out = self.run_check([pull(15, f"{ROW}\n", head_repo="outsider/fork")])
        self.assertEqual(code, 0)
        self.assertIn("1 from another repository not counted", out)
        self.assertIn("no open pull request with this fix", out)

    def test_a_pull_request_whose_fork_is_gone_does_not_count(self):
        # GitHub lists a deleted fork's head repository as null.
        code, out = self.run_check([pull(16, f"{ROW}\n", head_repo=None)])
        self.assertEqual(code, 0)
        self.assertNotIn("#16", out)

    def test_a_fork_does_not_hide_a_same_repository_pull_request(self):
        pulls = [pull(15, f"{ROW}\n", head_repo="outsider/fork"), pull(14, f"{ROW}\n")]
        code, out = self.run_check(pulls)
        self.assertEqual(code, 1)
        self.assertIn("#14 fix/netbox-nb-1", out)
        self.assertNotIn("#15", out)

    def test_a_body_with_windows_line_endings_is_read_too(self):
        # GitHub's web editor saves a body with CRLF.
        body = f"## A fix\r\n\r\n{ROW}\r\n"
        code, out = self.run_check([pull(14, body)])
        self.assertEqual(code, 1)
        self.assertIn("#14", out)

    def test_the_row_pattern_matches_what_the_propose_command_writes(self):
        # The two checks of ADR 0053 stay in step: a body pr_body writes is read.
        bundle = {
            "job": "nb-2",
            "case": "seed",
            "collected": "2026-10-30T18:00:00Z",
            "source": "model",
            "comparison": {
                "accounts": [
                    {
                        "account": "inventory-reader",
                        "configured": "excess",
                        "observed": "excess",
                        "model": "excess",
                    }
                ],
                "proposals": [
                    {
                        "account": "inventory-reader",
                        "action": "remove",
                        "permission": 2,
                        "references": ["ev-0002"],
                    }
                ],
            },
            "policy": {"allowed": True, "reasons": [], "changes": [CHANGE]},
            "rehearsal": {
                "passed": True,
                "verdicts": {
                    "inventory-reader": {"configured": "within", "observed": "within"}
                },
            },
        }
        body = propose.pr_body(bundle)
        self.assertEqual(open_fixes.ROW.findall(body), [("inventory-reader", "2")])
        code, _ = self.run_check([pull(14, body)])
        self.assertEqual(code, 1)

    def test_a_rule_fix_matches_the_rows_the_propose_command_writes(self):
        # ADR 0056: a fix for NetBox's port rules, by the inbound rule's priority.
        removed = [
            {
                "name": "allow-netbox-from-rehearsal",
                "direction": direction,
                "priority": 1120,
                "subnet": subnet,
            }
            for direction, subnet in (("Inbound", "netbox"), ("Outbound", "rehearsal"))
        ]
        change = {
            "account": "viewpoint-staging",
            "rule": "allow-netbox-from-rehearsal",
            "priority": 1120,
            "removed": removed,
            "commit": "c" * 40,
            "sha256": "d" * 64,
        }
        bundle = {
            "job": "nb-3",
            "case": "seed",
            "collected": "2026-11-01T21:18:00Z",
            "source": "model",
            "comparison": {
                "accounts": [
                    {
                        "account": "viewpoint-staging",
                        "configured": "excess",
                        "observed": "excess",
                        "model": "excess",
                    }
                ],
                "proposals": [
                    {
                        "account": "viewpoint-staging",
                        "action": "remove",
                        "permission": 1120,
                        "references": ["ev-0004"],
                    }
                ],
            },
            "policy": {"allowed": True, "reasons": [], "changes": [change]},
            "rehearsal": {
                "passed": True,
                "verdicts": {"viewpoint-staging": {"configured": "within"}},
            },
        }
        body = propose.rules_pr_body(bundle)
        self.assertEqual(open_fixes.rows(body), [("viewpoint-staging", 1120)])
        self.bundle.write_text(json.dumps(bundle))
        code, out = self.run_check([pull(15, body, ref="fix/exercise-2-nb-1")])
        self.assertEqual(code, 1)
        self.assertIn(
            "#15 fix/exercise-2-nb-1: `viewpoint-staging` loses rule 1120 there already",
            out,
        )
        other = body.replace("(Inbound, 1120)", "(Inbound, 1130)")
        self.assertEqual(self.run_check([pull(16, other)])[0], 0)
        # A permission's row with the same number is another fix.
        self.assertEqual(
            self.run_check([pull(17, ROW.replace("ID 2", "ID 1120"))])[0], 0
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
