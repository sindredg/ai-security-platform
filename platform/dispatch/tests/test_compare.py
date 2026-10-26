"""The comparison step: the model's verdict per account against the checks'.

compare.compare() gets the checks' verdicts and the answer as the workflow
hands them over. main() runs as a subprocess, as the step's container runs it,
with the three paths pointed into a temporary directory.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
TASK = REPO / "collectors" / "netbox" / "task.txt"
JOB_PROGRAM = REPO / "worker" / "agent-runtime" / "job" / "agent_job.py"
sys.path.insert(0, str(HERE))

import compare

CHECKS = {
    "inventory-reader": {"configured": "excess", "observed": "excess"},
    "inventory-reader-control": {"configured": "within", "observed": "within"},
}
RIGHT = (
    "The first account reads every tenant's devices (ev-0003).\n"
    "Verdict: inventory-reader excess ev-0002 ev-0003\n"
    "Verdict: inventory-reader-control within ev-0003\n"
)
CONTROL = "Verdict: inventory-reader-control within ev-0003\n"


def checks(account="inventory-reader", **verdicts):
    """CHECKS with one account's verdicts replaced."""
    return {**CHECKS, account: {**CHECKS[account], **verdicts}}


def document(job="nb-1", accounts=None):
    return {
        "job": job,
        "collected": "2026-10-25T16:00:00Z",
        "accounts": CHECKS if accounts is None else accounts,
    }


class TheComparison(unittest.TestCase):
    def test_a_match_on_every_account(self):
        result = compare.compare("nb-1", CHECKS, RIGHT)
        self.assertEqual(result["job"], "nb-1")
        self.assertEqual(result["outcome"], "match")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(
            result["accounts"],
            [
                {
                    "account": "inventory-reader",
                    "model": "excess",
                    "references": ["ev-0002", "ev-0003"],
                    "configured": "excess",
                    "observed": "excess",
                    "outcome": "match",
                },
                {
                    "account": "inventory-reader-control",
                    "model": "within",
                    "references": ["ev-0003"],
                    "configured": "within",
                    "observed": "within",
                    "outcome": "match",
                },
            ],
        )

    def test_a_mismatch_stops(self):
        answer = "Verdict: inventory-reader within ev-0003\n" + CONTROL
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(result["outcome"], "stop")
        self.assertEqual(
            result["reasons"],
            ["inventory-reader: the model says within, the checks say excess"],
        )
        self.assertEqual(result["accounts"][0]["outcome"], "mismatch")

    def test_an_inconclusive_verdict_stops(self):
        answer = "Verdict: inventory-reader inconclusive ev-0002\n" + CONTROL
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(result["outcome"], "stop")
        self.assertEqual(
            result["reasons"],
            [
                (
                    "inventory-reader: the model's verdict is inconclusive, "
                    "the checks say excess"
                )
            ],
        )

    def test_an_account_without_a_line_stops(self):
        result = compare.compare("nb-1", CHECKS, CONTROL)
        self.assertEqual(result["outcome"], "stop")
        self.assertEqual(
            result["reasons"],
            ["inventory-reader: the answer has no verdict line for it"],
        )
        row = result["accounts"][0]
        self.assertEqual((row["model"], row["references"]), (None, []))

    def test_checks_that_disagree_stop_whatever_the_model_says(self):
        result = compare.compare("nb-1", checks(observed="within"), RIGHT)
        self.assertEqual(result["outcome"], "stop")
        self.assertEqual(
            result["reasons"],
            [
                (
                    "inventory-reader: the checks disagree, configured excess, "
                    "observed within"
                )
            ],
        )

    def test_checks_that_cannot_settle_an_account_stop(self):
        answer = "Verdict: inventory-reader inconclusive ev-0002\n" + CONTROL
        unknown = checks(configured="unknown", observed="unknown")
        result = compare.compare("nb-1", unknown, answer)
        self.assertEqual(result["outcome"], "stop")
        self.assertEqual(
            result["reasons"], ["inventory-reader: the checks cannot settle it"]
        )

    def test_markdown_and_list_marks_are_read(self):
        answer = (
            "**Verdict:** `inventory-reader` excess (ev-0002, ev-0003)\n"
            "- Verdict: inventory-reader-control: within.\n"
        )
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(result["outcome"], "match", result["reasons"])
        self.assertEqual(
            [row["references"] for row in result["accounts"]],
            [["ev-0002", "ev-0003"], []],
        )

    def test_repeated_lines_that_agree_are_one_verdict(self):
        answer = (
            "Verdict: inventory-reader excess ev-0002\n"
            "More on the second document.\n"
            "Verdict: inventory-reader excess ev-0003\n" + CONTROL
        )
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(result["outcome"], "match", result["reasons"])
        self.assertEqual(result["accounts"][0]["references"], ["ev-0002", "ev-0003"])

    def test_lines_that_disagree_stop(self):
        answer = (
            "Verdict: inventory-reader excess ev-0002\n"
            "Verdict: inventory-reader within ev-0003\n" + CONTROL
        )
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(result["outcome"], "stop")
        self.assertEqual(
            result["reasons"], ["inventory-reader: the answer's verdict lines disagree"]
        )

    def test_a_line_for_an_account_the_checks_do_not_name_stops(self):
        answer = RIGHT + "Verdict: some-account within ev-0001\n"
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(result["outcome"], "stop")
        self.assertEqual(
            result["reasons"], ["some-account: not an account the checks name"]
        )
        self.assertEqual(
            [row["outcome"] for row in result["accounts"]], ["match", "match"]
        )

    def test_a_verdict_line_that_cannot_be_read_stops(self):
        answer = "Verdict: inventory-reader confirmed ev-0002\n" + CONTROL
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(result["outcome"], "stop")
        self.assertEqual(
            result["reasons"],
            [
                "inventory-reader: the answer has no verdict line for it",
                "verdict lines that could not be read: 1",
            ],
        )

    def test_no_accounts_is_never_a_match(self):
        result = compare.compare("nb-1", {}, RIGHT)
        self.assertEqual(result["outcome"], "stop")

    def test_a_dash_inside_a_name_is_not_a_separator(self):
        answer = "Verdict: inventory-reader-within ev-0002\n" + CONTROL
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(result["accounts"][0]["outcome"], "no-verdict")
        self.assertIn("verdict lines that could not be read: 1", result["reasons"])

    def test_a_line_under_any_markdown_mark_is_read(self):
        for mark in ("1. ", "2) ", "### ", "> ", "> - ", "__"):
            with self.subTest(mark):
                answer = (
                    f"{mark}Verdict: inventory-reader excess ev-0002\n"
                    f"{mark}Verdict: inventory-reader-control within ev-0003\n"
                )
                result = compare.compare("nb-1", CHECKS, answer)
                self.assertEqual(result["outcome"], "match", result["reasons"])

    def test_a_contradiction_under_another_mark_stops(self):
        # Unread, a line in another form would leave the right lines alone.
        for mark in ("1. ", "### ", "> ", "__"):
            with self.subTest(mark):
                answer = f"{mark}Verdict: inventory-reader within ev-0001\n" + RIGHT
                result = compare.compare("nb-1", CHECKS, answer)
                self.assertEqual(result["outcome"], "stop")
                self.assertIn(
                    "inventory-reader: the answer's verdict lines disagree",
                    result["reasons"],
                )

    def test_more_forms_of_a_line_are_read(self):
        for form in (
            "__Verdict: inventory-reader excess ev-0002 ev-0003__",
            "_Verdict: inventory-reader excess ev-0002_",
            "| Verdict: inventory-reader excess ev-0002 |",
            "- [x] Verdict: inventory-reader excess ev-0002",
            "1000. Verdict: inventory-reader excess ev-0002",
            "\u2705 Verdict: inventory-reader excess ev-0002",
            "\u00a0Verdict\uff1a inventory-reader excess ev-0002",
            "Ver\u200bdict: inventory-reader excess ev-0002",
            "VERDICT: inventory-reader excess EV-0002",
        ):
            with self.subTest(form):
                result = compare.compare("nb-1", CHECKS, form + "\n" + CONTROL)
                self.assertEqual(result["outcome"], "match", result["reasons"])
                self.assertEqual(result["accounts"][0]["references"][0], "ev-0002")

    def test_a_contradiction_in_those_forms_stops(self):
        for form in (
            "- [ ] Verdict: inventory-reader within ev-0001",
            "| Verdict: inventory-reader within ev-0001 |",
            "1000. Verdict: inventory-reader within ev-0001",
            "Verdict\uff1a inventory-reader within ev-0001",
            "Ver\u200bdict: inventory-reader within ev-0001",
        ):
            with self.subTest(form):
                result = compare.compare("nb-1", CHECKS, form + "\n" + RIGHT)
                self.assertEqual(result["outcome"], "stop")
                self.assertIn(
                    "inventory-reader: the answer's verdict lines disagree",
                    result["reasons"],
                )

    def test_a_line_that_starts_with_the_word_in_another_form_cannot_be_read(self):
        for form in (
            "Verdict for inventory-reader: within",
            "Verdict inventory-reader within ev-0001",
        ):
            with self.subTest(form):
                result = compare.compare("nb-1", CHECKS, form + "\n" + RIGHT)
                self.assertEqual(result["outcome"], "stop")
                self.assertIn(
                    "verdict lines that could not be read: 1", result["reasons"]
                )

    def test_a_hedged_value_cannot_be_read(self):
        for value in (
            "excess/within",
            "excess-ish",
            "excess - no wait, within",
            "excess or within",
            "excess, maybe within",
            "excess but see ev-0003",
        ):
            with self.subTest(value):
                answer = f"Verdict: inventory-reader {value} ev-0002\n" + CONTROL
                result = compare.compare("nb-1", CHECKS, answer)
                self.assertEqual(result["outcome"], "stop")
                self.assertIn(
                    "verdict lines that could not be read: 1", result["reasons"]
                )

    def test_references_may_come_in_brackets_or_a_list(self):
        for refs in (
            "(ev-0002, ev-0003)",
            "[ev-0002; ev-0003].",
            "ev-0002 and ev-0003",
        ):
            with self.subTest(refs):
                answer = f"Verdict: inventory-reader excess {refs}\n" + CONTROL
                result = compare.compare("nb-1", CHECKS, answer)
                self.assertEqual(result["outcome"], "match", result["reasons"])
                self.assertEqual(
                    result["accounts"][0]["references"], ["ev-0002", "ev-0003"]
                )

    def test_a_long_run_of_marks_or_spaces_is_read_quickly(self):
        # An answer is at most 8 KiB. The reading has to stay linear in it.
        for line in (
            "#" * 8000 + " Verdict: x",
            "Verdict: inventory-reader excess" + " " * 8000 + "x",
            "Verdict: inventory-reader excess" + ", " * 4000 + "x",
        ):
            with self.subTest(line[:20]):
                started = time.monotonic()
                compare.verdict_lines(line)
                self.assertLess(time.monotonic() - started, 1)

    def test_prose_that_mentions_a_verdict_is_not_a_line(self):
        answer = (
            "The verdict: inventory-reader within, at first sight.\n"
            "Verdicts follow.\n" + RIGHT
        )
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(result["outcome"], "match", result["reasons"])


PROPOSAL = "Proposal: inventory-reader remove 2 ev-0002\n"
KEPT = {
    "account": "inventory-reader",
    "action": "remove",
    "permission": 2,
    "references": ["ev-0002"],
}


class TheProposals(unittest.TestCase):
    """ADR 0043: a proposal line per excess account, after the verdict lines.
    The step keeps what it can read of them and never changes its outcome."""

    def test_a_proposal_after_the_verdicts_is_kept(self):
        self.assertEqual(
            compare.proposal_lines(RIGHT + PROPOSAL),
            ({"inventory-reader": [("remove", 2, ["ev-0002"])]}, 0),
        )
        result = compare.compare("nb-1", CHECKS, RIGHT + PROPOSAL)
        self.assertEqual(result["outcome"], "match")
        self.assertEqual(result["proposals"], [KEPT])
        self.assertEqual(result["unread_proposals"], 0)

    def test_proposals_never_change_the_outcome(self):
        stop = "Verdict: inventory-reader within ev-0003\n" + CONTROL
        for answer in (RIGHT, stop):
            without = compare.compare("nb-1", CHECKS, answer)
            for extra in (PROPOSAL, "Proposal: inventory-reader delete 2\n"):
                with self.subTest(answer=answer, extra=extra):
                    result = compare.compare("nb-1", CHECKS, answer + extra)
                    self.assertEqual(result["outcome"], without["outcome"])
                    self.assertEqual(result["reasons"], without["reasons"])
                    self.assertEqual(result["accounts"], without["accounts"])

    def test_a_proposal_in_another_form_is_unread(self):
        for line in (
            "Proposal: inventory-reader delete 2 ev-0002",
            "Proposal: inventory-reader remove two ev-0002",
            "Proposal: inventory-reader remove 1234567890 ev-0002",
            "Proposal: inventory-reader remove 0 ev-0002",
            "Proposal: remove 2 ev-0002",
            "Proposal: inventory-reader remove 2 ev-0002 and more",
            "Proposal inventory-reader remove 2 ev-0002",
        ):
            with self.subTest(line):
                self.assertEqual(compare.proposal_lines(RIGHT + line), ({}, 1))
                result = compare.compare("nb-1", CHECKS, RIGHT + line)
                self.assertEqual(
                    (result["proposals"], result["unread_proposals"]), ([], 1)
                )

    def test_a_proposal_with_marks_is_read_as_verdict_lines_are(self):
        for line in (
            "**Proposal:** inventory-reader remove 2 ev-0002",
            "- Proposal: inventory-reader remove 2 ev-0002",
            "Proposal\uff1a inventory-reader remove 2 ev-0002",
            "Proposal: `inventory-reader` remove 2 (ev-0002)",
        ):
            with self.subTest(line):
                self.assertEqual(
                    compare.proposal_lines(line),
                    ({"inventory-reader": [("remove", 2, ["ev-0002"])]}, 0),
                )

    def test_an_id_that_folding_made_is_unread(self):
        # The label's folding drops marks and folds compatibility forms. The
        # ID is kept only when the line holds it as written.
        for written in ("2*3", "1`2`", "1\u00b2", "\u2460\u2461", "1\u200b2", "\uff12"):
            with self.subTest(written):
                line = f"Proposal: inventory-reader remove {written} ev-0002"
                self.assertEqual(compare.proposal_lines(line), ({}, 1))

    def test_ids_are_one_to_nine_digits_without_a_leading_zero(self):
        for written, want in (("02", None), ("123456789", 123456789), ("9", 9)):
            with self.subTest(written):
                line = f"Proposal: inventory-reader remove {written} ev-0002"
                if want is None:
                    self.assertEqual(compare.proposal_lines(line), ({}, 1))
                else:
                    found, _ = compare.proposal_lines(line)
                    self.assertEqual(found["inventory-reader"][0][1], want)

    def test_case_and_repeated_references_are_read_as_verdict_lines_are(self):
        line = "Proposal: Inventory-Reader REMOVE 2 EV-0002, ev-0002 and ev-0003"
        self.assertEqual(
            compare.proposal_lines(line),
            ({"inventory-reader": [("remove", 2, ["ev-0002", "ev-0003"])]}, 0),
        )

    def test_each_line_that_cannot_be_read_counts(self):
        answer = RIGHT + "Proposal: x delete 1\nProposal: y remove\nProposal:\n"
        self.assertEqual(compare.proposal_lines(answer), ({}, 3))

    def test_a_long_proposal_line_is_read_quickly(self):
        # An answer is at most 8 KiB. The reading has to stay linear in it.
        for line in (
            "Proposal: inventory-reader remove 2 ev-0002" + " " * 8000 + "x",
            "Proposal: inventory-reader remove 2" + ", ev-0002" * 800 + " x",
            "Proposal: inventory-reader remove " + "1" * 8000,
        ):
            with self.subTest(line[:40]):
                started = time.monotonic()
                compare.proposal_lines(line)
                self.assertLess(time.monotonic() - started, 1)

    def test_a_line_that_only_mentions_a_proposal_is_not_one(self):
        answer = RIGHT + "The proposal: inventory-reader remove 2 ev-0002\n"
        self.assertEqual(compare.proposal_lines(answer), ({}, 0))

    def test_proposals_are_sorted_by_account(self):
        answer = (
            RIGHT
            + "Proposal: inventory-reader-control remove 7 ev-0002\n"
            + "Proposal: inventory-reader remove 3 ev-0002\n"
            + PROPOSAL
        )
        result = compare.compare("nb-1", CHECKS, answer)
        self.assertEqual(
            [(p["account"], p["permission"]) for p in result["proposals"]],
            [
                ("inventory-reader", 3),
                ("inventory-reader", 2),
                ("inventory-reader-control", 7),
            ],
        )


class TheChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = self.tmp / "verdicts.json"

    def test_the_jobs_verdicts_are_read(self):
        self.path.write_text(json.dumps(document()))
        self.assertEqual(compare.load_checks(self.path, "nb-1"), CHECKS)

    def test_checks_for_another_job_stop(self):
        self.path.write_text(json.dumps(document(job="nb-2")))
        with self.assertRaisesRegex(
            compare.Stop, "^the checks' verdicts are for another job$"
        ):
            compare.load_checks(self.path, "nb-1")

    def test_checks_out_of_shape_stop(self):
        good = document()
        many = {f"account-{n:02d}": CHECKS["inventory-reader"] for n in range(21)}
        broken = {
            "not JSON": "{",
            "a list": "[]",
            "an extra key": json.dumps({**good, "note": "within"}),
            "no collected": json.dumps(
                {k: v for k, v in good.items() if k != "collected"}
            ),
            "a collected that is not a time": json.dumps(
                {**good, "collected": "today"}
            ),
            "a job that is not text": json.dumps({**good, "job": 1}),
            "no accounts": json.dumps(document(accounts={})),
            "21 accounts": json.dumps(document(accounts=many)),
            "a value outside the checks'": json.dumps(
                document(accounts=checks(configured="maybe"))
            ),
            "a name outside the pattern": json.dumps(
                document(accounts={"Inventory Reader": CHECKS["inventory-reader"]})
            ),
            "an account with another key": json.dumps(
                document(accounts=checks(why="a permission"))
            ),
            "an account without its observed verdict": json.dumps(
                document(accounts={"inventory-reader": {"configured": "excess"}})
            ),
        }
        for name, text in broken.items():
            self.path.write_text(text)
            with (
                self.subTest(name),
                self.assertRaisesRegex(
                    compare.Stop, "^the checks' verdicts are not in their shape$"
                ),
            ):
                compare.load_checks(self.path, "nb-1")


class TheStep(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.verdicts = self.tmp / "verdicts.json"
        self.verdicts.write_text(json.dumps(document()))
        self.comparison = self.tmp / "comparison.json"
        self.termination = self.tmp / "termination-log"

    def run_compare(self, *args):
        env = {
            "PATH": os.environ["PATH"],
            "AISEC_VERDICTS": str(self.verdicts),
            "AISEC_COMPARISON": str(self.comparison),
            "AISEC_TERMINATION": str(self.termination),
        }
        process = subprocess.run(
            [sys.executable, "-I", str(HERE / "compare.py"), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False,
        )
        return process.returncode, process.stdout, process.stderr

    def test_main_writes_the_comparison_and_the_termination_message(self):
        code, _, err = self.run_compare("nb-1", RIGHT)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(self.comparison.read_text())["outcome"], "match")
        self.assertEqual(self.termination.read_text(), "match")
        code, _, err = self.run_compare(
            "nb-1", "Verdict: inventory-reader within ev-0003\n" + CONTROL
        )
        self.assertEqual(code, 1, err)
        self.assertEqual(json.loads(self.comparison.read_text())["outcome"], "stop")
        self.assertTrue(
            self.termination.read_text().startswith("stop: inventory-reader: "),
            self.termination.read_text(),
        )

    def test_the_log_has_a_row_per_account_and_the_outcome_last(self):
        code, out, err = self.run_compare("nb-1", RIGHT)
        self.assertEqual(code, 0, err)
        rows = [line.split() for line in out.splitlines()]
        self.assertIn(
            [
                "inventory-reader",
                "excess",
                "ev-0002,ev-0003",
                "excess",
                "excess",
                "match",
            ],
            rows,
        )
        self.assertIn(
            [
                "inventory-reader-control",
                "within",
                "ev-0003",
                "within",
                "within",
                "match",
            ],
            rows,
        )
        self.assertEqual(out.splitlines()[-1], "match")

    def test_no_checks_for_the_job_stops(self):
        self.verdicts.unlink()
        code, out, err = self.run_compare("nb-1", RIGHT)
        self.assertEqual(code, 1, err)
        written = json.loads(self.comparison.read_text())
        self.assertEqual(
            (written["outcome"], written["reasons"], written["accounts"]),
            ("stop", ["no checks' verdicts for this job"], []),
        )
        self.assertEqual(out.splitlines()[-1], "stop: no checks' verdicts for this job")

    def test_the_step_writes_proposals_for_a_stop_too(self):
        self.verdicts.unlink()
        code, _, err = self.run_compare(
            "nb-1", RIGHT + PROPOSAL + "Proposal: x delete 1\n"
        )
        self.assertEqual(code, 1, err)
        written = json.loads(self.comparison.read_text())
        self.assertEqual(written["outcome"], "stop")
        self.assertEqual(
            (written["proposals"], written["unread_proposals"]), ([KEPT], 1)
        )

    def test_an_escape_sequence_reaches_neither_the_log_nor_the_output(self):
        answer = "Verdict: inventory-reader\x1b[2J excess ev-0002\n" + CONTROL
        code, out, err = self.run_compare("nb-1", answer)
        self.assertEqual(code, 1, err)
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\x1b", self.comparison.read_text())
        self.assertNotIn("\\u001b", self.comparison.read_text())
        self.assertNotIn("\x1b", self.termination.read_text())

    def test_the_usage_needs_a_job_and_an_answer(self):
        for args in ((), ("nb-1",), ("Not_A_Job", RIGHT)):
            with self.subTest(args):
                code, _, _ = self.run_compare(*args)
                self.assertEqual(code, 2)
                self.assertFalse(self.comparison.exists())


class TheNetboxTask(unittest.TestCase):
    """The task the operator sends with a NetBox job, collectors/netbox/task.txt."""

    def test_the_netbox_task_asks_for_the_lines_the_comparison_reads(self):
        text = TASK.read_text(encoding="utf-8")
        self.assertIn("Verdict:", text)
        for value in compare.VALUES:
            self.assertIn(value, text)
        # Its examples are lines the comparison reads, for accounts no
        # contract has, so an answer that copies one stops.
        lines, unread = compare.verdict_lines(text)
        self.assertEqual(unread, 0)
        self.assertEqual(set(lines), {"some-account", "other-account"})
        for found in lines.values():
            self.assertIn(found[0][0], compare.VALUES)

    def test_the_netbox_task_passes_the_workers_refusals(self):
        spec = importlib.util.spec_from_file_location("agent_job", JOB_PROGRAM)
        agent_job = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent_job)
        text = TASK.read_text(encoding="utf-8")
        line = {
            "job": "nb-1",
            "token": "0" * 64,
            "task": text,
            "max_turns": 8,
            "seconds": 900,
        }
        self.assertEqual(agent_job.parse_job(json.dumps(line))["task"], text)
        # The operator passes it as one shell argument, and it holds no path.
        self.assertNotIn('"', text)
        self.assertNotIn("/", text)


if __name__ == "__main__":
    unittest.main()
