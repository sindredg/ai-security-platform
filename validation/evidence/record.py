"""Add one job's record to a run set's file, from what the live system kept.

    record.py SET WORKFLOW AUDIT [COLLECTED]

SET is a run set's file under `docs/evidence/records/`. WORKFLOW is the job's
workflow as `argo get -o json` prints it. AUDIT holds lines of the tool
service's audit log, and only the job's own are read. COLLECTED, for a NetBox
job, is what `collect-netbox-evidence` printed.

The record keeps what the evidence pages show and nothing else: the job's
limits but not its task, the workflow's phase and message, each step's
phase, message, and times, the result's counts, the checks' verdicts, the
comparison, the calls, and the answer. No transcript, address, token, or
error output.

The calls are the tool requests in the job's transcript, in order, each with
the tool service's decision from the audit log, matched by tool and by the
SHA-256 the service takes of the arguments. A request for one of Goose's own
tools has no audit line, and is kept as `goose`. A request the audit log lacks
is kept as `missing`. An audit line that no request matches is added at the
end, as for a job that ended without a transcript. A call's argument is the
reference with that SHA-256, or the arguments themselves.

When the job was compared, the checks' verdicts are the ones the comparison
read, and the collection's must be the same, or nothing is written. A record
with the same job name is replaced, and a note on it is kept. Standard
library only.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

RESULT_FIELDS = (
    "status",
    "seconds",
    "agent_status",
    "tool_calls",
    "tool_errors",
    "input_tokens",
    "output_tokens",
    "slot_erased",
)
CASE = re.compile(r"^\S+: case (\S+)$")
CHECK = r"([a-z0-9-]+):([a-z]+)/([a-z]+)"
CHECKS = re.compile(rf"^{CHECK}(?: {CHECK})*$")


def canonical(arguments):
    """The arguments as the tool service writes them before it hashes them."""
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"))


def digest(arguments):
    return hashlib.sha256(canonical(arguments).encode()).hexdigest()


REFERENCES = {
    digest({"reference": f"ev-{n:04d}"}): f"ev-{n:04d}" for n in range(1, 100)
}


def outputs(workflow):
    """Every output parameter of the workflow's nodes, by name."""
    found = {}
    for node in (workflow["status"].get("nodes") or {}).values():
        for param in (node.get("outputs") or {}).get("parameters") or []:
            found[param["name"]] = param.get("value")
    return found


def steps(workflow):
    nodes = (workflow["status"].get("nodes") or {}).values()
    pods = sorted(
        (n for n in nodes if n.get("type") == "Pod"),
        key=lambda n: n.get("startedAt") or "",
    )
    return [
        {
            "step": n.get("templateName") or n["displayName"],
            "phase": n.get("phase"),
            "message": n.get("message") or "",
            "started": n.get("startedAt"),
            "finished": n.get("finishedAt"),
        }
        for n in pods
    ]


def audited(job, lines):
    """The job's calls in the audit log, each with its arguments' hash."""
    found = []
    for line in lines:
        entry = json.loads(line)
        if entry.get("job") != job or entry.get("event") != "call":
            continue
        sha = entry.get("args_sha256") or ""
        found.append(
            {
                "at": entry["ts"],
                "tool": entry.get("tool"),
                "argument": REFERENCES.get(sha, f"sha256 {sha[:12]}"),
                "decision": entry["decision"],
                "reason": entry.get("reason"),
                "bytes": entry.get("result_bytes"),
                "sha": sha,
            }
        )
    return found


def requests(result):
    """The tool requests in the result's transcript, or None without one."""
    parts = (result or {}).get("transcript")
    if not isinstance(parts, list):
        return None
    found = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "toolRequest":
            try:
                found.append(json.loads(part.get("text") or ""))
            except ValueError:
                found.append({"name": "unreadable", "arguments": {}})
    return found


def calls(job, lines, asked=None):
    """What the model asked for, in order, with what the tool service did."""
    pending = audited(job, lines)
    found = []
    for request in asked or []:
        name = request.get("name") or ""
        arguments = request.get("arguments") or {}
        if name.startswith("tools__"):
            sha = digest(arguments)
            tool = name.removeprefix("tools__")
            match = next(
                (c for c in pending if c["tool"] == tool and c["sha"] == sha), None
            )
            if match:
                pending.remove(match)
                found.append(match)
                continue
            decision = "missing"
        else:
            tool, decision = name, "goose"
        found.append(
            {
                "at": None,
                "tool": tool,
                "argument": REFERENCES.get(digest(arguments), canonical(arguments)),
                "decision": decision,
                "reason": None,
                "bytes": None,
            }
        )
    return [{k: v for k, v in c.items() if k != "sha"} for c in found + pending]


def collected(text):
    case, checks = None, {}
    for line in text.splitlines():
        if match := CASE.match(line.strip()):
            case = match[1]
        elif CHECKS.match(line.strip()):
            for account, configured, observed in re.findall(CHECK, line):
                checks[account] = [configured, observed]
    return case, checks


def build(workflow, audit_lines, collection=""):
    name = workflow["metadata"]["name"]
    params = {
        p["name"]: p.get("value")
        for p in workflow["spec"].get("arguments", {}).get("parameters", [])
    }
    out = outputs(workflow)
    result = json.loads(out["result"]) if out.get("result") else None
    comparison = json.loads(out["comparison"]) if out.get("comparison") else None
    case, checks = collected(collection)
    if comparison:
        compared = {
            row["account"]: [row["configured"], row["observed"]]
            for row in comparison["accounts"]
        }
        if checks and checks != compared:
            raise ValueError(f"{name}: collected {checks}, compared {compared}")
        checks = compared
    if result is not None:
        answer = result.get("answer", out.get("answer")) or ""
    else:
        answer = out.get("answer")
    return {
        "job": name,
        "target": params.get("target"),
        "case": case,
        "limits": {
            "seconds": int(params["seconds"]) if params.get("seconds") else None,
            "turns": int(params["max-turns"]) if params.get("max-turns") else None,
        },
        "started": workflow["status"].get("startedAt"),
        "finished": workflow["status"].get("finishedAt"),
        "phase": workflow["status"].get("phase"),
        "message": workflow["status"].get("message") or "",
        "steps": steps(workflow),
        "result": {k: result.get(k) for k in RESULT_FIELDS} if result else None,
        "checks": checks or None,
        "comparison": (
            {k: comparison[k] for k in ("outcome", "reasons", "accounts")}
            if comparison
            else None
        ),
        "calls": calls(name, audit_lines, requests(result)),
        "answer": answer,
    }


def add(run_set, record):
    """The run set with the record in it, in order of start, any note kept."""
    old = {j["job"]: j for j in run_set.get("jobs", [])}
    if note := old.get(record["job"], {}).get("note"):
        record = {**record, "note": note}
    jobs = [j for name, j in old.items() if name != record["job"]] + [record]
    return {
        **run_set,
        "jobs": sorted(jobs, key=lambda j: j["started"] or j["finished"] or ""),
    }


def main(argv):
    if len(argv) not in (4, 5):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    set_path = Path(argv[1])
    run_set = json.loads(set_path.read_text())
    workflow = json.loads(Path(argv[2]).read_text())
    audit = Path(argv[3]).read_text().splitlines()
    collection = Path(argv[4]).read_text() if len(argv) == 5 else ""
    try:
        record = build(workflow, audit, collection)
    except ValueError as error:
        print(f"not written: {error}", file=sys.stderr)
        return 1
    run_set = add(run_set, record)
    set_path.write_text(json.dumps(run_set, indent=2, ensure_ascii=False) + "\n")
    print(f"{record['job']}: {record['phase']}, {len(record['calls'])} calls")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
