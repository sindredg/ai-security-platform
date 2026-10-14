"""What a turned worker sends. The groups follow the roadmap's table.

Every case ends the same way: the call is refused, nothing of the result goes
back, and one audit line records the decision and the reason. The two helpers
in conftest check all three, and that no token reached the reply or the log.
"""

import json
from concurrent.futures import ThreadPoolExecutor

import anyio
import pytest
from conftest import MARKER, TOKEN_A, TOKEN_B, refused_by_gate, refused_call

# --- Malformed arguments ---------------------------------------------------


@pytest.mark.parametrize("body", [b"not json", b"\xff\xfe{}", b"", b"[1, 2]", b'"x"'])
def test_a_body_that_is_not_a_json_message(two_jobs, lines, body):
    response = two_jobs.post(TOKEN_A, content=body)
    line = refused_by_gate(response, 400, lines, TOKEN_A)
    assert line["job"] == "job-a"
    assert line["reason"] == "not JSON, or not an allowed message"


@pytest.mark.parametrize(
    "params",
    [
        None,
        "get_evidence",
        {"arguments": {"reference": "ev-0001"}},
        {"name": 7, "arguments": {"reference": "ev-0001"}},
        {"name": "get_evidence"},
        {"name": "get_evidence", "arguments": ["ev-0001"]},
    ],
)
def test_a_call_with_the_wrong_shape(two_jobs, lines, params):
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
    refused_by_gate(two_jobs.post(TOKEN_A, message), 400, lines, TOKEN_A)


@pytest.mark.parametrize("method", ["resources/list", "tools/call2", "", None, 5])
def test_a_method_the_policy_does_not_name(two_jobs, lines, method):
    message = {"jsonrpc": "2.0", "id": 1, "method": method}
    refused_by_gate(two_jobs.post(TOKEN_A, message), 400, lines, TOKEN_A)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"reference": 1},
        {"reference": None},
        {"reference": ["ev-0001"]},
        {"reference": "ev-0001", "extra": True},
        {"reference": "ev-0001", "target": "synthetic-b"},
    ],
)
def test_a_missing_field_a_wrong_type_and_an_unnamed_field(two_jobs, lines, arguments):
    line = refused_call(two_jobs.call(TOKEN_A, arguments=arguments), lines, TOKEN_A)
    assert line["reason"] == "arguments do not match the schema"


@pytest.mark.parametrize(
    "reference",
    [
        "../synthetic-b/ev-0002",
        "ev-0001/../../synthetic-b/ev-0002",
        "/etc/passwd",
        "ev-0001\x00",
        "ev-0001\n",
        "ev-00010",
        "EV-0001",
        "",
    ],
)
def test_a_reference_that_is_not_a_reference(two_jobs, lines, reference):
    response = two_jobs.call(TOKEN_A, arguments={"reference": reference})
    line = refused_call(response, lines, TOKEN_A)
    assert line["reason"] == "arguments do not match the schema"


@pytest.mark.parametrize("name", ["no_such_tool", "", "get_evidence ", "GET_EVIDENCE"])
def test_a_tool_name_no_policy_lists(two_jobs, lines, name):
    line = refused_call(two_jobs.call(TOKEN_A, name=name), lines, TOKEN_A)
    assert line["reason"] == "tool not in the job's scope"
    assert line["tool"] == name


# --- Cross-job access ------------------------------------------------------


def test_a_valid_token_asks_for_another_jobs_evidence(two_jobs, lines):
    # ev-0002 exists, under job-b's target. job-b gets it. job-a does not.
    assert two_jobs.call(TOKEN_B, arguments={"reference": "ev-0002"}).status_code == 200
    assert lines()[0]["decision"] == "allowed"
    response = two_jobs.call(TOKEN_A, arguments={"reference": "ev-0002"})
    line = refused_call(response, lines, TOKEN_A)
    assert line["job"] == "job-a"
    assert line["reason"] == "nothing by that reference"


def test_a_valid_token_asks_for_a_tool_outside_its_scope(service, lines):
    # other_tool is in the policy, allowed on synthetic-b, and it works: job-c
    # was registered with it and gets an answer. job-b has the same target and
    # was not. job-a has another target.
    token_c = "token-for-job-c-0123456789abcdefghijklmnopq"
    service.register("job-a", TOKEN_A)
    service.register("job-b", TOKEN_B, "synthetic-b", ["get_evidence"])
    service.register("job-c", token_c, "synthetic-b", ["other_tool"])
    lines()
    reference = {"reference": "ev-0002"}
    allowed = service.call(token_c, name="other_tool", arguments=reference)
    assert allowed.json()["result"]["isError"] is False
    lines()
    for token in (TOKEN_A, TOKEN_B):
        response = service.call(token, name="other_tool", arguments=reference)
        line = refused_call(response, lines, token)
        assert line["reason"] == "tool not in the job's scope"
    # And job-c holds other_tool only.
    response = service.call(token_c, arguments=reference)
    assert refused_call(response, lines, token_c)["reason"].startswith("tool not")


def test_a_job_cannot_be_registered_outside_the_policy(service, lines):
    cases = [
        ("synthetic", ["other_tool"]),
        ("synthetic", ["get_evidence", "other_tool"]),
        ("no-such-target", ["get_evidence"]),
    ]
    for target, tools in cases:
        made = service.register("job-a", TOKEN_A, target, tools)
        line = refused_by_gate(made, 409, lines, TOKEN_A)
        assert line["reason"] == "target or tool not in policy"
    refused_by_gate(service.call(TOKEN_A), 401, lines, TOKEN_A)


def test_the_arguments_name_another_job_and_the_token_decides(two_jobs, lines):
    arguments = {"reference": "ev-0002", "job": "job-b"}
    line = refused_call(two_jobs.call(TOKEN_A, arguments=arguments), lines, TOKEN_A)
    assert line["job"] == "job-a"


# --- Tokens ----------------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer",
        "Bearer ",
        "bearer " + TOKEN_A,
        "Basic " + TOKEN_A,
        TOKEN_A,
        "Bearer tøken",
    ],
)
def test_no_token_and_a_malformed_token(two_jobs, lines, header):
    headers = {} if header is None else {"Authorization": header.encode("latin-1")}
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    line = refused_by_gate(two_jobs.post(None, message, headers=headers), 401, lines)
    assert line["reason"] == "no token, or a malformed one"
    assert line["job"] is None


@pytest.mark.parametrize("token", ["never-issued", TOKEN_A + "x", TOKEN_A[:-1], "a b"])
def test_a_token_nobody_issued(two_jobs, lines, token):
    line = refused_by_gate(two_jobs.call(token), 401, lines, token)
    assert line["reason"] == "unknown token"
    assert line["job"] is None


def test_an_expired_token(two_jobs, lines):
    two_jobs.now += 599
    assert two_jobs.call(TOKEN_A).json()["result"]["isError"] is False
    lines()
    two_jobs.now += 1
    line = refused_by_gate(two_jobs.call(TOKEN_A), 401, lines, TOKEN_A)
    assert line["reason"] == "expired token"
    assert line["job"] == "job-a"


def test_a_token_revoked_when_its_job_ended(two_jobs, lines):
    assert two_jobs.revoke("job-a").status_code == 200
    assert [line["event"] for line in lines()] == ["revoke"]
    line = refused_by_gate(two_jobs.call(TOKEN_A), 401, lines, TOKEN_A)
    assert line["reason"] == "revoked token"
    # The other job is untouched.
    assert two_jobs.call(TOKEN_B, arguments={"reference": "ev-0002"}).status_code == 200


# --- Oversized requests ----------------------------------------------------


def test_a_body_over_the_limit_is_refused_before_it_is_parsed(two_jobs, lines):
    limit = two_jobs.policy["limits"]["request_bytes"]
    # Not JSON, so a parser would give the other reason.
    line = refused_by_gate(
        two_jobs.post(TOKEN_A, content=b"x" * (limit + 1)), 413, lines
    )
    assert line["reason"] == "request too large"
    exact = two_jobs.post(TOKEN_A, content=b"x" * limit)
    assert refused_by_gate(exact, 400, lines)["reason"].startswith("not JSON")


@pytest.mark.parametrize("declared", [b"10", None, b"-1", b"ten", b"8193"])
def test_a_body_larger_than_it_declares(two_jobs, lines, declared):
    """Straight at the ASGI app, because an HTTP client would fix the header."""
    headers = [(b"authorization", b"Bearer " + TOKEN_A.encode())]
    if declared is not None:
        headers.append((b"content-length", declared))
    scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": headers}
    scope["client"] = ("10.40.0.36", 40000)
    chunks = [b"x" * 4096] * 4
    sent, read = [], []

    async def receive():
        read.append(1)
        more = len(read) < len(chunks)
        return {
            "type": "http.request",
            "body": chunks[len(read) - 1],
            "more_body": more,
        }

    async def send(message):
        sent.append(message)

    anyio.run(two_jobs.tool_app, scope, receive, send)
    assert sent[0]["status"] == 413
    if declared in (b"10", None):
        # The header was absent or lied, so the count stopped the read.
        assert len(read) == 3
    else:
        # The header alone was enough. Nothing was read.
        assert read == []
    (line,) = lines()
    assert line["reason"] == "request too large"
    assert line["caller"] == "10.40.0.36"


def test_a_result_over_the_limit(two_jobs, lines):
    limit = two_jobs.policy["limits"]["result_bytes"]
    big = two_jobs.root / "evidence" / "synthetic" / "ev-0009.json"
    big.write_text(MARKER + "x" * limit)
    response = two_jobs.call(TOKEN_A, arguments={"reference": "ev-0009"})
    assert refused_call(response, lines, TOKEN_A)["reason"] == "result too large"
    big.write_text("x" * limit)
    assert (
        two_jobs.call(TOKEN_A, arguments={"reference": "ev-0009"}).json()["result"][
            "isError"
        ]
        is False
    )


def test_one_call_more_than_the_jobs_limit(two_jobs, lines):
    limit = two_jobs.policy["limits"]["calls_per_job"]
    for _ in range(limit - 1):
        assert two_jobs.call(TOKEN_A).json()["result"]["isError"] is False
    # A refused call counts too.
    two_jobs.call(TOKEN_A, name="no_such_tool")
    lines()
    line = refused_call(two_jobs.call(TOKEN_A), lines, TOKEN_A)
    assert line["reason"] == "call limit reached"
    # The limit is the job's own.
    assert (
        two_jobs.call(TOKEN_B, arguments={"reference": "ev-0002"}).json()["result"][
            "isError"
        ]
        is False
    )


# --- Concurrent cancellation -----------------------------------------------


def test_a_job_cancelled_while_its_call_is_in_flight(two_jobs, lines):
    two_jobs.door.clear()
    with ThreadPoolExecutor() as pool:
        flying = pool.submit(two_jobs.call, TOKEN_A)
        assert two_jobs.inside.acquire(timeout=10)
        assert two_jobs.revoke("job-a").status_code == 200
        assert [line["event"] for line in lines()] == ["revoke"]
        two_jobs.door.set()
        response = flying.result(timeout=10)
    assert refused_call(response, lines, TOKEN_A)["reason"] == "revoked token"


def test_a_job_that_expires_while_its_call_is_in_flight(two_jobs, lines):
    two_jobs.door.clear()
    with ThreadPoolExecutor() as pool:
        flying = pool.submit(two_jobs.call, TOKEN_A)
        assert two_jobs.inside.acquire(timeout=10)
        two_jobs.now += 600
        two_jobs.door.set()
        response = flying.result(timeout=10)
    assert refused_call(response, lines, TOKEN_A)["reason"] == "expired token"


def test_two_calls_race_the_revocation(two_jobs, lines):
    two_jobs.door.clear()
    with ThreadPoolExecutor() as pool:
        flying = [pool.submit(two_jobs.call, TOKEN_A) for _ in range(2)]
        assert two_jobs.inside.acquire(timeout=10)
        assert two_jobs.inside.acquire(timeout=10)
        two_jobs.revoke("job-a")
        two_jobs.door.set()
        responses = [call.result(timeout=10) for call in flying]
    written = lines()
    assert [line["event"] for line in written] == ["revoke", "call", "call"]
    assert [line["decision"] for line in written[1:]] == ["refused", "refused"]
    for response in responses:
        assert response.json()["result"]["isError"] is True
        assert MARKER not in response.text
    refused_by_gate(two_jobs.call(TOKEN_A), 401, lines, TOKEN_A)


def test_a_job_cancelled_twice(two_jobs, lines):
    assert two_jobs.revoke("job-a").status_code == 200
    assert two_jobs.revoke("job-a").status_code == 200
    assert two_jobs.revoke("never-registered").status_code == 200
    lines()
    refused_by_gate(two_jobs.call(TOKEN_A), 401, lines, TOKEN_A)


def test_a_job_registered_twice(two_jobs, lines):
    second = "second-token-for-job-a-0123456789abcdefghij"
    again = two_jobs.register("job-a", second)
    line = refused_by_gate(again, 409, lines, second)
    assert line["reason"] == "job or token already registered"
    # The same token under a new job name is refused as well.
    refused_by_gate(two_jobs.register("job-c", TOKEN_A), 409, lines, TOKEN_A)
    refused_by_gate(two_jobs.call(second), 401, lines, second)
    # One revocation leaves no live token for the job.
    two_jobs.revoke("job-a")
    lines()
    refused_by_gate(two_jobs.call(TOKEN_A), 401, lines, TOKEN_A)
    # And the name cannot be taken over by a new token while the job is remembered.
    refused_by_gate(two_jobs.register("job-a", second), 409, lines, second)


# --- Everything that is not a tool call ------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/mcp"),
        ("DELETE", "/mcp"),
        ("GET", "/.well-known/oauth-protected-resource/mcp"),
        ("GET", "/.well-known/oauth-authorization-server"),
        ("GET", "/.well-known/openid-configuration/mcp"),
        ("POST", "/register"),
        ("POST", "/jobs"),
        ("POST", "/mcp/"),
        ("GET", "/"),
    ],
)
def test_the_paths_goose_tries_after_a_refusal(two_jobs, lines, method, path):
    headers = {"Authorization": "Bearer " + TOKEN_A}
    response = two_jobs.tools.request(method, path, headers=headers)
    assert (
        refused_by_gate(response, 404, lines, TOKEN_A)["reason"]
        == "not the tool endpoint"
    )


@pytest.mark.parametrize(
    "host", ["evil.example:8443", "tool-service.aisec.internal:8443", "10.40.0.4:30443"]
)
def test_a_host_name_that_is_not_the_services(two_jobs, lines, host):
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
    message["params"] = {"name": "get_evidence", "arguments": {"reference": "ev-0001"}}
    response = two_jobs.post(TOKEN_A, message, headers={"Host": host})
    assert response.status_code >= 400
    assert MARKER not in response.text
    (line,) = lines()
    assert line["decision"] == "refused"
    assert line["reason"].startswith("refused by the MCP layer")
    assert json.dumps(line).count(TOKEN_A) == 0
