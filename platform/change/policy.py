"""The policy check on a NetBox job's proposals (ADR 0043).

A library on the orchestrator host, installed beside the collector in
/usr/local/lib/aisec/, whose configured rule it reuses. It decides whether a
job's proposals go on to a rehearsal and a pull request. A proposal removes
one permission from one account, and the set is allowed only when every one
of these holds:

- The comparison matched, and read every proposal line.
- Each account both checks call excess has exactly one proposal, and no other
  account has one.
- The action is remove, and the permission is one the account holds directly,
  not through a group.
- The checks name that permission in the account's excess, and without it the
  account is within its contract.

A proposal for a viewpoint (ADR 0056), under the name viewpoint-NAME, removes
one inbound rule from NetBox's subnet, named by its priority, and the rule's
outbound half on the viewpoint's subnet. It is allowed only when:

- Both checks call the viewpoint excess, and it has exactly one proposal.
- The priority names an inbound allow on NetBox's subnet in the job's rules
  that lets the viewpoint in to NetBox's port.
- Without it and its outbound half the viewpoint is within, and every other
  viewpoint keeps its configured verdict.

A job's fix changes NetBox's permissions or the rules, not both: the two are
delivered by different hands.

The proposals come from the model's answer, or from the operator for a drill,
and are untrusted either way. The configured report, the rules, and the
contract are the job's own, as the collect command kept them. Standard library
only.
"""

import netbox_rules
from netbox_access import judge_configured, verdict


def excess_permissions(permissions, contract):
    """The IDs of the permissions an excess reason rests on, in order."""
    found = []
    for reason in judge_configured(permissions, contract):
        if reason["kind"] == "excess":
            found += [i for i in reason["permissions"] if i not in found]
    return found


def implied_fix(permissions, contract):
    """The excess permissions whose removal leaves the account within, [] for
    an account with none, or None when removing them is not enough."""
    excess = excess_permissions(permissions, contract)
    rest = [p for p in permissions if p["id"] not in excess]
    if verdict(judge_configured(rest, contract)) != "within":
        return None
    return excess


def judge(account, proposal, permissions, contract):
    """The reasons one proposal for an excess account is refused, if any."""
    if proposal["action"] != "remove":
        return [f"{account}: the action {proposal['action']}, not remove"]
    target = proposal["permission"]
    held = {p["id"]: p for p in permissions}
    if target not in held:
        return [f"{account}: permission {target} is not one it holds"]
    if held[target]["via"] != "user":
        return [f"{account}: permission {target} comes through {held[target]['via']}"]
    if target not in excess_permissions(permissions, contract):
        return [f"{account}: permission {target} is not one the checks call excess"]
    rest = [p for p in permissions if p["id"] != target]
    left = verdict(judge_configured(rest, contract))
    if left != "within":
        return [f"{account}: without permission {target} it is {left}, not within"]
    return []


def judge_viewpoint(name, proposal, rules, contract):
    """The reasons one proposal for an excess viewpoint is refused, if any,
    and the change if not."""
    if proposal["action"] != "remove":
        return [f"{name}: the action {proposal['action']}, not remove"], None
    network = contract.get("network")
    if rules is None or network is None:
        return [f"{name}: the job has no rules or no network part"], None
    view = name[len(netbox_rules.VIEWPOINT) :]
    priority = proposal["permission"]
    try:
        left, removed = netbox_rules.change(rules["rules"], network, view, priority)
    except netbox_rules.Invalid as error:
        return [f"{name}: {error}"], None
    before = netbox_rules.configured(rules["rules"], network)
    after = netbox_rules.configured(left, network)
    reasons = []
    if after[view]["verdict"] != "within":
        reasons.append(
            f"{name}: without rule {priority} it is {after[view]['verdict']}, not within"
        )
    for other in sorted(set(after) - {view}):
        if after[other]["verdict"] != before[other]["verdict"]:
            reasons.append(
                f"{name}: without rule {priority}, viewpoint-{other} is "
                f"{after[other]['verdict']}, not {before[other]['verdict']}"
            )
    change = {
        "account": name,
        "rule": removed[0]["name"],
        "priority": priority,
        "removed": removed,
        "commit": rules["commit"],
        "sha256": rules["sha256"],
    }
    return reasons, change


def check(comparison, configured, contract, rules=None):
    """Whether the job's proposals go on, why not, and the changes if so."""
    reasons, changes = [], []
    if comparison["outcome"] != "match":
        reasons.append(
            f"the comparison's outcome is {comparison['outcome']}, not match"
        )
    if comparison["unread_proposals"]:
        unread = comparison["unread_proposals"]
        reasons.append(f"proposal lines that could not be read: {unread}")
    rows = {row["account"]: row for row in comparison["accounts"]}
    excess = {
        name
        for name, row in rows.items()
        if row["configured"] == row["observed"] == "excess"
    }
    if not excess:
        reasons.append("no account the checks call excess")
    # The same change twice is one proposal, as two agreeing verdict lines
    # are one verdict.
    by_account = {}
    for proposal in comparison["proposals"]:
        same = by_account.setdefault(proposal["account"], [])
        if not any(
            (p["action"], p["permission"])
            == (proposal["action"], proposal["permission"])
            for p in same
        ):
            same.append(proposal)
    for name in sorted(by_account):
        if name not in rows:
            reasons.append(f"{name}: not an account the checks name")
        elif name not in excess:
            reasons.append(f"{name}: the checks do not call it excess")
    for name in sorted(excess):
        proposals = by_account.get(name, [])
        if not proposals:
            reasons.append(f"{name}: excess by both checks, and no proposal")
            continue
        if len(proposals) > 1:
            reasons.append(f"{name}: {len(proposals)} proposals, one expected")
            continue
        if name.startswith(netbox_rules.VIEWPOINT):
            refused, change = judge_viewpoint(name, proposals[0], rules, contract)
            reasons += refused
            if not refused:
                changes.append(change)
            continue
        permissions = configured["accounts"].get(name, {}).get("permissions", [])
        refused = judge(name, proposals[0], permissions, contract)
        reasons += refused
        if not refused:
            held = {p["id"]: p for p in permissions}
            target = proposals[0]["permission"]
            changes.append(
                {
                    "account": name,
                    "permission_id": target,
                    "permission": held[target]["name"],
                }
            )
    kinds = {"rule" in c for c in changes}
    if len(kinds) > 1:
        reasons.append(
            "a fix changes NetBox's permissions or its port's rules, not both"
        )
    allowed = not reasons and bool(changes)
    return {
        "allowed": allowed,
        "reasons": reasons,
        "changes": changes if allowed else [],
    }
