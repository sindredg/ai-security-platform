"""Fixtures: a service built from the real policy file, with a second target
and a second, working tool added so that the cross-job cases have something
to cross."""

import hashlib
import json
import threading
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from starlette.testclient import TestClient

import aisec_tools.__main__ as entry

POLICY = Path(__file__).parent.parent.parent / "policies" / "tool-service.json"
MARKER = "EVIDENCE-MARKER-A-5521"
MARKER_B = "EVIDENCE-MARKER-B-9034"


def public_pem(key):
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def kid_of(key):
    return hashlib.sha256(public_pem(key)).hexdigest()[:16]


def jwks(*keys):
    """A key set in the form the cluster serves at /openid/v1/jwks."""
    entries = []
    for key in keys:
        if isinstance(key, rsa.RSAPrivateKey):
            entry = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
            entry["alg"] = "RS256"
        else:
            entry = jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
            entry["alg"] = "ES256"
        entry.update({"use": "sig", "kid": kid_of(key)})
        entries.append(entry)
    return json.dumps({"keys": entries})


@pytest.fixture(scope="session")
def signer():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_signer():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def ec_signer():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def root(tmp_path, signer):
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["targets"]["synthetic-b"] = {"tools": ["get_evidence", "other_tool"]}
    policy["tools"]["other_tool"] = dict(policy["tools"]["get_evidence"])
    (tmp_path / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    for target, reference, marker in (
        ("synthetic", "ev-0001", MARKER),
        ("synthetic-b", "ev-0002", MARKER_B),
    ):
        (tmp_path / "evidence" / target).mkdir(parents=True)
        path = tmp_path / "evidence" / target / (reference + ".json")
        path.write_text(json.dumps({"reference": reference, "marker": marker}))
    (tmp_path / "sa-jwks.json").write_text(jwks(signer), encoding="utf-8")
    return tmp_path


class Service:
    """The two apps, their clients, and what a test needs to drive them."""

    def __init__(self, root, signer, monkeypatch):
        self.root, self.signer = root, signer
        # The real tool, behind a door a test can shut to keep a call in flight.
        self.door, self.inside = threading.Event(), threading.Semaphore(0)
        self.door.set()
        real_tools = entry.make_tools

        def held_tools(path):
            tool = real_tools(path)["get_evidence"]

            def held(job, arguments):
                self.inside.release()
                assert self.door.wait(10)
                return tool(job, arguments)

            # other_tool exists and works, so only the job's scope refuses it.
            return {"get_evidence": held, "other_tool": held}

        monkeypatch.setattr(entry, "make_tools", held_tools)
        self.policy, self.tool_app, self.register_app = entry.build(root)
        self.jobs = self.tool_app.jobs
        self.now = 1000.0
        self.jobs.clock = lambda: self.now
        where = self.policy["listeners"]
        self.caller = self.policy["registration_caller"]
        # The worker dials the advertised port, and the Host header says so.
        host = "https://{tls_name}:{advertised_port}".format(**where)
        self.tools = TestClient(self.tool_app, base_url=host)
        self.registration = TestClient(self.register_app)

    def sa_token(self, key=None, algorithm="RS256", kid=None, **changes):
        claims = {
            "iss": self.caller["issuer"],
            "aud": self.caller["audience"],
            "sub": self.caller["subject"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        }
        claims.update(changes)
        key = key or self.signer
        headers = {"kid": kid or kid_of(key)}
        return jwt.encode(claims, key, algorithm=algorithm, headers=headers)

    def register(self, job, token, target="synthetic", tools=None, seconds=600):
        body = {
            "job": job,
            "target": target,
            "tools": tools or ["get_evidence"],
            "seconds": seconds,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        }
        headers = {"Authorization": "Bearer " + self.sa_token()}
        return self.registration.post("/jobs", json=body, headers=headers)

    def revoke(self, job):
        headers = {"Authorization": "Bearer " + self.sa_token()}
        return self.registration.delete("/jobs/" + job, headers=headers)

    def post(self, token, message=None, content=None, headers=None):
        """One MCP message to the tool listener, as the worker sends it."""
        send = {"Accept": "application/json, text/event-stream"}
        send["Content-Type"] = "application/json"
        if token is not None:
            send["Authorization"] = "Bearer " + token
        send.update(headers or {})
        if content is None:
            content = json.dumps(message).encode()
        return self.tools.post("/mcp", content=content, headers=send)

    def call(self, token, name="get_evidence", arguments=None):
        if arguments is None:
            arguments = {"reference": "ev-0001"}
        params = {"name": name, "arguments": arguments}
        message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
        return self.post(token, message)


@pytest.fixture
def service(root, signer, monkeypatch):
    made = Service(root, signer, monkeypatch)
    with made.tools:
        yield made


@pytest.fixture
def lines(capsys):
    """Returns the audit lines written since the last time it was asked."""

    def read():
        out = capsys.readouterr().out
        return [json.loads(line) for line in out.splitlines()]

    return read


TOKEN_A = "token-for-job-a-0123456789abcdefghijklmnopq"
TOKEN_B = "token-for-job-b-0123456789abcdefghijklmnopq"


@pytest.fixture
def two_jobs(service, lines):
    assert service.register("job-a", TOKEN_A).status_code == 201
    made = service.register("job-b", TOKEN_B, "synthetic-b", ["get_evidence"])
    assert made.status_code == 201
    lines()
    return service


def refused_by_gate(response, status, lines, *secrets):
    """A refusal in front of the SDK: the status, one line, and nothing leaked."""
    written = lines()
    assert response.status_code == status
    assert response.json() == {"error": "refused"}
    assert [line["decision"] for line in written] == ["refused"]
    for secret in (MARKER, MARKER_B, *secrets):
        assert secret not in response.text
        assert secret not in json.dumps(written)
    return written[0]


def refused_call(response, lines, *secrets):
    """A refused tool call: an MCP error result, one line, and nothing leaked."""
    written = lines()
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["content"][0]["text"] == "refused: " + written[0]["reason"]
    assert [(line["event"], line["decision"]) for line in written] == [
        ("call", "refused")
    ]
    for secret in (MARKER, MARKER_B, *secrets):
        assert secret not in response.text
        assert secret not in json.dumps(written)
    return written[0]
