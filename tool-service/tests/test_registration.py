"""Who may register a job. The caller's service account token is checked
offline against the cluster's public signing key."""

import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from conftest import TOKEN_A, public_pem, refused_by_gate
from cryptography.hazmat.primitives.asymmetric import ec

from aisec_tools.registration import CallerCheck


def body(job="job-a", **changes):
    made = {
        "job": job,
        "target": "synthetic",
        "tools": ["get_evidence"],
        "seconds": 600,
    }
    made["token_sha256"] = hashlib.sha256(TOKEN_A.encode()).hexdigest()
    made.update(changes)
    return {name: value for name, value in made.items() if value is not ...}


def post(service, sa_token, payload=None):
    headers = {} if sa_token is None else {"Authorization": "Bearer " + sa_token}
    return service.registration.post("/jobs", json=payload or body(), headers=headers)


def test_the_dispatch_account_registers_and_revokes(service, lines):
    made = post(service, service.sa_token())
    assert made.status_code == 201
    assert made.json() == {"job": "job-a"}
    (line,) = lines()
    assert (line["event"], line["decision"], line["job"]) == (
        "register",
        "allowed",
        "job-a",
    )
    assert service.call(TOKEN_A).json()["result"]["isError"] is False
    assert service.revoke("job-a").status_code == 200
    assert service.call(TOKEN_A).status_code == 401


def test_the_token_itself_is_never_sent_to_registration(service, lines):
    post(service, service.sa_token())
    assert TOKEN_A not in json.dumps(lines())
    assert all(TOKEN_A not in key for key in service.jobs._by_digest)


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "another-service"},
        {"aud": ["https://kubernetes.default.svc.cluster.local"]},
        {"iss": "https://another-cluster.example"},
        {"sub": "system:serviceaccount:orchestration:default"},
        {"sub": "system:serviceaccount:tool-services:dispatch"},
        {"exp": int(time.time()) - 5},
        {"exp": ...},
        {"iat": ...},
        {"sub": ...},
        {"aud": ...},
        {"iss": ...},
    ],
)
def test_a_service_account_token_with_the_wrong_claims(service, lines, changes):
    token = service.sa_token(**{k: v for k, v in changes.items() if v is not ...})
    for name in [k for k, v in changes.items() if v is ...]:
        claims = jwt.decode(token, options={"verify_signature": False})
        del claims[name]
        token = jwt.encode(claims, service.signer, algorithm="RS256")
    line = refused_by_gate(post(service, token), 401, lines, token)
    assert line["reason"] == "caller not accepted"
    assert service.call(TOKEN_A).status_code == 401


def test_a_service_account_token_from_another_signer(service, lines, other_signer):
    token = service.sa_token(key=other_signer)
    refused_by_gate(post(service, token), 401, lines, token)


def test_a_token_signed_with_the_public_key_as_a_shared_secret(service, lines):
    """The algorithm confusion attack: HS256, keyed with the public PEM.

    PyJWT will not sign with a PEM as a shared secret, so the token is built
    by hand.
    """

    def part(data):
        return base64.urlsafe_b64encode(data).rstrip(b"=")

    claims = jwt.decode(service.sa_token(), options={"verify_signature": False})
    signed = part(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    signed += b"." + part(json.dumps(claims).encode())
    mac = hmac.new(public_pem(service.signer), signed, hashlib.sha256).digest()
    token = (signed + b"." + part(mac)).decode()
    refused_by_gate(post(service, token), 401, lines, token)


def test_an_unsigned_token(service, lines):
    claims = jwt.decode(service.sa_token(), options={"verify_signature": False})
    token = jwt.encode(claims, None, algorithm="none")
    refused_by_gate(post(service, token), 401, lines, token)


@pytest.mark.parametrize("header", [None, "", "not-a-jwt", "a.b.c"])
def test_no_caller_token_or_a_broken_one(service, lines, header):
    refused_by_gate(post(service, header), 401, lines)


def test_the_workers_job_token_does_not_open_registration(service, lines):
    post(service, service.sa_token())
    lines()
    refused_by_gate(post(service, TOKEN_A, body("job-x")), 401, lines, TOKEN_A)
    headers = {"Authorization": "Bearer " + TOKEN_A}
    gone = service.registration.delete("/jobs/job-a", headers=headers)
    refused_by_gate(gone, 401, lines, TOKEN_A)
    assert service.call(TOKEN_A).json()["result"]["isError"] is False


def test_an_elliptic_curve_signer_works_the_same(service, ec_signer, other_signer):
    """K3s can sign with either key type. The check follows the key."""
    caller = service.policy["registration_caller"]
    check = CallerCheck(public_pem(ec_signer), **caller)
    assert check.accepts(service.sa_token(key=ec_signer, algorithm="ES256"))
    # An RSA token against an elliptic curve key is refused, not a crash.
    assert not check.accepts(service.sa_token())
    assert not check.accepts(service.sa_token(key=other_signer))
    other_curve = ec.generate_private_key(ec.SECP256R1())
    assert not check.accepts(service.sa_token(key=other_curve, algorithm="ES256"))


def test_an_elliptic_curve_token_against_an_rsa_signer(service, lines, ec_signer):
    token = service.sa_token(key=ec_signer, algorithm="ES256")
    refused_by_gate(post(service, token), 401, lines, token)


@pytest.mark.parametrize(
    "changes",
    [
        {"job": "Job-A"},
        {"job": "job-a\n"},
        {"job": "../job"},
        {"job": ""},
        {"job": "j" * 64},
        {"job": 7},
        {"job": ...},
        {"seconds": 0},
        {"seconds": -1},
        {"seconds": 1801},
        {"seconds": "600"},
        {"seconds": True},
        {"tools": []},
        {"tools": "get_evidence"},
        {"tools": ["get_evidence", "get_evidence"]},
        {"tools": [7]},
        {"target": 7},
        {"token_sha256": TOKEN_A},
        {"token_sha256": "A" * 64},
        {"token_sha256": "a" * 63},
        {"token_sha256": "a" * 64 + "\n"},
        {"extra": 1},
        {"token": TOKEN_A},
    ],
)
def test_a_malformed_registration(service, lines, changes):
    line = refused_by_gate(
        post(service, service.sa_token(), body(**changes)), 400, lines
    )
    assert line["reason"] == "malformed registration"
    assert service.jobs._by_id == {}


@pytest.mark.parametrize("content", [b"", b"not json", b"[]", b"\xff", b"x" * 9000])
def test_a_registration_body_that_is_not_a_json_object(service, lines, content):
    headers = {"Authorization": "Bearer " + service.sa_token()}
    response = service.registration.post("/jobs", content=content, headers=headers)
    refused_by_gate(response, 400, lines)


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/jobs"), ("POST", "/jobs/job-a"), ("PUT", "/jobs"), ("POST", "/mcp")],
)
def test_a_path_registration_does_not_have(service, lines, method, path):
    headers = {"Authorization": "Bearer " + service.sa_token()}
    response = service.registration.request(method, path, headers=headers)
    refused_by_gate(response, 404, lines)


def test_ended_jobs_are_forgotten_an_hour_after_they_expire(service, lines):
    post(service, service.sa_token())
    service.now += 600 + 3600 - 1
    assert post(service, service.sa_token()).status_code == 409
    service.now += 2
    assert post(service, service.sa_token()).status_code == 201
