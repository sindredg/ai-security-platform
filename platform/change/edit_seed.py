#!/usr/bin/python3 -I
"""Applies an allowed proposal to the targets repository's seed (ADR 0045).

    edit_seed.py SEED PROPOSAL

Runs on the operator's machine, in the targets checkout, with the bundle the
propose command wrote. Each change removes one account from one permission's
users. The seed is edited as text, so the diff is the users line of each
changed permission and nothing else. Both versions are then parsed, and the
edit is written only when they differ in those users lists alone, by exactly
those removals.

Exits 0 when the seed was changed, 1 when the proposal was not allowed or the
edit would change anything else, and 2 for a call without both files.
Standard library only.
"""

import copy
import json
import re
import sys
from pathlib import Path

PERMISSIONS = "/api/users/permissions/"
USERS = re.compile(r'^(\s*"users": )(\[[^\]\n]*\])(,?)\s*$')


class Refused(Exception):
    pass


def permission_items(seed):
    for group in seed["objects"]:
        if group["path"] == PERMISSIONS:
            return {item["name"]: item for item in group["items"]}
    raise Refused("the seed holds no permissions")


def expected(seed, changes):
    """The seed as the changes leave it, built from the parsed seed."""
    want = copy.deepcopy(seed)
    items = permission_items(want)
    for change in changes:
        item = items.get(change["permission"])
        if item is None:
            raise Refused(f"{change['permission']}: not a permission in the seed")
        if change["account"] not in item.get("users", []):
            raise Refused(f"{change['permission']}: does not name {change['account']}")
        item["users"] = [u for u in item["users"] if u != change["account"]]
    return want


def edit_text(text, changes):
    """The seed's text with each change's account taken from the users line
    that follows its permission's name."""
    lines = text.split("\n")
    for change in changes:
        name = f'"name": {json.dumps(change["permission"])},'
        at = [i for i, line in enumerate(lines) if line.strip() == name]
        if len(at) != 1:
            raise Refused(f"{change['permission']}: {len(at)} name lines, one expected")
        for i in range(at[0] + 1, len(lines)):
            found = USERS.match(lines[i])
            if found:
                users = [u for u in json.loads(found[2]) if u != change["account"]]
                lines[i] = f"{found[1]}{json.dumps(users)}{found[3]}"
                break
        else:
            raise Refused(f"{change['permission']}: no users line after its name")
    return "\n".join(lines)


def edit(seed_path, proposal_path):
    bundle = json.loads(Path(proposal_path).read_text(encoding="utf-8"))
    if not bundle.get("policy", {}).get("allowed"):
        raise Refused("the policy did not allow this proposal")
    changes = bundle["policy"]["changes"]
    if not changes:
        raise Refused("the proposal holds no change")
    path = Path(seed_path)
    text = path.read_text(encoding="utf-8")
    want = expected(json.loads(text), changes)
    new = edit_text(text, changes)
    if json.loads(new) != want:
        raise Refused("the edit changes more than the proposal's users lists")
    path.write_text(new, encoding="utf-8")
    return changes


def main(argv):
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        changes = edit(argv[1], argv[2])
    except (Refused, OSError, ValueError, KeyError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    for change in changes:
        print(f"{change['permission']}: without {change['account']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
