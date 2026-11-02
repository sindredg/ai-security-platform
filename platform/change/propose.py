#!/usr/bin/python3 -I
"""Proposes a NetBox job's fix (ADR 0043, ADR 0045).

    propose-netbox-fix JOB [--proposals FILE]

Runs as root on the orchestrator, after the job's workflow. It reads the
workflow and takes its comparison only from a run of the investigate
template that went through its dispatch and its comparison and matched
(#203). It checks the comparison's proposals with the policy, rehearses
every one it can name on the copy, even one the policy refuses, and writes
the bundle to /var/lib/aisec/proposals/JOB/: proposal.json, and for a fix that
was allowed and passed its rehearsal, pr-body.md, which the operator's machine
uses for the pull request. A job is proposed once, and a fix only once until
it is delivered: a proposal naming an account and permission that an earlier
allowed, rehearsed bundle holds is refused while no delivery of that bundle
passed, and nothing is written for it (ADR 0053).

A fix for a viewpoint (ADR 0056) changes NetBox's port rules in the targets
repository, which no copy can stand in for: the copy shares the lab VM and
its network with the live NetBox's subnets. So it has no staging test. The
bundle holds the rules' judgment without the change instead, and says so,
and the connections from the viewpoints after the operator's apply are the
test.

With --proposals, the file's proposals replace the comparison's, in the same
shape, and the bundle marks them as the operator's. It is for the unsafe
patch's demonstration and the drills.

Nothing the model wrote is copied but what matched a pattern in the
comparison: account names, actions, permission IDs, and references. Names of
permissions come from the job's collection, or from NetBox for a permission
the collection does not hold, and are checked against a pattern too.

Exits 0 for a fix that was allowed and passed its rehearsal, 1 for one that
was refused or failed it, and 2 for a call without a job ID. Standard library
only.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/usr/local/lib/aisec")

import netbox_access
import netbox_rules

import netbox_change
import policy
import rehearse

STATE = Path(os.environ.get("AISEC_STATE", "/var/lib/aisec/evidence/netbox"))
PROPOSALS = Path(os.environ.get("AISEC_PROPOSALS", "/var/lib/aisec/proposals"))
# The delivery command's results, one per tag (ADR 0046).
DELIVERIES = Path(os.environ.get("AISEC_DELIVERIES", "/var/lib/aisec/delivery/results"))
CONTRACT = Path(os.environ.get("AISEC_CONTRACT", "/etc/aisec/netbox/contract.json"))
CASES = Path(os.environ.get("AISEC_CASES", "/etc/aisec/netbox/cases.json"))
KUBECTL = os.environ.get("AISEC_KUBECTL", "/usr/local/bin/k3s kubectl").split()
NAMESPACE = "orchestration"
TEMPLATE = "investigate"
JOB_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
ACCOUNT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
REFERENCE = re.compile(r"ev-[0-9]{4}")
# A permission's name is NetBox's, so target side, and it goes into a public
# pull request. The seed's names fit this.
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 :._-]{0,99}")
CONTRACT_FIELDS = ("accounts", "viewpoint", "grants", "reads", "denials", "network")


class Refused(Exception):
    pass


def workflow_checked(workflow, job):
    """The workflow's comparison, if the workflow is a run of the investigate
    template from its own entrypoint whose comparison ran and matched."""
    spec, status = workflow.get("spec", {}), workflow.get("status", {})
    if spec.get("workflowTemplateRef", {}).get("name") != TEMPLATE:
        raise Refused(f"not a run of the {TEMPLATE} template")
    if spec.get("entrypoint", TEMPLATE) != TEMPLATE:
        raise Refused(f"run from the entrypoint {spec['entrypoint']}, not {TEMPLATE}")
    # The steps are inline (ADR 0048), so a node carries the step's name as
    # its display name, and no template name. The template above names the
    # steps, not the submitter.
    nodes = [
        node
        for node in status.get("nodes", {}).values()
        if node.get("displayName") == "compare" and node.get("type") == "Pod"
    ]
    if len(nodes) != 1:
        raise Refused(f"{len(nodes)} comparisons, one expected")
    if status.get("phase") != "Succeeded" or nodes[0].get("phase") != "Succeeded":
        raise Refused("the workflow or its comparison did not succeed")
    values = [
        p.get("value")
        for p in nodes[0].get("outputs", {}).get("parameters", [])
        if p.get("name") == "comparison"
    ]
    try:
        comparison = json.loads(values[0]) if len(values) == 1 else None
    except (TypeError, ValueError):
        comparison = None
    if not isinstance(comparison, dict):
        raise Refused("the comparison's output is not a comparison")
    if comparison.get("job") != job:
        raise Refused("the comparison is for another job")
    if comparison.get("outcome") != "match":
        raise Refused(f"the comparison's outcome is {comparison.get('outcome')}")
    return comparison


def fetch_workflow(job):
    try:
        # A fixed command. The job ID matched its pattern first.
        done = subprocess.run(  # noqa: S603
            [*KUBECTL, "get", "workflow", job, "-n", NAMESPACE, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Refused(f"the workflow: {error}") from None
    if done.returncode != 0:
        raise Refused(f"the workflow: {done.stderr.strip()[-300:]}")
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise Refused("the workflow is not JSON") from None


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Refused(f"{path.name}: {error}") from None


def case_of(contract):
    """The held-out case the job was collected for, or seed for the installed
    contract. The collect command keeps the contract, not the case's name."""
    facts = {f: contract.get(f) for f in CONTRACT_FIELDS}
    installed = read_json(CONTRACT)
    if facts == {f: installed.get(f) for f in CONTRACT_FIELDS}:
        return "seed"
    for name, case in read_json(CASES)["cases"].items():
        if facts == {f: case["contract"].get(f) for f in CONTRACT_FIELDS}:
            return name
    return "unknown"


def proposals_from(path):
    """An operator's proposals, in the comparison's shape."""
    found = read_json(Path(path))
    good = isinstance(found, list) and all(
        isinstance(p, dict)
        and set(p) == {"account", "action", "permission", "references"}
        and isinstance(p["account"], str)
        and ACCOUNT.fullmatch(p["account"])
        and p["action"] == "remove"
        and type(p["permission"]) is int
        and 0 < p["permission"] < 10**9
        and isinstance(p["references"], list)
        and all(isinstance(r, str) and REFERENCE.fullmatch(r) for r in p["references"])
        for p in found
    )
    if not good:
        raise Refused("the proposals file is not in the comparison's shape")
    return found


def permission_name(permission_id):
    """A permission's name in the live NetBox, read with the collector's token,
    for a permission the job's collection does not hold."""
    token = Path(netbox_access.TOKEN_DIR) / netbox_access.COLLECTOR
    netbox = netbox_change.client(netbox_access.URL, netbox_access.CERT, str(token))
    status, answer = netbox.call("GET", f"/api/users/permissions/{permission_id}/")
    if status != 200 or not isinstance(answer, dict):
        raise Refused(f"permission {permission_id}: {status} from NetBox")
    return answer.get("name")


def named(proposals, configured):
    """Each proposal as a change the rehearsal can apply by name."""
    held = {
        (account, p["id"]): p["name"]
        for account, found in configured["accounts"].items()
        for p in found["permissions"]
    }
    changes = []
    for proposal in proposals:
        key = (proposal["account"], proposal["permission"])
        name = held.get(key) or permission_name(proposal["permission"])
        if not (isinstance(name, str) and NAME.fullmatch(name)):
            raise Refused(f"permission {proposal['permission']}: a name out of pattern")
        changes.append(
            {
                "account": proposal["account"],
                "permission_id": proposal["permission"],
                "permission": name,
            }
        )
    return changes


def judged(changes, rules, contract):
    """A fix for the rules, judged without a staging test: each viewpoint's
    configured verdict once every change is made, as the policy judged each
    change alone."""
    result = {
        "method": "the rules judged without the change, no staging test",
        "verdicts": {},
        "passed": False,
        "reason": None,
    }
    network, left = contract["network"], rules["rules"]
    try:
        for change in changes:
            view = change["account"][len(netbox_rules.VIEWPOINT) :]
            left, _ = netbox_rules.change(left, network, view, change["priority"])
    except netbox_rules.Invalid as error:
        result["reason"] = str(error)
        return result
    for name, found in netbox_rules.configured(left, network).items():
        result["verdicts"][netbox_rules.VIEWPOINT + name] = {
            "configured": found["verdict"],
            "observed": "not tested",
        }
    expected = {
        netbox_rules.VIEWPOINT + name: "within" for name in network["viewpoints"]
    }
    got = {name: v["configured"] for name, v in result["verdicts"].items()}
    result["passed"] = got == expected
    if not result["passed"]:
        result["reason"] = "a viewpoint is not within without the change"
    return result


def rules_pr_body(bundle):
    rows, changes = bundle["comparison"]["accounts"], bundle["policy"]["changes"]
    change = {c["account"]: c for c in changes}
    lines = [
        f"## A fix for NetBox's port rules, from job `{bundle['job']}`",
        "",
        (
            "Both checks found a viewpoint that reaches NetBox's port although the "
            "contract says it should not. This change removes the rule that lets it "
            "in on NetBox's subnet, and the rule's outbound half on the viewpoint's "
            "subnet, as the policy allowed (platform ADRs 0043 and 0056). Every field "
            "below comes from the checks, the collection, or a pattern."
        ),
        "",
        "| Name | Checks | Model | Change |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        done = change.get(row["account"])
        what = (
            ", ".join(
                f"remove `{r['name']}` ({r['direction']}, {r['priority']}) from `{r['subnet']}`"
                for r in done["removed"]
            )
            if done
            else "none"
        )
        lines.append(
            f"| `{row['account']}` | {row['configured']}, {row['observed']} "
            f"| {row['model'] or '-'} | {what} |"
        )
    references = sorted(
        {r for p in bundle["comparison"]["proposals"] for r in p["references"]}
    )
    judgment = bundle["rehearsal"]["verdicts"]
    commit = changes[0]["commit"]
    lines += [
        "",
        f"- Job: `{bundle['job']}`, case `{bundle['case']}`, collected {bundle['collected']}.",
        f"- Proposed by: the {bundle['source']}.",
        f"- Evidence the change rests on: {', '.join(f'`{r}`' for r in references) or 'none named'}.",
        f"- Rules read at the targets commit `{commit}`.",
        "- Policy: allowed.",
        (
            "- No staging test: a security rule has no copy to change. The rules "
            "without the change, judged as the configured check judges them:"
        ),
        *[
            f"  - `{name}`: configured {found['configured']}"
            for name, found in sorted(judgment.items())
        ],
        "",
        (
            f"Approval: a tag `approve/netbox/{bundle['job']}` on this pull request's "
            "head commit, signed with the approval key (platform ADR 0046). The "
            "Approved commit check requires it before the merge. Delivery is the "
            "operator's apply of the merged commit, once its tree is the tagged "
            "commit's, and the connections from the viewpoints after it are the test."
        ),
        "",
    ]
    return "\n".join(lines)


def pr_body(bundle):
    rows, changes = bundle["comparison"]["accounts"], bundle["policy"]["changes"]
    change = {c["account"]: c for c in changes}
    lines = [
        f"## A fix for NetBox, from job `{bundle['job']}`",
        "",
        (
            "Both checks found an account with more access than its contract grants. "
            "This change removes the permission that gives it, as the policy allowed "
            "and a rehearsal on the copy confirmed (platform ADRs 0043 and 0044). "
            "Every field below comes from the checks, the collection, or a pattern."
        ),
        "",
        "| Account | Checks | Model | Change |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        done = change.get(row["account"])
        what = (
            f"remove `{done['permission']}` (ID {done['permission_id']})"
            if done
            else "none"
        )
        lines.append(
            f"| `{row['account']}` | {row['configured']}, {row['observed']} "
            f"| {row['model'] or '-'} | {what} |"
        )
    references = sorted(
        {r for p in bundle["comparison"]["proposals"] for r in p["references"]}
    )
    rehearsal = bundle["rehearsal"]["verdicts"]
    lines += [
        "",
        f"- Job: `{bundle['job']}`, case `{bundle['case']}`, collected {bundle['collected']}.",
        f"- Proposed by: the {bundle['source']}.",
        f"- Evidence the change rests on: {', '.join(f'`{r}`' for r in references) or 'none named'}.",
        "- Policy: allowed.",
        "- Rehearsal on the copy: every contract account within by both checks.",
        *[
            f"  - `{name}`: configured {found['configured']}, observed {found['observed']}"
            for name, found in sorted(rehearsal.items())
        ],
        "",
        (
            f"Approval: a tag `approve/netbox/{bundle['job']}` on this pull request's "
            "head commit, signed with the approval key (platform ADR 0046). Delivery "
            "checks NetBox after it applies the change, and the pull request merges "
            "only after that."
        ),
        "",
    ]
    return "\n".join(lines)


def delivered(job):
    """Whether a delivery of the job's fix passed."""
    result = DELIVERIES / f"approve_netbox_{job}.json"
    if not result.exists():
        return False
    found = read_json(result)
    return isinstance(found, dict) and found.get("passed") is True


def duplicate_of(proposals):
    """The earlier job whose allowed, rehearsed, and undelivered fix removes
    an account from a permission these proposals name too, or None."""
    wanted = {(p["account"], p["permission"]) for p in proposals}
    if not wanted or not PROPOSALS.is_dir():
        return None
    for earlier in sorted(PROPOSALS.iterdir()):
        if not (earlier / "pr-body.md").exists():
            continue
        bundle = read_json(earlier / "proposal.json")
        changes = (
            bundle.get("policy", {}).get("changes", [])
            if isinstance(bundle, dict)
            else []
        )
        held = {
            (c.get("account"), c.get("permission_id", c.get("priority")))
            for c in changes
            if isinstance(c, dict)
        }
        if held & wanted and not delivered(earlier.name):
            return earlier.name
    return None


def propose(job, operator=None):
    out = PROPOSALS / job
    if out.exists():
        raise Refused(f"{job} was proposed already")
    comparison = workflow_checked(fetch_workflow(job), job)
    collection = STATE / job
    configured = read_json(collection / "configured.json")
    contract = read_json(collection / "ev-0001.json")
    rules = (
        read_json(collection / "rules.json")
        if (collection / "rules.json").exists()
        else None
    )
    if operator is not None:
        comparison = dict(
            comparison, proposals=proposals_from(operator), unread_proposals=0
        )
    earlier = duplicate_of(comparison["proposals"])
    if earlier:
        raise Refused(
            f"{job}: the same fix as {earlier}, not delivered: deliver that one, "
            "or remove its bundle"
        )
    decision = policy.check(comparison, configured, contract, rules)
    viewpoint = [
        p
        for p in comparison["proposals"]
        if p["account"].startswith(netbox_rules.VIEWPOINT)
    ]
    if viewpoint:
        # A rule has no copy to change. Only an allowed fix is judged, as the
        # policy's changes are the rules it names.
        rehearsal = (
            judged(decision["changes"], rules, contract)
            if decision["allowed"]
            else {"passed": False, "reason": "the policy refused a fix for the rules"}
        )
    else:
        try:
            changes = named(comparison["proposals"], configured)
        except Refused as error:
            rehearsal = {"passed": False, "reason": str(error)}
        else:
            rehearsal = (
                rehearse.rehearse(changes, contract)
                if changes
                else {"passed": False, "reason": "no proposal to rehearse"}
            )
    bundle = {
        "job": job,
        "case": case_of(contract),
        "collected": contract.get("collected"),
        "source": "operator" if operator is not None else "model",
        "comparison": {
            key: comparison[key]
            for key in ("outcome", "accounts", "proposals", "unread_proposals")
        },
        "policy": decision,
        "rehearsal": rehearsal,
    }
    PROPOSALS.mkdir(mode=0o700, parents=True, exist_ok=True)
    out.mkdir(mode=0o700)
    (out / "proposal.json").write_text(json.dumps(bundle, indent=2) + "\n")
    good = decision["allowed"] and rehearsal.get("passed") is True
    if good:
        body = rules_pr_body(bundle) if viewpoint else pr_body(bundle)
        (out / "pr-body.md").write_text(body)
    return bundle, good


def main(argv):
    args = argv[1:]
    operator = None
    if len(args) == 3 and args[1] == "--proposals":
        operator = args[2]
    elif len(args) != 1:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    job = args[0]
    if not JOB_ID.fullmatch(job):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        bundle, good = propose(job, operator)
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(f"policy: {'allowed' if bundle['policy']['allowed'] else 'refused'}")
    for reason in bundle["policy"]["reasons"]:
        print(f"  {reason}")
    rehearsal = bundle["rehearsal"]
    print(f"rehearsal: {'passed' if rehearsal.get('passed') else 'failed'}")
    if rehearsal.get("reason"):
        print(f"  {rehearsal['reason']}")
    for name, found in sorted(rehearsal.get("verdicts", {}).items()):
        print(f"  {name}: {found['configured']}/{found['observed']}")
    print(f"bundle: {PROPOSALS / job}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
