#!/usr/bin/python3 -I
"""Collects one job's NetBox evidence on the orchestrator (ADR 0040).

    collect-netbox-evidence JOB

Runs the configured half here, with the collector's token, and the observed
half on the lab VM, through the observer account's forced command. Both get
the contract on standard input. What comes back is checked against the
contract's accounts before anything is written: the lab VM is target side.

The job gets the facts the verdicts rest on, in three documents: ev-0001 the
contract, ev-0002 the configured permissions, ev-0003 the records each read
returns and each denial's status. Names, reasons, and other free text from
NetBox are left out. The verdicts and both full reports stay here, under the
job's directory, for the workflow's comparison and for the operator.

The documents go into the tool service's ConfigMap for NetBox, keyed
`JOB.REFERENCE.json`, which the pod mounts as a directory. The command then
waits until the kubelet has put them there. A job ID is collected once.

Standard library only.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

STATE = Path(os.environ.get("AISEC_STATE", "/var/lib/aisec/evidence/netbox"))
CONTRACT = Path(os.environ.get("AISEC_CONTRACT", "/etc/aisec/netbox/contract.json"))
COLLECTOR = os.environ.get("AISEC_COLLECTOR", "/usr/local/lib/aisec/netbox_access.py")
SSH = os.environ.get("AISEC_SSH", "/usr/bin/ssh")
KUBECTL = os.environ.get("AISEC_KUBECTL", "/usr/local/bin/k3s kubectl").split()
KUBELET = Path(os.environ.get("AISEC_KUBELET", "/var/lib/kubelet"))
WAIT = int(os.environ.get("AISEC_WAIT", "180"))

KEY = "/etc/aisec/netbox/observe/id_ed25519"
KNOWN_HOSTS = "/etc/aisec/netbox/observe/known_hosts"
LAB = "aisec-observe@10.50.0.36"
NAMESPACE = "tool-services"
CONFIGMAP = "tool-service-evidence-netbox"
VOLUME = "evidence-netbox"
POD = "app.kubernetes.io/name=tool-service"
KEEP_JOBS = 20
JOB_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
VERDICTS = ("excess", "missing", "unknown", "within")


class Failed(Exception):
    pass


def run(argv, stdin, what, timeout=120):
    try:
        # Fixed commands. No argument comes from a report or the job ID.
        done = subprocess.run(  # noqa: S603
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Failed(f"{what}: {error}") from None
    if done.returncode != 0:
        raise Failed(f"{what}: exit {done.returncode}: {done.stderr.strip()[-300:]}")
    return done.stdout


def report(text, check, contract, what):
    """The collector's report, if it has the contract's accounts and the
    shape of its check. A report from the lab VM is target side."""
    try:
        found = json.loads(text)
    except ValueError:
        raise Failed(f"{what}: not JSON") from None
    if not isinstance(found, dict) or found.get("check") != check:
        raise Failed(f"{what}: not a report of the {check} check")
    accounts = found.get("accounts")
    if not isinstance(accounts, dict) or set(accounts) != set(contract["accounts"]):
        raise Failed(f"{what}: not the contract's accounts")
    for name, account in accounts.items():
        if not isinstance(account, dict) or account.get("verdict") not in VERDICTS:
            raise Failed(f"{what}: {name} has no verdict")
        if check == "configured":
            good = isinstance(account.get("permissions"), list) and all(
                isinstance(p, dict)
                and type(p.get("id")) is int
                and isinstance(p.get("object_types"), list)
                and isinstance(p.get("actions"), list)
                and isinstance(p.get("via"), str)
                for p in account["permissions"]
            )
        else:
            reads, denials = account.get("reads"), account.get("denials")
            good = (
                isinstance(reads, dict)
                and all(isinstance(r, list) for r in reads.values())
                and isinstance(denials, list)
                and all(
                    isinstance(d, dict) and type(d.get("status")) is int
                    for d in denials
                )
            )
        if not good:
            raise Failed(f"{what}: {name} is not in the {check} report's shape")
    return found


def header(reference, job, collected):
    return {"reference": reference, "job": job, "collected": collected}


def facts_contract(contract, job, collected):
    fields = ("accounts", "viewpoint", "grants", "reads", "denials")
    return header("ev-0001", job, collected) | {f: contract[f] for f in fields}


def facts_configured(configured, job, collected):
    accounts = {
        name: {
            "permissions": [
                {
                    "id": p["id"],
                    "object_types": p["object_types"],
                    "actions": p["actions"],
                    "constraints": p.get("constraints"),
                    # "group <name>": the group's name is NetBox's text.
                    "via": "user" if p["via"] == "user" else "group",
                }
                for p in account["permissions"]
            ]
        }
        for name, account in configured["accounts"].items()
    }
    return header("ev-0002", job, collected) | {"accounts": accounts}


def facts_observed(observed, job, collected):
    accounts = {
        name: {
            "reads": account["reads"],
            "denials": [
                {
                    "method": d.get("method"),
                    "path": d.get("path"),
                    "status": d["status"],
                }
                for d in account["denials"]
            ],
        }
        for name, account in observed["accounts"].items()
    }
    return header("ev-0003", job, collected) | {"accounts": accounts}


def verdicts(configured, observed):
    return {
        name: {
            "configured": configured["accounts"][name]["verdict"],
            "observed": observed["accounts"][name]["verdict"],
        }
        for name in configured["accounts"]
    }


def write(path, document):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(document, file, indent=2)
        file.write("\n")


def collected_at(data, job):
    try:
        return json.loads(data[f"{job}.ev-0001.json"])["collected"]
    except (KeyError, ValueError, TypeError):
        return ""


def store(job, documents):
    """Adds the job's keys to the ConfigMap, and keeps the newest jobs.

    The replace carries the resourceVersion it read, so a change made in
    between fails the replace instead of being lost."""
    get = [*KUBECTL, "-n", NAMESPACE, "get", "configmap", CONFIGMAP, "-o", "json"]
    configmap = json.loads(run(get, None, "reading the ConfigMap"))
    data = configmap.get("data") or {}
    for reference, document in documents.items():
        data[f"{job}.{reference}.json"] = json.dumps(document, indent=2)
    jobs = sorted(
        {key.split(".", 1)[0] for key in data},
        key=lambda name: collected_at(data, name),
        reverse=True,
    )
    for gone in jobs[KEEP_JOBS:]:
        for key in [k for k in data if k.split(".", 1)[0] == gone]:
            del data[key]
    configmap["data"] = data
    replace = [*KUBECTL, "replace", "-f", "-"]
    run(replace, json.dumps(configmap), "writing the ConfigMap")


def wait_visible(job):
    """Seconds until every tool service pod's volume holds the job's keys."""
    get = [*KUBECTL, "-n", NAMESPACE, "get", "pod", "-l", POD]
    uids = run([*get, "-o", "jsonpath={.items[*].metadata.uid}"], None, "pods").split()
    if not uids:
        raise Failed("no tool service pod")
    volume = Path("volumes", "kubernetes.io~configmap", VOLUME)
    paths = [KUBELET / "pods" / uid / volume / f"{job}.ev-0003.json" for uid in uids]
    start = time.monotonic()
    while not all(path.is_file() for path in paths):
        if time.monotonic() - start > WAIT:
            raise Failed(
                f"not visible to the tool service after {WAIT} s. The evidence "
                f"is in the ConfigMap and in {STATE / job}"
            )
        time.sleep(1)
    return round(time.monotonic() - start)


def collect(job):
    if not JOB_ID.fullmatch(job):
        raise Failed("not a job ID")
    if (STATE / job).exists():
        raise Failed(f"{job} already collected")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    sent = json.dumps(contract)
    halves = {
        "configured": [sys.executable, "-I", COLLECTOR, "configured"],
        "observed": [SSH, "-F", "none", "-i", KEY, "-o", "IdentitiesOnly=yes"]
        + ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
        + ["-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-T", LAB],
    }
    reports = {
        check: report(run(argv, sent, check), check, contract, check)
        for check, argv in halves.items()
    }
    collected = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    documents = {
        "ev-0001": facts_contract(contract, job, collected),
        "ev-0002": facts_configured(reports["configured"], job, collected),
        "ev-0003": facts_observed(reports["observed"], job, collected),
    }
    found = verdicts(reports["configured"], reports["observed"])
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        (STATE / job).mkdir(mode=0o700)
    except FileExistsError:
        raise Failed(f"{job} already collected") from None
    for name, document in (
        ("verdicts.json", found),
        ("configured.json", reports["configured"]),
        ("observed.json", reports["observed"]),
        *((f"{ref}.json", doc) for ref, doc in documents.items()),
    ):
        write(STATE / job / name, document)
    store(job, documents)
    seconds = wait_visible(job)
    print(
        f"{job}: ev-0001 ev-0002 ev-0003, visible to the tool service after {seconds} s"
    )
    print(" ".join(f"{a}:{v['configured']}/{v['observed']}" for a, v in found.items()))


def main(argv):
    if len(argv) != 2:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        collect(argv[1])
    except Failed as error:
        print(f"failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
