"""The rehearsal of an allowed fix on the copy (ADR 0044).

A library on the orchestrator host, beside the collector and the collect
command, whose limits on a half it reuses. It resets the copy on the lab VM
to the seed, applies the fix there by the permissions' names, since the copy's
IDs are its own, and runs both of the collector's methods against the copy:
the configured half here, and the observed half through the observer with the
word rehearsal. The fix passes when every contract account is within by both.

The copy is target side, and so are its answers and the lab VM's report. A
passed rehearsal is evidence that the fix keeps the contract, not proof: the
proof is the check after delivery (ADR 0046). Standard library only.
"""

import json
import os
from pathlib import Path

import collect_evidence as collection

import netbox_change

COPY_URL = "https://10.50.1.4:8443"
# The copy's certificate, its collector's and delivery tokens, and the reset
# key with the dump's SHA-256. The tests point these at a temporary directory.
COPY = Path(os.environ.get("AISEC_COPY", "/etc/aisec/netbox-rehearsal"))
SSH = os.environ.get("AISEC_SSH", "/usr/bin/ssh")
PYTHON = os.environ.get("AISEC_PYTHON", "/usr/bin/python3")
COLLECTOR = os.environ.get("AISEC_COLLECTOR", "/usr/local/lib/aisec/netbox_access.py")
LAB = "10.50.0.36"
# The reset restores the database and waits up to five minutes for NetBox.
RESET_SECONDS = 360
OBSERVE = "/etc/aisec/netbox/observe"


def ssh(key, user, *command):
    """A fixed command on the lab VM, through an account's forced command."""
    return [
        SSH,
        "-F",
        "none",
        "-i",
        str(key),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={OBSERVE}/known_hosts",
        "-T",
        f"{user}@{LAB}",
        *command,
    ]


def reset():
    """Resets the copy, and returns the dump's SHA-256 the reset printed."""
    out = collection.run(
        ssh(COPY / "reset" / "id_ed25519", "aisec-rehearse"),
        "",
        "the copy's reset",
        timeout=RESET_SECONDS,
    )
    lines = out.strip().splitlines()
    got = lines[-1] if lines else ""
    want = (COPY / "reset" / "seed.sha256").read_text().strip()
    if got != want:
        raise collection.Failed(
            f"the copy's reset restored {got or 'nothing'}, not the seed's dump {want}"
        )
    return got


def wanted_users(live, changes):
    """Each changed permission's users on the copy, without the fix's account."""
    wanted = {name: list(found["users"]) for name, found in live.items()}
    for change in changes:
        users = wanted[change["permission"]]
        if change["account"] not in users:
            raise collection.Failed(
                f"{change['permission']}: {change['account']} does not hold it on the copy"
            )
        users.remove(change["account"])
    return wanted


def halves(contract):
    """Both methods' reports from the copy, checked as the collect command
    checks a job's."""
    text = json.dumps(contract)
    copy_env = [
        "/usr/bin/env",
        f"AISEC_NETBOX_URL={COPY_URL}",
        f"AISEC_NETBOX_CERT={COPY / 'tls.crt'}",
        f"AISEC_NETBOX_TOKENS={COPY / 'tokens'}",
    ]
    what = "the copy's configured half"
    out = collection.run_half(
        [*copy_env, PYTHON, "-I", COLLECTOR, "configured"], text, what
    )
    configured = collection.report(out, "configured", contract, what)
    what = "the copy's observed half"
    out = collection.run_half(
        ssh(f"{OBSERVE}/id_ed25519", "aisec-observe", "rehearsal"), text, what
    )
    observed = collection.report(out, "observed", contract, what)
    return configured, observed


def rehearse(changes, contract):
    """The rehearsal's result: the reset, the changes made on the copy, both
    methods' verdicts for each contract account, whether all are within, and
    why not when it stopped short. Once the copy's first reset is done, it is
    reset again whatever happens after it, so the copy rests at the seed."""
    result = {
        "reset": None,
        "applied": [],
        "verdicts": {},
        "passed": False,
        "reason": None,
        "reset_after": None,
    }
    try:
        result["reset"] = reset()
    except (collection.Failed, netbox_change.Failed, OSError) as error:
        result["reason"] = str(error)
        return result
    try:
        copy = netbox_change.client(
            COPY_URL, str(COPY / "tls.crt"), str(COPY / "tokens" / "aisec-deliver")
        )
        names = sorted({change["permission"] for change in changes})
        live = netbox_change.live_assignments(copy, names)
        applied = netbox_change.plan(live, wanted_users(live, changes))
        netbox_change.apply(copy, applied)
        result["applied"] = applied
        configured, observed = halves(contract)
    except (collection.Failed, netbox_change.Failed, OSError) as error:
        result["reason"] = str(error)
    finally:
        # The copy rests at the seed between rehearsals, so a failure in
        # between does not leave the change on it (#216).
        try:
            result["reset_after"] = reset()
        except (collection.Failed, OSError) as error:
            after = f"the reset after it: {error}"
            result["reason"] = (
                f"{result['reason']}; {after}" if result["reason"] else after
            )
    if result["reason"]:
        return result
    result["verdicts"] = {
        name: {
            "configured": configured["accounts"][name]["verdict"],
            "observed": observed["accounts"][name]["verdict"],
        }
        for name in contract["accounts"]
    }
    result["passed"] = all(
        found["configured"] == found["observed"] == "within"
        for found in result["verdicts"].values()
    )
    return result
