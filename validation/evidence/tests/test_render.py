"""The evidence pages from their records, and the checks that guard them.

main() runs against a temporary tree with the layout of the repository's, so
--check is tried on pages that match, a changed record, a page left over,
and records that must fail.
"""

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render

CHECKS = {
    "inventory-reader": ["excess", "excess"],
    "inventory-reader-control": ["within", "excess"],
}


def job(name, **fields):
    base = {
        "job": name,
        "case": None,
        "started": "2026-10-25T23:09:34Z",
        "finished": "2026-10-25T23:16:07Z",
        "phase": "Succeeded",
        "message": "",
        "steps": [{"step": "dispatch", "phase": "Succeeded", "message": ""}],
        "result": {
            "status": "completed",
            "seconds": 357.4,
            "input_tokens": 9119,
            "output_tokens": 933,
            "slot_erased": True,
        },
        "checks": None,
        "comparison": None,
        "calls": [
            {
                "at": "2026-10-25T23:11:19Z",
                "tool": "get_evidence",
                "argument": "ev-0001",
                "decision": "allowed",
                "reason": None,
                "bytes": 1471,
            }
        ],
        "answer": "Status: confirmed",
    }
    return {**base, **fields}


def stopped(name, accounts, reasons):
    rows = [
        {
            "account": a,
            "model": m,
            "references": ["ev-0003"],
            "configured": CHECKS[a][0],
            "observed": CHECKS[a][1],
            "outcome": o,
        }
        for a, m, o in accounts
    ]
    return job(
        name,
        phase="Failed",
        steps=[
            {"step": "dispatch", "phase": "Succeeded", "message": ""},
            {
                "step": "compare",
                "phase": "Failed",
                "message": "main: Error (exit code 1): stop",
            },
        ],
        checks=CHECKS,
        comparison={"outcome": "stop", "reasons": reasons, "accounts": rows},
    )


RUN_SET = {
    "title": "A run set",
    "short": "Run set",
    "milestone": 4,
    "tested": "Whether the pages say what the records hold.",
    "changed": "Nothing.",
    "setup": [["Model", "Qwen3.5-4B, thinking off"]],
    "source": "Made up for the tests.",
    "links": [["Worklog", "../worklogs/0005-netbox-target-and-exercise-1.md"]],
    "jobs": [
        job("syn-1"),
        stopped(
            "nb-1",
            [
                ("inventory-reader", "excess", "match"),
                ("inventory-reader-control", "within", "checks-disagree"),
            ],
            [
                "inventory-reader-control: the checks disagree, configured within, observed excess",
                "verdict lines that could not be read: 2",
            ],
        ),
    ],
}
LESSONS = {
    "intro": "What the runs showed.",
    "lessons": [
        {
            "finding": "A finding.",
            "runs": ["2026-10-25-2308-a-run-set#nb-1"],
            "change": "Nothing yet.",
        }
    ],
}


class Outcome(unittest.TestCase):
    def test_a_match_and_a_job_with_nothing_to_compare(self):
        compared = job(
            "nb-2",
            checks=CHECKS,
            comparison={"outcome": "match", "reasons": [], "accounts": []},
        )
        self.assertEqual(render.outcome(compared), "Match")
        self.assertEqual(render.outcome(job("syn-1")), "Completed")

    def test_a_stop_names_each_cause_once(self):
        nb = RUN_SET["jobs"][1]
        self.assertEqual(
            render.outcome(nb), "Stop: checks disagree, 2 unreadable lines"
        )
        wrong = stopped(
            "nb-3",
            [
                ("inventory-reader", "missing", "mismatch"),
                ("inventory-reader-control", None, "no-verdict"),
            ],
            [
                "inventory-reader: the model says missing, the checks say excess",
                "verdict lines that could not be read: 1",
            ],
        )
        self.assertEqual(
            render.outcome(wrong),
            "Stop: wrong verdict, no verdict line, 1 unreadable line",
        )

    def test_a_timeout_a_stop_a_refusal_and_a_job_without_a_workflow(self):
        failed = [
            {
                "step": "dispatch",
                "phase": "Failed",
                "message": "main: Error (exit code 1)",
            }
        ]
        timeout = job(
            "nb-4",
            phase="Failed",
            steps=failed,
            result={"status": "timeout", "seconds": 1290.5},
        )
        self.assertEqual(render.outcome(timeout), "Failed: time limit reached")
        stop = job(
            "w-1", phase="Failed", message="Stopped with strategy 'Stop'", steps=failed
        )
        self.assertEqual(render.outcome(stop), "Stopped")
        refused = job(
            "w-2",
            phase="Error",
            message="workflows must use workflowTemplateRef",
            steps=[],
        )
        self.assertEqual(render.outcome(refused), "Refused")
        by_hand = job("hand-1", phase=None, steps=[], result={"status": "cancelled"})
        self.assertEqual(render.outcome(by_hand), "Cancelled")


class Counts(unittest.TestCase):
    def test_verdicts_right_counts_only_accounts_whose_checks_agree(self):
        self.assertEqual(render.verdicts_right(RUN_SET["jobs"][1]), "1 of 1")
        self.assertEqual(render.verdicts_right(job("syn-1")), "No checks")

    def test_calls_name_the_refused_and_gooses_own(self):
        calls = [
            {"decision": "allowed"},
            {"decision": "refused"},
            {"decision": "goose"},
        ]
        self.assertEqual(
            render.call_count({"calls": calls}), "3, 1 refused, 1 to Goose's own tools"
        )


class Unpublishable(unittest.TestCase):
    def test_each_kind_is_found(self):
        for text, label in [
            ("seen at 100.64.1.2", "a public address, 100.64.1.2"),
            ("key 0123456789abcdef0123456789abcdef", "a long hex string"),
            ("in /home/someone/x", "a home directory"),
            ("sub 12345678-1234-1234-1234-123456789abc", "a GUID"),
            ("mail a.b@example.com", "an email address"),
            ("-----BEGIN OPENSSH PRIVATE KEY-----", "a private key"),
        ]:
            self.assertIn(label, render.unpublishable(text), text)

    def test_private_and_seed_addresses_pass(self):
        self.assertEqual(
            render.unpublishable("10.40.0.36 and 172.16.1.1/24, ev-0001"), []
        )


class PageRules(unittest.TestCase):
    def test_each_rule_is_found(self):
        page = "\n".join(
            [
                "| a | b | c | d | e | f |",
                "",
                "One. Two. Three. Four.",
                "",
                "A — dash.",
                "",
                "| " + "word " * 30 + "|",
            ]
        )
        problems = " ".join(render.page_problems("p", page))
        for found in ("6 columns", "4 sentences", "an em dash", "a cell of 30 words"):
            self.assertIn(found, problems)

    def test_code_blocks_and_a_page_within_the_rules_pass(self):
        page = "One. Two. Three.\n\n- An item. Another.\n\n```text\nOne. Two. Three. Four. Five — six.\n```\n"
        self.assertEqual(render.page_problems("p", page), [])


class Rules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, name, text):
        path = self.folder / name
        path.write_text(text)
        return str(path)

    def run_rules(self, *pages):
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            code = render.main(["render.py", "--rules", *pages])
        return code, err.getvalue()

    def test_pages_within_the_rules_pass(self):
        pages = (
            self.page("a.md", "# A\n\nOne. Two. Three.\n"),
            self.page("b.md", "| x | y |\n| --- | --- |\n| 1 | 2 |\n"),
        )
        self.assertEqual(self.run_rules(*pages), (0, ""))

    def test_a_page_that_breaks_a_rule_fails_and_is_named(self):
        good = self.page("a.md", "One. Two. Three.\n")
        bad = self.page("b.md", "One. Two. Three. Four.\n")
        code, err = self.run_rules(good, bad)
        self.assertEqual(code, 1)
        self.assertIn(f"{bad}: a paragraph of 4 sentences", err)
        self.assertNotIn(good, err)

    def test_a_page_that_cannot_be_read_fails(self):
        code, err = self.run_rules(str(self.folder / "gone.md"))
        self.assertEqual(code, 1)
        self.assertIn("gone.md: cannot be read", err)

    def test_no_page_is_a_usage_error(self):
        self.assertEqual(self.run_rules()[0], 2)


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.records = self.root / "docs" / "evidence" / "records"
        self.records.mkdir(parents=True)
        self.write(RUN_SET, LESSONS)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, run_set, lessons):
        (self.records / "2026-10-25-2308-a-run-set.json").write_text(
            json.dumps(run_set)
        )
        (self.records / "lessons.json").write_text(json.dumps(lessons))

    def run_main(self, *args):
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            code = render.main(["render.py", *args], self.root)
        return code, err.getvalue()

    def test_written_pages_pass_the_check(self):
        self.assertEqual(self.run_main()[0], 0)
        pages = sorted(p.name for p in (self.root / "docs" / "evidence").glob("*.md"))
        self.assertEqual(
            pages, ["2026-10-25-2308-a-run-set.md", "README.md", "lessons.md"]
        )
        self.assertEqual(self.run_main("--check")[0], 0)

    def test_a_changed_record_fails_the_check(self):
        self.run_main()
        changed = copy.deepcopy(RUN_SET)
        changed["jobs"][0]["answer"] = "Status: refuted"
        self.write(changed, LESSONS)
        code, err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("out of date: docs/evidence/2026-10-25-2308-a-run-set.md", err)

    def test_a_page_without_a_record_fails_the_check(self):
        self.run_main()
        (self.root / "docs" / "evidence" / "old.md").write_text("# Old\n")
        code, err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("no record for: docs/evidence/old.md", err)

    def test_a_lesson_naming_a_job_without_a_record_fails(self):
        lessons = copy.deepcopy(LESSONS)
        lessons["lessons"][0]["runs"] = ["2026-10-25-2308-a-run-set#nb-9"]
        self.write(RUN_SET, lessons)
        code, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("no run set or job 2026-10-25-2308-a-run-set#nb-9", err)

    def test_a_record_with_a_public_address_or_no_title_writes_nothing(self):
        for broken in (
            {**RUN_SET, "source": "Read from 100.64.1.2."},
            {k: v for k, v in RUN_SET.items() if k != "title"},
        ):
            self.write(broken, LESSONS)
            self.assertEqual(self.run_main()[0], 1)
            self.assertEqual(list((self.root / "docs" / "evidence").glob("*.md")), [])


if __name__ == "__main__":
    unittest.main()
