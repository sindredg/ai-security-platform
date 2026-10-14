"""The tools. Each is a function of (job, arguments) that returns text or None."""

from .evidence import make_get_evidence


def make_tools(root):
    """Every tool the service has, by name. The policy decides who may call it."""
    return {"get_evidence": make_get_evidence(root / "evidence")}
