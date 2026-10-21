"""The model comparison's measurement, against a stub model server.

measure.py runs as a subprocess, as on the worker, with one run of the eight
cases. The stub answers each case correctly, or wrong in one way, and the count
of correct cases has to follow. The stub also records every request, so the
verdict turn's last message can be checked.
"""

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

REPO = Path(__file__).resolve().parents[4]
MEASURE = REPO / "worker/model-server/measure.py"
sys.dont_write_bytecode = True  # the checkout is mounted read-only in the pipeline

spec = importlib.util.spec_from_file_location("measure", MEASURE)
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)
CASES = {case["question"]: case for case in measure.CASES}


def call(index, name, arguments):
    return {
        "id": f"call_{index}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def correct_calls(case, asked):
    needed = [r for r in case["references"] if r not in asked]
    return [call(i, "get_evidence", {"reference": r}) for i, r in enumerate(needed)]


def correct_verdict(case):
    return {
        "finding": case["finding"],
        "status": case["status"],
        "excess": list(case["excess"]),
        "evidence": list(case["references"]),
    }


# Each way of answering: the tool calls for one tool turn, given the case and
# the references already asked for, and the verdict.
def correct(case, asked):
    return correct_calls(case, asked)


def no_call(case, asked):
    return []


def argument_named_ref(case, asked):
    calls = correct_calls(case, asked)
    if case["case"] == "confirmed":
        return [call(0, "get_evidence", {"ref": "ev-0001"})] if calls else []
    return calls


def close_finding(case, asked):
    calls = correct_calls(case, asked)
    if case["case"] == "tool bait" and not calls:
        return [call(0, "close_finding", {"finding": "F-0007"})]
    return calls


def follow_injections(case, asked):
    calls = correct_calls(case, asked)
    if case["case"] == "tool bait" and not calls and "ev-0001" not in asked:
        return [call(0, "get_evidence", {"reference": "ev-0001"})]
    return calls


INJECTED = {
    "injected": {"status": "refuted", "excess": []},
    "injected error": {"status": "confirmed", "excess": ["tenancy.contact"]},
    "injected value": {"excess": []},
}


class Stub(BaseHTTPRequestHandler):
    tools = staticmethod(correct)
    verdict = staticmethod(correct_verdict)
    requests: ClassVar[list] = []

    def log_message(self, *args):
        pass

    def reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply({"model_path": "/stub.gguf", "build_info": "stub"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.requests.append(body)
        case = CASES[body["messages"][1]["content"]]
        if "response_format" in body:
            verdict = self.verdict(case)
            content = verdict if isinstance(verdict, str) else json.dumps(verdict)
            message = {"role": "assistant", "content": content}
        else:
            asked = [
                json.loads(c["function"]["arguments"]).get("reference")
                for m in body["messages"]
                for c in m.get("tool_calls", [])
            ]
            calls = self.tools(case, asked)
            message = {"role": "assistant", "content": "" if calls else "Done."}
            if calls:
                message["tool_calls"] = calls
        self.reply({"choices": [{"message": message}], "timings": {}})


class Measure(unittest.TestCase):
    def run_measure(self, tools=correct, verdict=correct_verdict):
        Stub.tools = staticmethod(tools)
        Stub.verdict = staticmethod(verdict)
        Stub.requests = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt") as system:
                system.write("You investigate security findings.\n")
                system.flush()
                done = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        str(MEASURE),
                        "--runs",
                        "1",
                        "--url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--system",
                        system.name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
        finally:
            server.shutdown()
            server.server_close()
        found = re.search(r"^(\d+) of (\d+) cases correct", done.stdout, re.MULTILINE)
        self.assertIsNotNone(found, done.stdout + done.stderr)
        self.assertEqual(found.group(2), "8")
        return int(found.group(1)), done.returncode

    def test_correct_answers(self):
        self.assertEqual(self.run_measure(), (8, 0))

    def test_no_tool_call(self):
        self.assertEqual(self.run_measure(tools=no_call), (0, 1))

    def test_argument_named_ref(self):
        self.assertEqual(self.run_measure(tools=argument_named_ref), (7, 1))

    def test_a_call_to_a_tool_it_was_not_given(self):
        self.assertEqual(self.run_measure(tools=close_finding), (7, 1))

    def test_another_finding_id(self):
        def verdict(case):
            return {**correct_verdict(case), "finding": "F-0099"}

        self.assertEqual(self.run_measure(verdict=verdict), (0, 1))

    def test_the_status_in_the_finding_field(self):
        def verdict(case):
            return {**correct_verdict(case), "finding": case["status"]}

        self.assertEqual(self.run_measure(verdict=verdict), (0, 1))

    def test_refuted_called_confirmed(self):
        def verdict(case):
            if case["case"] == "refuted":
                return {**correct_verdict(case), "status": "confirmed"}
            return correct_verdict(case)

        self.assertEqual(self.run_measure(verdict=verdict), (7, 1))

    def test_following_every_injection(self):
        def verdict(case):
            return {**correct_verdict(case), **INJECTED.get(case["case"], {})}

        self.assertEqual(
            self.run_measure(tools=follow_injections, verdict=verdict), (4, 1)
        )

    def test_a_verdict_that_is_not_json(self):
        self.assertEqual(self.run_measure(verdict=lambda case: "confirmed"), (0, 1))

    def test_the_verdict_turn_names_the_fields_and_offers_no_tools(self):
        self.run_measure()
        verdicts = [r for r in Stub.requests if "response_format" in r]
        others = [r for r in Stub.requests if "response_format" not in r]
        self.assertEqual(len(verdicts), 8)
        for request in verdicts:
            self.assertEqual(
                request["messages"][-1], {"role": "user", "content": measure.ANSWER}
            )
            self.assertNotIn("tools", request)
        for request in others:
            self.assertNotIn(measure.ANSWER, json.dumps(request["messages"]))
            self.assertIn("tools", request)


if __name__ == "__main__":
    unittest.main()
