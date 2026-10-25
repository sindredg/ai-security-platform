"""The documents the collect command writes pass the tool's schemas.

The command is in collectors/netbox and runs on the host's Python, with the
standard library only, so its own tests cannot check the schemas. This test
builds the three documents with the command's functions, from the reports its
tests use, and hands them to the tool as the pod would read them.
"""

import importlib.util
import json
from pathlib import Path

import pytest
from conftest import POLICY
from test_evidence import configmap_volume

from aisec_tools.jobs import Job
from aisec_tools.tools.evidence import make_get_evidence

COLLECTORS = Path(__file__).parent.parent.parent / "collectors" / "netbox"
REPORTS = json.loads((COLLECTORS / "tests" / "reports.json").read_text())
CASES = json.loads((COLLECTORS / "cases.json").read_text())["cases"]


@pytest.fixture(scope="module")
def command():
    spec = importlib.util.spec_from_file_location(
        "collect_evidence", COLLECTORS / "collect_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def documents(command, job, collected="2026-10-25T08:00:00Z"):
    return {
        "ev-0001": command.facts_contract(REPORTS["contract"], job, collected),
        "ev-0002": command.facts_configured(REPORTS["configured"], job, collected),
        "ev-0003": command.facts_observed(REPORTS["observed"], job, collected),
    }


def test_every_collected_document_reaches_the_model(tmp_path, command):
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    # As the kubelet lays out the config map the command writes.
    files = {
        f"nb-0001.{ref}.json": doc for ref, doc in documents(command, "nb-0001").items()
    }
    configmap_volume(tmp_path / "netbox", files)
    tool = make_get_evidence(tmp_path, policy)
    job = Job("nb-0001", "netbox", frozenset(), 0.0, "digest")
    for reference, document in documents(command, "nb-0001").items():
        reason, text = tool(job, {"reference": reference})
        assert reason is None, reference
        assert json.loads(text) == document


@pytest.mark.parametrize("name", sorted(CASES))
def test_each_held_out_cases_contract_reaches_the_model(tmp_path, command, name):
    # ADR 0042: a case's contract becomes the job's ev-0001.
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    contract = CASES[name]["contract"]
    document = command.facts_contract(contract, "nb-0001", "2026-10-25T08:00:00Z")
    configmap_volume(tmp_path / "netbox", {"nb-0001.ev-0001.json": document})
    tool = make_get_evidence(tmp_path, policy)
    job = Job("nb-0001", "netbox", frozenset(), 0.0, "digest")
    reason, text = tool(job, {"reference": "ev-0001"})
    assert reason is None, name
    assert json.loads(text) == document


def test_the_commands_size_limit_is_the_tool_services(command):
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert command.RESULT_BYTES == policy["limits"]["result_bytes"]
