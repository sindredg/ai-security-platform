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

from aisec_tools.jobs import Job
from aisec_tools.tools.evidence import make_get_evidence

COLLECTORS = Path(__file__).parent.parent.parent / "collectors" / "netbox"
REPORTS = json.loads((COLLECTORS / "tests" / "reports.json").read_text())


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
    (tmp_path / "netbox").mkdir()
    for reference, document in documents(command, "nb-0001").items():
        # As the command stores it in the ConfigMap.
        text = json.dumps(document, indent=2)
        (tmp_path / "netbox" / f"nb-0001.{reference}.json").write_text(text)
    tool = make_get_evidence(tmp_path, policy)
    job = Job("nb-0001", "netbox", frozenset(), 0.0, "digest")
    for reference, document in documents(command, "nb-0001").items():
        reason, text = tool(job, {"reference": reference})
        assert reason is None, reference
        assert json.loads(text) == document
