#!/usr/bin/python3 -I
"""Delivers an approved NetBox change (ADR 0046).

    deliver-netbox-change TAG

Runs as root on the orchestrator, during a fetch window. It fetches the
targets repository into a mirror of its own, through Squid, and takes TAG, an
approve/netbox/NAME tag, only when the approval key signed it, its message
names NetBox as the target, it is at most a day old and not from the future,
and it was never used before. The tagged commit decides the mode:

- fix: a child of main's head that changes only the seed, and in it removes
  at least one account from a permission and adds none. NetBox's assignments
  must equal main's seed first, or nothing changes and the difference is
  printed.
- restore: main's head, the rollback.

The tag is written to the ledger before anything changes. Delivery then sets
each permission's users to the commit's seed, reads them back, and runs both
of the collector's methods against NetBox with the commit's contract. A fix
passes only when every contract account is within by both. A failed check
stops for the operator: nothing is rolled back by itself.

Exits 0 for a fix that passed its checks or a restore that was applied, 1 for
a refusal or a failure, and 2 for a call without a tag. The result goes to
/var/lib/aisec/delivery/results/. Standard library only.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "/usr/local/lib/aisec")

import collect_evidence as collection
import netbox_access

import netbox_change
import rehearse

STATE = Path(os.environ.get("AISEC_DELIVERY", "/var/lib/aisec/delivery"))
APPROVERS = Path(os.environ.get("AISEC_APPROVERS", "/etc/aisec/delivery/approvers"))
REMOTE = "https://github.com/sindredg/ai-security-platform-test.git"
PROXY = "http://10.45.0.4:3128"
TOKEN = "/etc/aisec/netbox/tokens/aisec-deliver"  # noqa: S105 - a file's path
GIT = "/usr/bin/git"
TAG = re.compile(r"approve/netbox/[a-z0-9][a-z0-9-]{0,62}")
MAX_AGE = 86400
MAX_AHEAD = 300
SEED = "netbox/seed.json"


class Refused(Exception):
    pass


def git(repo, *args, check=True):
    # Fixed commands. The tag matched its pattern, and commits are git's own.
    done = subprocess.run(  # noqa: S603
        [GIT, "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if check and done.returncode != 0:
        raise Refused(f"git {args[0]}: {done.stderr.strip()[-300:]}")
    return done


def fetch():
    repo = STATE / "targets.git"
    if not repo.exists():
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        git(STATE, "init", "-q", "--bare", repo.name)
        git(repo, "remote", "add", "origin", REMOTE)
    proxy = ["-c", f"http.proxy={PROXY}"] if PROXY else []
    git(
        repo,
        *proxy,
        "fetch",
        "-q",
        "--prune",
        "--tags",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
    )
    return repo


def verify_tag(repo, tag, approvers, now):
    """The tagged commit, the tag object, and when it was signed, if the tag is
    a usable approval."""
    ref = f"refs/tags/{tag}"
    signed = git(
        repo,
        "-c",
        f"gpg.ssh.allowedSignersFile={approvers}",
        "verify-tag",
        ref,
        check=False,
    )
    if signed.returncode != 0:
        raise Refused(f"{tag}: the signature is not the approval key's")
    text = git(repo, "cat-file", "tag", ref).stdout
    header, _, message = text.partition("\n\n")
    fields = dict(line.split(" ", 1) for line in header.splitlines() if " " in line)
    if fields.get("type") != "commit" or fields.get("tag") != tag:
        raise Refused(f"{tag}: not a tag of a commit by that name")
    if message.split("\n", 1)[0] != "target: netbox":
        raise Refused(f"{tag}: its message does not start with target: netbox")
    when = re.fullmatch(r".* ([0-9]{1,12}) [+-][0-9]{4}", fields.get("tagger", ""))
    if not when:
        raise Refused(f"{tag}: no tagger time")
    tagged_at = int(when[1])
    if now - tagged_at > MAX_AGE:
        raise Refused(
            f"{tag}: signed more than a day ago, older than an approval lasts"
        )
    if tagged_at - now > MAX_AHEAD:
        raise Refused(f"{tag}: signed {tagged_at - now} s ahead of this clock")
    tag_sha = git(repo, "rev-parse", ref).stdout.strip()
    ledger = STATE / "used"
    if ledger.exists() and tag_sha in ledger.read_text().split():
        raise Refused(f"{tag}: this approval was used already")
    return {"commit": fields["object"], "tag_sha": tag_sha, "tagged_at": tagged_at}


def seed_at(repo, commit):
    return json.loads(git(repo, "show", f"{commit}:{SEED}").stdout)


def mode(repo, commit):
    """fix, restore, or a refusal."""
    main = git(repo, "rev-parse", "refs/remotes/origin/main").stdout.strip()
    if commit == main:
        return "restore"
    parents = git(repo, "rev-list", "--parents", "-n", "1", commit).stdout.split()[1:]
    if parents != [main]:
        raise Refused("the commit is neither main's head nor a child of it")
    changed = git(repo, "diff", "--name-only", main, commit).stdout.split()
    if changed != [SEED]:
        raise Refused(f"the commit changes more than the seed: {', '.join(changed)}")
    old = netbox_change.seed_assignments(seed_at(repo, main))
    new = netbox_change.seed_assignments(seed_at(repo, commit))
    if old == new or not netbox_change.remove_only(old, new):
        raise Refused("the seed change removes nobody, or adds someone")
    return "fix"


def halves(contract):
    """Both methods' verdicts on the live NetBox, with the collect command's
    limits and checks."""
    text = json.dumps(contract)
    reports = {}
    for check, argv in (
        ("configured", [rehearse.PYTHON, "-I", rehearse.COLLECTOR, "configured"]),
        ("observed", rehearse.ssh(f"{rehearse.OBSERVE}/id_ed25519", "aisec-observe")),
    ):
        what = f"NetBox's {check} half"
        out = collection.run_half(argv, text, what)
        reports[check] = collection.report(out, check, contract, what)
    return {
        name: {check: reports[check]["accounts"][name]["verdict"] for check in reports}
        for name in contract["accounts"]
    }


def users(assignments):
    return {name: found["users"] for name, found in assignments.items()}


def deliver(tag, now=None):
    if not TAG.fullmatch(tag):
        raise Refused(f"{tag}: not an approval tag")
    repo = fetch()
    approval = verify_tag(repo, tag, APPROVERS, time.time() if now is None else now)
    commit = approval["commit"]
    chosen = mode(repo, commit)
    main = git(repo, "rev-parse", "refs/remotes/origin/main").stdout.strip()
    wanted = netbox_change.seed_assignments(seed_at(repo, commit))
    netbox = netbox_change.client(netbox_access.URL, netbox_access.CERT, TOKEN)
    live = netbox_change.live_assignments(netbox, sorted(wanted))
    if chosen == "fix":
        expected = netbox_change.seed_assignments(seed_at(repo, main))
        drift = [
            f"{name}: NetBox {found}, main's seed {expected.get(name)}"
            for name, found in sorted(users(live).items())
            if found != expected.get(name)
        ]
        if drift:
            raise Refused("NetBox differs from main's seed: " + "; ".join(drift))
    # Written before anything changes: a delivery that stops halfway has still
    # used its approval.
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(STATE / "used", "a") as ledger:
        ledger.write(approval["tag_sha"] + "\n")
    changes = netbox_change.plan(live, wanted)
    netbox_change.apply(netbox, changes)
    back = users(netbox_change.live_assignments(netbox, sorted(wanted)))
    result = {
        "tag": tag,
        "tag_sha": approval["tag_sha"],
        "commit": commit,
        "mode": chosen,
        "tagged_at": approval["tagged_at"],
        "delivered_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "applied": changes,
        "read_back": back == wanted,
        "verdicts": {},
        "passed": False,
    }
    if result["read_back"]:
        contract = json.loads(
            git(repo, "show", f"{commit}:netbox/contract.json").stdout
        )
        result["verdicts"] = halves(contract)
        within = all(
            v == {"configured": "within", "observed": "within"}
            for v in result["verdicts"].values()
        )
        result["passed"] = within if chosen == "fix" else True
    results = STATE / "results"
    results.mkdir(mode=0o700, parents=True, exist_ok=True)
    (results / f"{tag.replace('/', '_')}.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result


def main(argv):
    if len(argv) != 2:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        result = deliver(argv[1])
    except (
        Refused,
        netbox_change.Failed,
        collection.Failed,
        OSError,
        ValueError,
    ) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(f"{result['mode']} {result['commit'][:12]}, read back: {result['read_back']}")
    for change in result["applied"]:
        print(f"  {change['permission']}: {', '.join(change['users']) or 'nobody'}")
    for name, found in sorted(result["verdicts"].items()):
        print(f"  {name}: {found['configured']}/{found['observed']}")
    print("passed" if result["passed"] else "failed: stopped for the operator")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
