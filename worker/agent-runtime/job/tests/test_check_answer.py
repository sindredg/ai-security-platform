"""The fixture check, check_answer.py, on transcripts written by the test.

The verdict and the excess types are read from the two lines the system text
asks every answer to end with (#149).
"""

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

AGENT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True  # the checkout is mounted read-only in the pipeline

spec = importlib.util.spec_from_file_location(
    "check_answer", AGENT / "fixture/check_answer.py"
)
check_answer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_answer)

GOOD = (
    "The token can list tenancy.contact and circuits.circuit, which the "
    "consumer's contract does not name.\n"
    "Status: confirmed\n"
    "Excess: tenancy.contact, circuits.circuit"
)


def transcript(answer):
    return {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "question"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "toolRequest",
                        "toolCall": {
                            "value": {
                                "name": "evidence__get_evidence",
                                "arguments": {"reference": "ev-0001"},
                            }
                        },
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "toolResponse",
                        "toolResult": {"status": "success", "value": {}},
                    }
                ],
            },
            {"role": "assistant", "content": [{"type": "text", "text": answer}]},
        ],
        "metadata": {"status": "completed"},
    }


def run(answer):
    """main() on one transcript. Returns (exit code, the printed line)."""
    stdin, out = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(json.dumps(transcript(answer)))
    try:
        with redirect_stdout(out):
            code = check_answer.main()
    finally:
        sys.stdin = stdin
    return code, json.loads(out.getvalue())


class TheVerdict(unittest.TestCase):
    def test_a_confirmed_answer_with_both_types_passes(self):
        code, line = run(GOOD)
        self.assertEqual((code, line["ok"]), (0, True), line["reason"])

    def test_markdown_case_and_a_full_stop_around_the_lines_pass(self):
        answer = (
            "Confirmed.\n\n**Status:** Confirmed.\n"
            "**excess:** `circuits.circuit`, `tenancy.contact`\n"
        )
        code, line = run(answer)
        self.assertEqual(code, 0, line["reason"])

    def test_each_wrong_answer_fails(self):
        wrong = {
            # Run 2 of the model comparison on 2026-10-21, which the old check
            # passed: both names, and a verdict of not confirmed.
            "the comparison's run 2": (
                "The token can list tenancy.contact and circuits.circuit. "
                "However, the evidence does not provide the consumer's required "
                "record types. Therefore, the finding cannot be confirmed "
                "without additional information.\nResult: Not confirmed."
            ),
            "no lines at all": "tenancy.contact and circuits.circuit. Confirmed.",
            "not confirmed": GOOD.replace("Status: confirmed", "Status: not confirmed"),
            "refuted": GOOD.replace("Status: confirmed", "Status: refuted"),
            "inconclusive": GOOD.replace("Status: confirmed", "Status: inconclusive"),
            "two status lines": GOOD + "\nStatus: refuted",
            "no excess line": GOOD.rsplit("\n", 1)[0],
            "one type missing": GOOD.replace(", circuits.circuit", ""),
            # Run 3 of the same comparison named a type the contract holds.
            "a type the contract holds": GOOD + ", ipam.prefix",
            "none in excess": GOOD.replace("tenancy.contact, circuits.circuit", "none"),
            "the lines in an earlier message only": "",
        }
        for name, answer in wrong.items():
            with self.subTest(name):
                code, line = run(answer)
                self.assertEqual((code, line["ok"]), (1, False))

    def test_the_lines_are_read_from_the_last_message_only(self):
        # The tool's answer, or an earlier message, may hold the same words.
        run_with_earlier = transcript("No lines here.")
        run_with_earlier["messages"].insert(
            1, {"role": "assistant", "content": [{"type": "text", "text": GOOD}]}
        )
        stdin, out = sys.stdin, io.StringIO()
        sys.stdin = io.StringIO(json.dumps(run_with_earlier))
        try:
            with redirect_stdout(out):
                code = check_answer.main()
        finally:
            sys.stdin = stdin
        self.assertEqual(code, 1)

    def test_the_system_text_asks_for_the_two_lines(self):
        system = (AGENT / "system.txt").read_text()
        self.assertIn("Status:", system)
        self.assertIn("Excess:", system)
        for word in check_answer.STATUSES:
            self.assertIn(word, system)


if __name__ == "__main__":
    unittest.main()
