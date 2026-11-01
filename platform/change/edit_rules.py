#!/usr/bin/python3 -I
"""Applies an allowed fix for NetBox's port rules to the targets repository
(ADR 0056).

    edit_rules.py RULES PROPOSAL

Runs on the operator's machine, in the targets checkout, with the bundle the
propose command wrote. RULES is infra/targets/netbox-rules.json. Each change
removes the rules the policy named: an inbound rule on NetBox's subnet and
its outbound half on the viewpoint's subnet. The file has to be the one the
job judged, by its SHA-256, and in its own layout, so the diff is the removed
rules and nothing else. The edit is written only when the new file parses as
the old one less exactly those rules.

Exits 0 when the file was changed, 1 when the fix was not allowed or the edit
would change anything else, and 2 for a call without both files. Standard
library only.
"""

import copy
import hashlib
import json
import sys
from pathlib import Path

# The rules module is the collector's, in this checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "collectors" / "netbox"))

import netbox_rules


class Refused(Exception):
    pass


def removed_from(rules, removed):
    """The rules without each removed one, which has to be there once."""
    left = copy.deepcopy(rules)
    for gone in removed:
        found = [
            i
            for i, r in enumerate(left.get(gone["subnet"], []))
            if (r["direction"], r["name"], r["priority"])
            == (gone["direction"], gone["name"], gone["priority"])
        ]
        if len(found) != 1:
            raise Refused(
                f"{gone['subnet']} {gone['name']}: {len(found)} such rules, one expected"
            )
        del left[gone["subnet"]][found[0]]
    return left


def edit(rules_path, proposal_path):
    bundle = json.loads(Path(proposal_path).read_text(encoding="utf-8"))
    if not bundle.get("policy", {}).get("allowed"):
        raise Refused("the policy did not allow this proposal")
    changes = bundle["policy"]["changes"]
    if not changes or not all("rule" in c for c in changes):
        raise Refused("the proposal holds no change to the rules")
    if bundle.get("rehearsal", {}).get("passed") is not True:
        raise Refused("the rules' judgment without the change did not pass")
    path = Path(rules_path)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if any(c["sha256"] != digest for c in changes):
        raise Refused("the rules file is not the one the job judged")
    text = data.decode("utf-8")
    try:
        rules = netbox_rules.load(text)
    except netbox_rules.Invalid as error:
        raise Refused(f"the rules file: {error}") from None
    if netbox_rules.dump(rules) != text:
        raise Refused("the rules file is not in its own layout")
    removed = [gone for c in changes for gone in c["removed"]]
    left = removed_from(rules, removed)
    new = netbox_rules.dump(left)
    if netbox_rules.load(new) != left:
        raise Refused("the edit changes more than the removed rules")
    path.write_text(new, encoding="utf-8")
    return removed


def main(argv):
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        removed = edit(argv[1], argv[2])
    except (Refused, OSError, ValueError, KeyError, TypeError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    for gone in removed:
        print(
            f"{gone['subnet']}: without {gone['name']} ({gone['direction']}, {gone['priority']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
