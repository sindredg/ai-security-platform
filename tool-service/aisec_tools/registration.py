"""The registration listener. The dispatch step registers and revokes jobs here.

It has its own port, which the worker cannot reach. The caller proves itself
with its Kubernetes service account token. The token is checked offline, against
the cluster's public signing key, so this pod holds no credential for the
cluster and opens no connection to it.

    POST   /jobs        {"job", "target", "tools", "seconds", "token_sha256"}
    DELETE /jobs/<job>
"""

import json

import jsonschema
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from .audit import audit
from .http import bearer, caller, read_body, reply

REQUIRED = {"require": ["exp", "iat", "iss", "aud", "sub"]}


class CallerCheck:
    """Accepts one service account, for one audience, from one issuer."""

    def __init__(self, public_key_pem, issuer, audience, subject):
        # The type of the key picks the algorithm. The token's header does not.
        self.key = load_pem_public_key(public_key_pem)
        rsa_key = isinstance(self.key, rsa.RSAPublicKey)
        self.checks = {"algorithms": ["RS256" if rsa_key else "ES256"]}
        self.checks |= {"issuer": issuer, "audience": audience, "options": REQUIRED}
        self.subject = subject

    def accepts(self, token):
        try:
            claims = jwt.decode(token, self.key, **self.checks)
        except (jwt.PyJWTError, TypeError):
            # TypeError is what PyJWT raises for a key it cannot use.
            return False
        return claims["sub"] == self.subject


class Registration:
    def __init__(self, jobs, caller_check):
        self.jobs, self.caller_check, self.policy = jobs, caller_check, jobs.policy

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        event, job, status, reason = await self._handle(scope, receive)
        decision = "refused" if reason else "allowed"
        audit(event, decision, caller=caller(scope), job=job, reason=reason)
        await reply(send, status, {"error": "refused"} if reason else {"job": job})

    async def _handle(self, scope, receive):
        """Returns (event, job ID, status, reason). A reason means refused."""
        method, path = scope["method"], scope["path"]
        token = bearer(scope)
        if token is None or not self.caller_check.accepts(token):
            return "request", None, 401, "caller not accepted"
        if method == "DELETE" and path.startswith("/jobs/"):
            job_id = path.removeprefix("/jobs/")
            return "revoke", job_id if self.jobs.revoke(job_id) else None, 200, None
        if method != "POST" or path != "/jobs":
            return "request", None, 404, "not a registration path"
        body = await read_body(scope, receive, self.policy["limits"]["request_bytes"])
        try:
            fields = json.loads(body or b"")
            jsonschema.validate(fields, self.policy["registration_schema"])
        except (ValueError, jsonschema.ValidationError):
            return "register", None, 400, "malformed registration"
        reason = self.jobs.register(**fields)
        job_id = None if reason else fields["job"]
        return "register", job_id, 409 if reason else 201, reason
