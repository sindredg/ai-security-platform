"""get_evidence: one stored piece of evidence, by reference, read-only.

Evidence lives under one directory per target. The directory comes from the
job's scope, never from the call, so a job reads its own target and no other.
On a per-job target the file name starts with the job's ID, so a job reads its
own collection and no other job's on the same target (ADR 0040).

The policy's input schema has already limited the reference to a fixed
pattern. The target's list of references limits it again, and the path is
checked again here, because this is the line that opens a file.

What the file holds came from a target, so it is checked before the model sees
any of it: one JSON document, no key twice, and every field and value as the
schema for its kind names them (#152). The model gets the document as parsed,
not the file's text.
"""

import json
from pathlib import Path

import jsonschema

NOTHING = ("nothing by that reference", None)
REFUSED = ("evidence does not match its schema", None)


class RepeatedKey(ValueError):
    pass


def no_repeated_keys(pairs):
    found = dict(pairs)
    if len(found) != len(pairs):
        raise RepeatedKey("a key appears twice")
    return found


def make_get_evidence(root, policy):
    root = Path(root).resolve()

    def get_evidence(job, arguments):
        target = policy["targets"].get(job.target)
        reference = arguments["reference"]
        if target is None or reference not in target["evidence"]:
            return NOTHING
        name = reference if target["store"] == "shared" else f"{job.id}.{reference}"
        store = (root / job.target).resolve()
        path = (store / (name + ".json")).resolve()
        if store.parent != root or path.parent != store or not path.is_file():
            return NOTHING
        try:
            text = path.read_text(encoding="utf-8")
            document = json.loads(text, object_pairs_hook=no_repeated_keys)
            schema = policy["evidence_schemas"][target["evidence"][reference]]
            jsonschema.validate(document, schema)
        except (ValueError, jsonschema.ValidationError):
            return REFUSED
        if document["reference"] != reference:
            return REFUSED
        if target["store"] != "shared" and document["job"] != job.id:
            return REFUSED
        return None, json.dumps(document, indent=2, sort_keys=True)

    return get_evidence
