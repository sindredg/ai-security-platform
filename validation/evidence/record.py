"""Add one job's record to a run set's file, from what the live system kept.

    record.py SET WORKFLOW AUDIT [COLLECTED] [--proposal FILE] [--delivery FILE]... [--pr N]

SET is a run set's file under `docs/evidence/records/`. WORKFLOW is the job's
workflow as `argo get -o json` prints it. AUDIT holds lines of the tool
service's audit log, and only the job's own are read. COLLECTED, for a NetBox
job, is what `collect-netbox-evidence` printed. For a job whose fix was
proposed, --proposal is the bundle `propose-netbox-fix` wrote, each
--delivery a result `deliver-netbox-change` wrote, and --pr the number of
the fix's pull request in the targets repository.

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
from datetime import UTC, datetime
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


def proposal_record(bundle):
    """What a fix's bundle shows: who proposed it, the changes the policy
    named, its decision, and the rehearsal's verdicts. No answer text."""
    rehearsal = bundle["rehearsal"]
    return {
        "source": bundle["source"],
        "changes": bundle["policy"]["changes"],
        # What was proposed, the model's lines or the operator's file, as the
        # comparison read them: checked fields only.
        "proposed": [
            {k: p[k] for k in ("account", "action", "permission", "references")}
            for p in bundle["comparison"]["proposals"]
        ],
        "policy": {
            "allowed": bundle["policy"]["allowed"],
            "reasons": bundle["policy"]["reasons"],
        },
        "rehearsal": {
            "passed": rehearsal.get("passed") is True,
            "verdicts": rehearsal.get("verdicts") or {},
            "reason": rehearsal.get("reason"),
        },
    }


def delivery_record(result, pr):
    """A delivery's tag, its commit shortened, its mode, when the approval was
    signed, what changed, and the checks after it."""
    signed = datetime.fromtimestamp(result["tagged_at"], UTC)
    return {
        "tag": result["tag"],
        "commit": result["commit"][:12],
        "mode": result["mode"],
        "approved_at": signed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "applied": [
            {"permission": c["permission"], "users": c["users"]}
            for c in result["applied"]
        ],
        "verdicts": result["verdicts"],
        "passed": result["passed"],
        "pr": pr,
    }


def build(workflow, audit_lines, collection="", proposal=None, deliveries=(), pr=None):
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
    return (
        {
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
                {
                    k: comparison[k]
                    for k in (
                        "outcome",
                        "reasons",
                        "accounts",
                        "proposals",
                        "unread_proposals",
                    )
                    if k in comparison
                }
                if comparison
                else None
            ),
            "calls": calls(name, audit_lines, requests(result)),
            "answer": answer,
        }
        | ({"proposal": proposal_record(proposal)} if proposal else {})
        | (
            {"deliveries": [delivery_record(d, pr) for d in deliveries]}
            if deliveries
            else {}
        )
    )


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


def arguments(argv):
    """The positional arguments, and the options' values."""
    positional, options = [], {"--proposal": [], "--delivery": [], "--pr": []}
    args = iter(argv[1:])
    for arg in args:
        if arg in options:
            options[arg].append(next(args, None))
        else:
            positional.append(arg)
    if None in [v for values in options.values() for v in values]:
        return None
    if len(options["--proposal"]) > 1 or len(options["--pr"]) > 1:
        return None
    if not 3 <= len(positional) <= 4:
        return None
    return positional, options


def main(argv):
    parsed = arguments(argv)
    if parsed is None:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    positional, options = parsed
    set_path = Path(positional[0])
    run_set = json.loads(set_path.read_text())
    workflow = json.loads(Path(positional[1]).read_text())
    audit = Path(positional[2]).read_text().splitlines()
    collection = Path(positional[3]).read_text() if len(positional) == 4 else ""
    proposal = (
        json.loads(Path(options["--proposal"][0]).read_text())
        if options["--proposal"]
        else None
    )
    deliveries = [json.loads(Path(f).read_text()) for f in options["--delivery"]]
    pr = int(options["--pr"][0]) if options["--pr"] else None
    try:
        record = build(workflow, audit, collection, proposal, deliveries, pr)
    except ValueError as error:
        print(f"not written: {error}", file=sys.stderr)
        return 1
    run_set = add(run_set, record)
    set_path.write_text(json.dumps(run_set, indent=1, ensure_ascii=False) + "\n")
    print(f"{record['job']}: {record['phase']}, {len(record['calls'])} calls")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
