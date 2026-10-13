"""The round trip that is allowed, and what the audit line says about it."""

import hashlib
import json

from conftest import MARKER, MARKER_B, TOKEN_A, TOKEN_B


def test_an_authorized_call_returns_the_evidence(two_jobs, lines):
    response = two_jobs.call(TOKEN_A)
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"])["marker"] == MARKER

    (line,) = lines()
    arguments = json.dumps({"reference": "ev-0001"}, separators=(",", ":"))
    assert line["event"] == "call"
    assert line["decision"] == "allowed"
    assert line["job"] == "job-a"
    assert line["caller"] == "testclient"
    assert line["tool"] == "get_evidence"
    assert line["args_sha256"] == hashlib.sha256(arguments.encode()).hexdigest()
    assert line["reason"] is None
    assert line["result_bytes"] == len(result["content"][0]["text"].encode())


def test_the_audit_line_holds_no_payload_and_no_token(two_jobs, lines):
    two_jobs.call(TOKEN_A)
    written = json.dumps(lines())
    assert MARKER not in written
    assert "ev-0001" not in written
    assert TOKEN_A not in written


def test_each_job_reads_its_own_target(two_jobs, lines):
    response = two_jobs.call(TOKEN_B, arguments={"reference": "ev-0002"})
    assert MARKER_B in response.text
    assert [line["job"] for line in lines()] == ["job-b"]


def test_the_tool_list_is_the_jobs_scope(service, lines):
    service.register("job-a", TOKEN_A)
    service.register("job-b", TOKEN_B, "synthetic-b", ["get_evidence", "other_tool"])
    listing = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    names = {}
    for token in (TOKEN_A, TOKEN_B):
        tools = service.post(token, listing).json()["result"]["tools"]
        names[token] = [tool["name"] for tool in tools]
    assert names == {TOKEN_A: ["get_evidence"], TOKEN_B: ["get_evidence", "other_tool"]}


def test_the_handshake_goose_sends_is_answered(two_jobs, lines):
    """What Goose 1.54.0 sent in the trial, in its order."""
    discover = {"jsonrpc": "2.0", "id": 0, "method": "server/discover"}
    assert two_jobs.post(TOKEN_A, discover).status_code == 200
    params = {"protocolVersion": "2025-11-25", "capabilities": {}}
    params["clientInfo"] = {"name": "goose", "version": "1.54.0"}
    start = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params}
    answer = two_jobs.post(TOKEN_A, start)
    assert answer.json()["result"]["serverInfo"]["name"] == "aisec-tools"
    ready = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert two_jobs.post(TOKEN_A, ready).status_code == 202
    assert lines() == []
