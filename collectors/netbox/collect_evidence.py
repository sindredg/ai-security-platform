#!/usr/bin/python3 -I
"""Collects one job's NetBox evidence on the orchestrator (ADR 0040).

    collect-netbox-evidence JOB [CASE]

Runs the configured half here, with the collector's token, and the observed
half on the lab VM, through the observer account's forced command. Both get
the contract on standard input. Both answers are target side, NetBox's and
the lab VM's: each half gets a megabyte and two minutes, and what comes back
has to name the contract's accounts, and no read or denial the contract does
not, before anything is written. The contract is the installed one, or with
CASE that held-out case's, from the installed case file (ADR 0042).

The job gets the facts the verdicts rest on, in three documents: ev-0001 the
contract, ev-0002 the configured permissions, ev-0003 the records each read
returns and each denial's status. Names, reasons, and other free text from
NetBox are left out. The verdicts and both full reports stay here, under the
job's directory, for the workflow's comparison and for the operator.

The documents go into the tool service's ConfigMap for NetBox, keyed
`JOB.REFERENCE.json`, which the pod mounts as a directory. The verdicts go
into the ConfigMap `netbox-verdicts` in `orchestration`, keyed `JOB.json`,
where the workflow's comparison step reads its own job's key (ADR 0041). The
command then waits until the kubelet has put the documents in the tool
service's directory. A job ID is collected once.

Standard library only.
"""

import json
import os
import re
import selectors
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

STATE = Path(os.environ.get("AISEC_STATE", "/var/lib/aisec/evidence/netbox"))
CONTRACT = Path(os.environ.get("AISEC_CONTRACT", "/etc/aisec/netbox/contract.json"))
CASES = Path(os.environ.get("AISEC_CASES", "/etc/aisec/netbox/cases.json"))
COLLECTOR = os.environ.get("AISEC_COLLECTOR", "/usr/local/lib/aisec/netbox_access.py")
SSH = os.environ.get("AISEC_SSH", "/usr/bin/ssh")
KUBECTL = os.environ.get("AISEC_KUBECTL", "/usr/local/bin/k3s kubectl").split()
KUBELET = Path(os.environ.get("AISEC_KUBELET", "/var/lib/kubelet"))
WAIT = int(os.environ.get("AISEC_WAIT", "180"))
# How long each half may take. NetBox and the lab VM are target side, and
# neither chooses how long the orchestrator waits for its answer.
TIMEOUT = int(os.environ.get("AISEC_TIMEOUT", "120"))

KEY = "/etc/aisec/netbox/observe/id_ed25519"
KNOWN_HOSTS = "/etc/aisec/netbox/observe/known_hosts"
LAB = "aisec-observe@10.50.0.36"
NAMESPACE = "tool-services"
CONFIGMAP = "tool-service-evidence-netbox"
# The comparison step's, which no job reads (ADR 0041).
VERDICTS_NAMESPACE = "orchestration"
VERDICTS_CONFIGMAP = "netbox-verdicts"
VOLUME = "evidence-netbox"
POD = "app.kubernetes.io/name=tool-service"
KEEP_JOBS = 20
# The tool service's limits.result_bytes. A document over it would reach no
# job, so it fails here. A tool service test holds the two equal.
RESULT_BYTES = 16384
# A report is a few kilobytes. Far more is not a report, and is not held.
OUTPUT_BYTES = 1 << 20
JOB_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
CASE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
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


def run_half(argv, stdin, what):
    """A half's report, as NetBox's answers and the lab VM shape it.

    Past OUTPUT_BYTES on either stream, or TIMEOUT seconds, the half is
    stopped, and the collection fails before it writes anything."""
    deadline = time.monotonic() + TIMEOUT
    try:
        # Fixed commands. No argument comes from a report or the job ID.
        half = subprocess.Popen(  # noqa: S603
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise Failed(f"{what}: {error}") from None
    read = {half.stdout: bytearray(), half.stderr: bytearray()}
    with half, selectors.DefaultSelector() as selector:
        try:
            # The contract is a few kilobytes, less than a pipe holds, so
            # this does not wait for the half to read it.
            half.stdin.write(stdin.encode())
            half.stdin.close()
        except BrokenPipeError:
            pass
        for stream in read:
            selector.register(stream, selectors.EVENT_READ)
        try:
            while selector.get_map():
                left = deadline - time.monotonic()
                ready = selector.select(left) if left > 0 else []
                if not ready:
                    raise Failed(f"{what}: no answer in {TIMEOUT} s")
                for key, _ in ready:
                    chunk = os.read(key.fd, 1 << 16)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(read[key.fileobj]) + len(chunk) > OUTPUT_BYTES:
                        raise Failed(f"{what}: more than {OUTPUT_BYTES} bytes")
                    else:
                        read[key.fileobj] += chunk
            code = half.wait(max(deadline - time.monotonic(), 0))
        except subprocess.TimeoutExpired:
            half.kill()
            raise Failed(f"{what}: no answer in {TIMEOUT} s") from None
        except Failed:
            half.kill()
            raise
    if code != 0:
        error = read[half.stderr].decode(errors="replace").strip()[-300:]
        raise Failed(f"{what}: exit {code}: {error}")
    return bytes(read[half.stdout])


def report(text, check, contract, what):
    """The collector's report, if it has the contract's accounts, the shape
    of its check, and no read or denial the contract does not name. A report
    from the lab VM is target side, and so is NetBox's part in either."""
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
                # A read NetBox refused has no path here, and says missing.
                and set(reads) <= {r["path"] for r in contract["reads"]}
                and all(isinstance(r, list) for r in reads.values())
                and isinstance(denials, list)
                and all(
                    isinstance(d, dict) and type(d.get("status")) is int
                    for d in denials
                )
                and [(d.get("method"), d.get("path")) for d in denials]
                == [(d["method"], d["path"]) for d in contract["denials"]]
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
    """When the job was collected, from the first of its documents that says."""
    for key, value in data.items():
        if key.split(".", 1)[0] != job:
            continue
        try:
            collected = json.loads(value)["collected"]
        except (KeyError, ValueError, TypeError):
            continue
        if isinstance(collected, str):
            return collected
    return ""


def verdicts_document(job, collected, found):
    return {"job": job, "collected": collected, "accounts": found}


def store(namespace, name, entries):
    """Adds the entries to a ConfigMap, and keeps the newest jobs' keys.

    The replace carries the resourceVersion it read, so a change made in
    between fails the replace instead of being lost."""
    get = [*KUBECTL, "-n", namespace, "get", "configmap", name, "-o", "json"]
    configmap = json.loads(run(get, None, f"reading the ConfigMap {name}"))
    data = configmap.get("data") or {}
    data.update(entries)
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
    run(replace, json.dumps(configmap), f"writing the ConfigMap {name}")


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


def contract_for(case):
    """The installed contract, or the held-out case's from the case file."""
    if case is None:
        return json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not CASE.fullmatch(case):
        raise Failed("not a case name")
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    if case not in cases:
        raise Failed(f"no case {case}")
    return cases[case]["contract"]


def collect(job, case=None):
    if not JOB_ID.fullmatch(job):
        raise Failed("not a job ID")
    if (STATE / job).exists():
        raise Failed(f"{job} already collected")
    contract = contract_for(case)
    if case is not None:
        print(f"{job}: case {case}", flush=True)
    sent = json.dumps(contract)
    halves = {
        "configured": [sys.executable, "-I", COLLECTOR, "configured"],
        "observed": [SSH, "-F", "none", "-i", KEY, "-o", "IdentitiesOnly=yes"]
        + ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
        + ["-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-T", LAB],
    }
    reports = {
        check: report(run_half(argv, sent, check), check, contract, check)
        for check, argv in halves.items()
    }
    collected = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    documents = {
        "ev-0001": facts_contract(contract, job, collected),
        "ev-0002": facts_configured(reports["configured"], job, collected),
        "ev-0003": facts_observed(reports["observed"], job, collected),
    }
    for reference, document in documents.items():
        size = len(json.dumps(document, indent=2, sort_keys=True).encode())
        if size > RESULT_BYTES:
            raise Failed(
                f"{reference} is larger than the tool service hands back: "
                f"{size} bytes, the limit is {RESULT_BYTES}"
            )
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
    store(
        NAMESPACE,
        CONFIGMAP,
        {
            f"{job}.{reference}.json": json.dumps(document, indent=2)
            for reference, document in documents.items()
        },
    )
    checks = verdicts_document(job, collected, found)
    store(
        VERDICTS_NAMESPACE,
        VERDICTS_CONFIGMAP,
        {f"{job}.json": json.dumps(checks, indent=2)},
    )
    seconds = wait_visible(job)
    print(
        f"{job}: ev-0001 ev-0002 ev-0003, visible to the tool service after {seconds} s"
    )
    print(" ".join(f"{a}:{v['configured']}/{v['observed']}" for a, v in found.items()))
    print(f"verdicts for the comparison in {VERDICTS_NAMESPACE}/{VERDICTS_CONFIGMAP}")


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        collect(argv[1], argv[2] if len(argv) == 3 else None)
    except Failed as error:
        print(f"failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
