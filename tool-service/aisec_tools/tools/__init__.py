"""The tools. Each is a function of (job, arguments) that returns (None, text),
or (reason, None) for a refusal in its own words."""

import os
from pathlib import Path

from .evidence import make_get_evidence


def make_tools(root, policy):
    """Every tool the service has, by name. The policy decides who may call it.

    The evidence is under the root, unless AISEC_EVIDENCE names another
    directory. The pod mounts each target's store as a volume of its own there.
    """
    evidence = Path(os.environ.get("AISEC_EVIDENCE", root / "evidence"))
    return {"get_evidence": make_get_evidence(evidence, policy)}
