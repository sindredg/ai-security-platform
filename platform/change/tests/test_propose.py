"""The propose command (ADR 0043, ADR 0045).

main() runs in the test's process with its paths in a temporary directory,
kubectl a stub that prints a stored workflow, and the rehearsal and the live
lookup of a permission's name replaced. The policy is the real one.
"""

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

import propose

MARKER = "MARKER-the-model-wrote-this"
TENANT_A = {"tenant__slug": "tenant-a"}
TYPES = ["dcim.device", "ipam.ipaddress"]
CONTRACT = {
    "accounts": ["inventory-reader", "inventory-reader-control"],
    "viewpoint": "10.50.0.36",
    "grants": [
        {"object_type": t, "action": "view", "constraints": TENANT_A} for t in TYPES
    ],
    "reads": [],
    "denials": [],
}


def permission(id_, name, constraints):
    return {
        "id": id_,
        "name": name,
        "object_types": TYPES,
        "actions": ["view"],
        "constraints": constraints,
        "via": "user",
    }


CONFIGURED = {
    "check": "configured",
    "accounts": {
        "inventory-reader": {
            "verdict": "excess",
            "reasons": [],
            "permissions": [
                permission(1, "inventory-reader: tenant-a inventory", TENANT_A),
                permission(2, "inventory-reader: inventory", None),
            ],
        },
        "inventory-reader-control": {
            "verdict": "within",
            "reasons": [],
            "permissions": [
                permission(3, "inventory-reader-control: tenant-a inventory", TENANT_A)
            ],
        },
    },
}


def row(account, verdict):
    return {
        "account": account,
        "model": verdict,
        "references": ["ev-0002", "ev-0003"],
        "configured": verdict,
        "observed": verdict,
        "outcome": "match",
    }


def comparison(job="nb-1", outcome="match", proposals=None):
    return {
        "job": job,
        "outcome": outcome,
        "reasons": [],
        "accounts": [
            row("inventory-reader", "excess"),
            row("inventory-reader-control", "within"),
        ],
        "proposals": [
            {
                "account": "inventory-reader",
                "action": "remove",
                "permission": 2,
                "references": ["ev-0002"],
            }
        ]
        if proposals is None
        else proposals,
        "unread_proposals": 0,
    }


def workflow(job="nb-1", compared=None, entrypoint=None, compare_phase="Succeeded"):
    spec = {"workflowTemplateRef": {"name": "investigate"}, "arguments": {}}
    if entrypoint is not None:
        spec["entrypoint"] = entrypoint
    answer = f"{MARKER}\nVerdict: inventory-reader excess ev-0002\n"
    return {
        "metadata": {"name": job},
        "spec": spec,
        "status": {
            "phase": "Succeeded" if compare_phase == "Succeeded" else "Failed",
            "nodes": {
                "a": {
                    "templateName": "dispatch",
                    "type": "Pod",
                    "phase": "Succeeded",
                    "outputs": {"parameters": [{"name": "answer", "value": answer}]},
                },
                "b": {
                    "templateName": "compare",
                    "type": "Pod",
                    "phase": compare_phase,
                    "outputs": {
                        "parameters": [
                            {
                                "name": "comparison",
                                "value": json.dumps(compared or comparison(job)),
                            }
                        ]
                    },
                },
            },
        },
    }


PASSED = {
    "reset": "a" * 64,
    "applied": [{"permission": "inventory-reader: inventory", "id": 22, "users": []}],
    "verdicts": {
        "inventory-reader": {"configured": "within", "observed": "within"},
        "inventory-reader-control": {"configured": "within", "observed": "within"},
    },
    "passed": True,
    "reason": None,
}


class WorkflowChecked(unittest.TestCase):
    def test_a_workflow_from_another_entrypoint_is_refused(self):
        for entrypoint in ("dispatch", "compare"):
            with (
                self.subTest(entrypoint),
                self.assertRaisesRegex(propose.Refused, "entrypoint"),
            ):
                propose.workflow_checked(workflow(entrypoint=entrypoint), "nb-1")
        self.assertEqual(
            propose.workflow_checked(workflow(entrypoint="investigate"), "nb-1")["job"],
            "nb-1",
        )

    def test_a_failed_compare_node_is_refused(self):
        with self.assertRaisesRegex(propose.Refused, "did not succeed"):
            propose.workflow_checked(workflow(compare_phase="Failed"), "nb-1")

    def test_a_workflow_without_one_compare_node_is_refused(self):
        found = workflow()
        del found["status"]["nodes"]["b"]
        with self.assertRaisesRegex(propose.Refused, "0 comparisons, one expected"):
            propose.workflow_checked(found, "nb-1")

    def test_a_comparison_for_another_job_is_refused(self):
        with self.assertRaisesRegex(propose.Refused, "another job"):
            propose.workflow_checked(workflow(compared=comparison(job="nb-2")), "nb-1")

    def test_a_stop_is_refused(self):
        with self.assertRaisesRegex(propose.Refused, "stop"):
            propose.workflow_checked(
                workflow(compared=comparison(outcome="stop")), "nb-1"
            )

    def test_another_template_is_refused(self):
        found = workflow()
        found["spec"]["workflowTemplateRef"]["name"] = "other"
        with self.assertRaisesRegex(propose.Refused, "investigate"):
            propose.workflow_checked(found, "nb-1")


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        job = self.state / "nb-1"
        job.mkdir(parents=True)
        header = {"job": "nb-1", "collected": "2026-10-27T10:00:00Z"}
        files = {
            "configured.json": CONFIGURED,
            "ev-0001.json": {"reference": "ev-0001", **header, **CONTRACT},
            "verdicts.json": {
                "inventory-reader": {"configured": "excess", "observed": "excess"},
                "inventory-reader-control": {
                    "configured": "within",
                    "observed": "within",
                },
            },
        }
        for name, document in files.items():
            (job / name).write_text(json.dumps(document))
        (self.tmp / "contract.json").write_text(json.dumps(CONTRACT))
        other = dict(CONTRACT, accounts=["inventory-reader-control"])
        (self.tmp / "cases.json").write_text(
            json.dumps({"cases": {"control-only": {"contract": other}}})
        )
        self.workflow_file = self.tmp / "workflow.json"
        self.workflow_file.write_text(json.dumps(workflow()))
        kubectl = self.tmp / "kubectl"
        kubectl.write_text(f"#!/bin/sh\ncat {self.workflow_file}\n")
        kubectl.chmod(0o755)
        self.rehearsed = []
        self.result = PASSED

        def fake_rehearse(changes, contract):
            self.rehearsed.append((changes, contract))
            return self.result

        for patch in (
            mock.patch.object(propose, "STATE", self.state),
            mock.patch.object(propose, "PROPOSALS", self.tmp / "proposals"),
            mock.patch.object(propose, "CONTRACT", self.tmp / "contract.json"),
            mock.patch.object(propose, "CASES", self.tmp / "cases.json"),
            mock.patch.object(propose, "KUBECTL", [str(kubectl)]),
            mock.patch.object(propose.rehearse, "rehearse", fake_rehearse),
            mock.patch.object(
                propose,
                "permission_name",
                lambda i: {7: "aisec-deliver: assignments"}[i],
            ),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def bundle(self):
        return json.loads(
            (self.tmp / "proposals" / "nb-1" / "proposal.json").read_text()
        )

    def test_an_allowed_fix_writes_the_bundle(self):
        self.assertEqual(propose.main(["propose-netbox-fix", "nb-1"]), 0)
        bundle = self.bundle()
        self.assertEqual(
            (bundle["job"], bundle["case"], bundle["collected"], bundle["source"]),
            ("nb-1", "seed", "2026-10-27T10:00:00Z", "model"),
        )
        self.assertTrue(bundle["policy"]["allowed"])
        self.assertEqual(bundle["rehearsal"], PASSED)
        self.assertEqual(
            self.rehearsed[0][0],
            [
                {
                    "account": "inventory-reader",
                    "permission_id": 2,
                    "permission": "inventory-reader: inventory",
                }
            ],
        )
        body = (self.tmp / "proposals" / "nb-1" / "pr-body.md").read_text()
        self.assertIn("inventory-reader: inventory", body)
        self.assertIn("nb-1", body)

    def test_a_refused_fix_still_shows_its_rehearsal(self):
        compared = comparison(
            proposals=[
                {
                    "account": "inventory-reader",
                    "action": "remove",
                    "permission": 1,
                    "references": [],
                }
            ]
        )
        self.workflow_file.write_text(json.dumps(workflow(compared=compared)))
        self.result = dict(PASSED, passed=False)
        self.assertEqual(propose.main(["propose-netbox-fix", "nb-1"]), 1)
        bundle = self.bundle()
        self.assertFalse(bundle["policy"]["allowed"])
        self.assertEqual(len(self.rehearsed), 1)
        self.assertEqual(
            self.rehearsed[0][0][0]["permission"],
            "inventory-reader: tenant-a inventory",
        )
        self.assertIn("rehearsal", bundle)
        self.assertFalse((self.tmp / "proposals" / "nb-1" / "pr-body.md").exists())

    def test_the_pr_body_holds_no_answer_text(self):
        self.assertEqual(propose.main(["propose-netbox-fix", "nb-1"]), 0)
        for name in ("pr-body.md", "proposal.json"):
            text = (self.tmp / "proposals" / "nb-1" / name).read_text()
            self.assertNotIn(MARKER, text)

    def test_operator_proposals_are_marked(self):
        operator = self.tmp / "operator.json"
        operator.write_text(
            json.dumps(
                [
                    {
                        "account": "inventory-reader",
                        "action": "remove",
                        "permission": 2,
                        "references": ["ev-0002"],
                    },
                    {
                        "account": "aisec-deliver",
                        "action": "remove",
                        "permission": 7,
                        "references": [],
                    },
                ]
            )
        )
        code = propose.main(
            ["propose-netbox-fix", "nb-1", "--proposals", str(operator)]
        )
        self.assertEqual(code, 1)
        bundle = self.bundle()
        self.assertEqual(bundle["source"], "operator")
        self.assertIn(
            "aisec-deliver: not an account the checks name", bundle["policy"]["reasons"]
        )
        names = sorted(change["permission"] for change in self.rehearsed[0][0])
        self.assertEqual(
            names, ["aisec-deliver: assignments", "inventory-reader: inventory"]
        )

    def test_the_case_is_named_from_the_case_file(self):
        other = dict(CONTRACT, accounts=["inventory-reader-control"])
        ev = self.state / "nb-1" / "ev-0001.json"
        document = json.loads(ev.read_text())
        ev.write_text(json.dumps({**document, **other}))
        propose.main(["propose-netbox-fix", "nb-1"])
        self.assertEqual(self.bundle()["case"], "control-only")

    def test_a_job_proposed_once_is_not_proposed_again(self):
        self.assertEqual(propose.main(["propose-netbox-fix", "nb-1"]), 0)
        self.assertEqual(propose.main(["propose-netbox-fix", "nb-1"]), 1)

    def test_the_usage_needs_a_job(self):
        for argv in (["p"], ["p", "Not_A_Job"], ["p", "nb-1", "--proposals"]):
            with self.subTest(argv):
                self.assertEqual(propose.main(argv), 2)


if __name__ == "__main__":
    unittest.main()
