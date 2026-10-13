"""get_evidence: one stored piece of evidence, by reference, read-only.

Evidence lives under one directory per target. The directory comes from the
job's scope, never from the call, so a job reads its own target and no other.
The policy's schema has already limited the reference to a fixed pattern. The
path is checked again here, because this is the line that opens a file.
"""

from pathlib import Path


def make_get_evidence(root):
    root = Path(root).resolve()

    def get_evidence(job, arguments):
        store = (root / job.target).resolve()
        path = (store / (arguments["reference"] + ".json")).resolve()
        if store.parent != root or path.parent != store or not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    return get_evidence
