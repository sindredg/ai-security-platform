"""The fixture's question and evidence, where more than one program carries them.

Each copy belongs to a program that runs on its own: the tool service serves
ev-0001 to dispatched jobs, the fixture tool serves it to the agent without the
service, and measure.py answers the model server's tool calls with it. The
model comparison is about the job, so a copy that drifts makes it measure
something else. The system text is one file, read by all of them.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

AGENT = Path(__file__).resolve().parents[2]
REPO = AGENT.parents[1]
sys.dont_write_bytecode = True  # the checkout is mounted read-only in the pipeline


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


measure = load("measure", REPO / "worker/model-server/measure.py")
evidence_tool = load("evidence_tool", AGENT / "fixture/evidence_tool.py")
check_answer = load("check_answer", AGENT / "fixture/check_answer.py")
SERVICE = json.loads(
    (REPO / "platform/tool-service/evidence/synthetic/ev-0001.json").read_text()
)
QUESTION = (AGENT / "fixture/question.txt").read_text().strip()
FIRST = measure.CASES[0]


class Copies(unittest.TestCase):
    def test_measure_reads_the_system_text_the_job_installs(self):
        install = (AGENT / "install-job.sh").read_text()
        self.assertIn('"$here/system.txt" /usr/local/lib/aisec/job/', install)
        self.assertEqual(measure.SYSTEM_FILE, "/usr/local/lib/aisec/job/system.txt")
        self.assertFalse(hasattr(measure, "SYSTEM"))

    def test_the_first_case_is_the_fixture_question(self):
        self.assertEqual(FIRST["case"], "confirmed")
        self.assertEqual(FIRST["question"], QUESTION)
        self.assertEqual(FIRST["references"], ["ev-0001"])

    def test_every_copy_of_ev_0001_is_the_tool_services(self):
        self.assertEqual(measure.EVIDENCE["ev-0001"], SERVICE)
        self.assertEqual(evidence_tool.EVIDENCE, {"ev-0001": SERVICE})

    def test_the_expected_answer_follows_from_the_evidence(self):
        excess = sorted(
            set(SERVICE["granted_object_types"]) - set(SERVICE["contract_object_types"])
        )
        self.assertEqual(FIRST["excess"], excess)
        self.assertEqual(sorted(check_answer.EXCESS), excess)
        self.assertEqual(check_answer.WANTED_CALL[1], {"reference": "ev-0001"})


if __name__ == "__main__":
    unittest.main()
