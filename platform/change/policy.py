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

The proposals come from the model's answer, or from the operator for a drill,
and are untrusted either way. The configured report and the contract are the
job's own, as the collect command kept them. Standard library only.
"""

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


def check(comparison, configured, contract):
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
    allowed = not reasons and bool(changes)
    return {
        "allowed": allowed,
        "reasons": reasons,
        "changes": changes if allowed else [],
    }
