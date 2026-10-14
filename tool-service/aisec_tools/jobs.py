"""Which jobs exist, and what each one may do.

A job is registered with the SHA-256 digest of its token, so the token itself
is seen only when the worker presents it. Scope is fixed at registration and
looked up by the token. Nothing in a call can widen it.
"""

import hashlib
import time
from dataclasses import dataclass

KEEP_ENDED_SECONDS = 3600


@dataclass
class Job:
    id: str
    target: str
    tools: frozenset
    expires: float
    digest: str
    calls: int = 0
    revoked: bool = False


class Jobs:
    def __init__(self, policy, clock=time.monotonic):
        self.policy = policy
        self.clock = clock
        self._by_id = {}
        self._by_digest = {}

    def register(self, job, target, tools, seconds, token_sha256):
        """Add a job. Returns the reason for a refusal, or None.

        The policy's registration schema has already checked the shape.
        """
        self._forget_old()
        if job in self._by_id or token_sha256 in self._by_digest:
            return "job or token already registered"
        allowed = self.policy["targets"].get(target)
        if allowed is None or not set(tools) <= set(allowed["tools"]):
            return "target or tool not in policy"
        entry = Job(job, target, frozenset(tools), self.clock() + seconds, token_sha256)
        self._by_id[job] = self._by_digest[token_sha256] = entry
        return None

    def revoke(self, job_id):
        """End a job by ID. Ending an unknown or ended job changes nothing."""
        job = self._by_id.get(job_id)
        if job is not None:
            job.revoked = True
        return job is not None

    def by_token(self, token):
        """Returns (job, None) for a live token, or (job or None, reason)."""
        digest = hashlib.sha256(token.encode()).hexdigest()
        job = self._by_digest.get(digest)
        if job is None:
            return None, "unknown token"
        return job, self.ended(job)

    def ended(self, job):
        if job.revoked:
            return "revoked token"
        if self.clock() >= job.expires:
            return "expired token"
        return None

    def count_call(self, job):
        """Counts every call, allowed or not. Returns a reason past the limit."""
        job.calls += 1
        if job.calls > self.policy["limits"]["calls_per_job"]:
            return "call limit reached"
        return None

    def _forget_old(self):
        cutoff = self.clock() - KEEP_ENDED_SECONDS
        for job in [j for j in self._by_id.values() if j.expires < cutoff]:
            del self._by_id[job.id], self._by_digest[job.digest]
