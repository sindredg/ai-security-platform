"""A job's record from a workflow, audit lines, and a collection.

The workflows here have the shape `argo get -o json` gives, cut to the fields
record.py reads.
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import record

JOB = "nb-test-1"
CHECKS = {
    "inventory-reader": ["excess", "excess"],
    "inventory-reader-control": ["within", "within"],
}


def request(name, arguments):
    return {
        "role": "assistant",
        "type": "toolRequest",
        "text": json.dumps({"name": name, "arguments": arguments}),
    }


def audit(job, ref, decision="allowed", ts="2026-10-25T23:11:19Z", size=1471):
    return json.dumps(
        {
            "ts": ts,
            "event": "call",
            "decision": decision,
            "job": job,
            "caller": "10.40.0.36",
            "tool": "get_evidence",
            "args_sha256": record.digest({"reference": ref}),
            "reason": None if decision == "allowed" else "nothing by that reference",
            "result_bytes": size if decision == "allowed" else None,
        }
    )


def workflow(transcript=None, comparison=True, status="completed", phase="Succeeded"):
    result = {
        "job": JOB,
        "status": status,
        "seconds": 357.4,
        "tool_calls": 2,
        "tool_errors": 0,
        "slot_erased": True,
        "stderr_tail": "Traceback from /home/someone",
        "input_tokens": 9119,
        "output_tokens": 933,
        "answer": "Verdict: inventory-reader excess ev-0003",
    }
    if transcript is not None:
        result["transcript"] = transcript
    nodes = {
        "a": {
            "type": "Pod",
            "templateName": "dispatch",
            "displayName": "dispatch",
            "phase": "Succeeded",
            "startedAt": "2026-10-25T23:09:34Z",
            "outputs": {
                "parameters": [{"name": "result", "value": json.dumps(result)}]
            },
        },
        "b": {"type": "StepGroup", "displayName": "[0]", "phase": "Succeeded"},
    }
    if comparison:
        rows = [
            {
                "account": a,
                "model": c,
                "references": ["ev-0003"],
                "configured": c,
                "observed": o,
                "outcome": "match",
            }
            for a, (c, o) in CHECKS.items()
        ]
        compared = {"job": JOB, "outcome": "match", "reasons": [], "accounts": rows}
        nodes["c"] = {
            "type": "Pod",
            "templateName": "compare",
            "displayName": "compare",
            "phase": "Succeeded",
            "startedAt": "2026-10-25T23:15:48Z",
            "outputs": {
                "parameters": [{"name": "comparison", "value": json.dumps(compared)}]
            },
        }
    return {
        "metadata": {"name": JOB},
        "spec": {
            "arguments": {
                "parameters": [
                    {"name": "target", "value": "netbox"},
                    {"name": "seconds", "value": "1200"},
                    {"name": "max-turns", "value": "8"},
                    {"name": "task", "value": "a long task"},
                ]
            }
        },
        "status": {
            "phase": phase,
            "startedAt": "2026-10-25T23:09:34Z",
            "finishedAt": "2026-10-25T23:16:07Z",
            "nodes": nodes,
        },
    }


COLLECTED = (
    f"{JOB}: case control-only\n"
    f"{JOB}: ev-0001 ev-0002 ev-0003, visible to the tool service after 54 s\n"
    "inventory-reader:excess/excess inventory-reader-control:within/within\n"
)


class Build(unittest.TestCase):
    def test_a_compared_job_keeps_the_rows_the_steps_and_the_answer(self):
        rec = record.build(workflow([]), [], COLLECTED)
        self.assertEqual(rec["comparison"]["outcome"], "match")
        self.assertEqual(rec["checks"], CHECKS)
        self.assertEqual(rec["case"], "control-only")
        self.assertEqual([s["step"] for s in rec["steps"]], ["dispatch", "compare"])
        self.assertEqual(rec["steps"][1]["started"], "2026-10-25T23:15:48Z")
        self.assertEqual(rec["limits"], {"seconds": 1200, "turns": 8})
        self.assertEqual(rec["answer"], "Verdict: inventory-reader excess ev-0003")

    def test_the_record_keeps_no_transcript_task_or_error_output(self):
        rec = record.build(
            workflow([request("tools__get_evidence", {"reference": "ev-0001"})]), []
        )
        text = json.dumps(rec)
        self.assertNotIn("transcript", text)
        self.assertNotIn("a long task", text)
        self.assertNotIn("Traceback", text)
        self.assertNotIn(record.digest({"reference": "ev-0001"}), text)

    def test_calls_follow_the_transcript_with_the_services_decision(self):
        asked = [
            request("tools__get_evidence", {"reference": "ev-0002"}),
            request("tools__get_evidence", {"reference": "ev-0001"}),
        ]
        lines = [
            audit(JOB, "ev-0001", ts="2026-10-25T23:11:19Z"),
            audit(JOB, "ev-0002", ts="2026-10-25T23:11:20Z", size=492),
        ]
        calls = record.build(workflow(asked), lines)["calls"]
        self.assertEqual([c["argument"] for c in calls], ["ev-0002", "ev-0001"])
        self.assertEqual([c["bytes"] for c in calls], [492, 1471])
        self.assertEqual({c["decision"] for c in calls}, {"allowed"})

    def test_a_call_to_one_of_gooses_own_tools_is_kept_without_an_audit_line(self):
        asked = [request("load_skill", {"name": "goose-doc-guide"})]
        (call,) = record.build(workflow(asked), [])["calls"]
        self.assertEqual(call["decision"], "goose")
        self.assertEqual(call["tool"], "load_skill")
        self.assertEqual(call["argument"], '{"name":"goose-doc-guide"}')
        self.assertIsNone(call["at"])

    def test_a_request_the_audit_log_lacks_is_kept_as_missing(self):
        asked = [request("tools__get_evidence", {"reference": "ev-0001"})]
        (call,) = record.build(workflow(asked), [audit("other-job", "ev-0001")])[
            "calls"
        ]
        self.assertEqual(call["decision"], "missing")

    def test_audit_lines_without_a_transcript_are_the_calls(self):
        lines = [
            audit(JOB, "ev-0001"),
            audit(JOB, "ev-0009", decision="refused"),
            audit("other", "ev-0002"),
        ]
        calls = record.build(workflow(None), lines)["calls"]
        self.assertEqual(
            [(c["argument"], c["decision"]) for c in calls],
            [("ev-0001", "allowed"), ("ev-0009", "refused")],
        )

    def test_an_unknown_argument_hash_is_shortened(self):
        line = json.loads(audit(JOB, "ev-0001"))
        line["args_sha256"] = "ab" * 32
        (call,) = record.build(workflow(None), [json.dumps(line)])["calls"]
        self.assertEqual(call["argument"], "sha256 abababababab")

    def test_checks_that_differ_from_the_compared_ones_stop_the_record(self):
        changed = COLLECTED.replace("within/within", "within/excess")
        with self.assertRaises(ValueError):
            record.build(workflow([]), [], changed)

    def test_the_collection_gives_the_checks_when_nothing_was_compared(self):
        rec = record.build(
            workflow(None, comparison=False, status="timeout", phase="Failed"),
            [],
            COLLECTED,
        )
        self.assertEqual(rec["checks"], CHECKS)
        self.assertIsNone(rec["comparison"])
        self.assertEqual(rec["result"]["status"], "timeout")

    def test_no_result_and_no_answer_parameter_means_the_answer_was_not_kept(self):
        flow = workflow(None)
        flow["status"]["nodes"] = {}
        self.assertIsNone(record.build(flow, [])["answer"])


class Add(unittest.TestCase):
    def test_a_rebuilt_record_keeps_its_note_and_jobs_stay_in_order(self):
        early = {"job": "a", "started": "2026-10-25T10:00:00Z", "finished": None}
        old = {"job": JOB, "started": "2026-10-25T23:09:34Z", "note": "Kept."}
        run_set = record.add(
            {"title": "t", "jobs": [old, early]},
            {"job": JOB, "started": "2026-10-25T23:09:34Z"},
        )
        self.assertEqual([j["job"] for j in run_set["jobs"]], ["a", JOB])
        self.assertEqual(run_set["jobs"][1]["note"], "Kept.")


class Main(unittest.TestCase):
    def test_nothing_is_written_when_the_checks_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "set.json").write_text('{"title": "t", "jobs": []}\n')
            (folder / "wf.json").write_text(json.dumps(workflow([])))
            (folder / "audit.jsonl").write_text("")
            (folder / "collected.txt").write_text(
                COLLECTED.replace("excess/excess", "excess/within")
            )
            argv = [
                "record.py",
                *(
                    str(folder / n)
                    for n in ("set.json", "wf.json", "audit.jsonl", "collected.txt")
                ),
            ]
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(record.main(argv), 1)
            self.assertEqual(
                (folder / "set.json").read_text(), '{"title": "t", "jobs": []}\n'
            )


if __name__ == "__main__":
    unittest.main()
