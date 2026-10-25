# 0040. A job's evidence is collected on the hosts and stored per job in the tool service

Status: Proposed
Date: 2026-10-25

## Context

The workflow's first step collects evidence, and the AI worker reads it through the tool service ([architecture](../architecture.md#workflow)). For exercise 1 the collector exists. `collectors/netbox/netbox_access.py` reads what each account in the consumer contract may see: the configured half on the orchestrator with the collector's token, the observed half on the lab VM with each account's own token ([0037](0037-an-unscoped-copy-of-the-consumers-permission.md)). Only the checks run it, from the workstation over SSH (`N.14`, `N.17`).

Three things stand between that and a job:

- **No pod reaches NetBox.** The host rule drops forwarded pod traffic to anything outside the cluster except the worker's SSH port, and pod traffic to the host except the API server and the kubelet ([0018](0018-a-host-rule-keeps-pods-off-the-internet.md), [0023](0023-the-host-rule-limits-what-pods-reach-on-the-host.md)). The tool service pod has no egress at all ([0014](0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)).
- **The evidence store is per target.** `get_evidence` reads `<target>/<reference>.json`, so two jobs on one target read the same files ([#45](https://github.com/sindredg/ai-security-platform/issues/45)).
- **The evidence tool returns the stored file as it is.** Any field reaches the model. In the model comparison, Qwen3.5-4B followed text injected into an extra field and into a list value ([#152](https://github.com/sindredg/ai-security-platform/issues/152)).

The job ID is the workflow's name. The dispatch step names one target, `synthetic`.

## Options

| Option | What it gives | What it costs |
| --- | --- | --- |
| The hosts collect, as the checks do, and the orchestrator writes a snapshot per job into the tool service's store | No network rule changes. The collector's token stays where it is | Collection runs before the workflow, not in it. One more orchestrator key into the lab VM |
| A collector pod in the workflow | Collection is a workflow step | Host rule exceptions for NetBox's port and the lab VM's SSH. The rule cannot tell pods apart, so every pod reaches both. The collector's token becomes a cluster secret |
| The tool service asks NetBox during the job | The model can ask for fresh answers | Outbound access and a NetBox token in the component that parses the worker's input. The target's answers reach the model as NetBox sends them |
| The workstation runs both halves, as the checks do, and uploads the snapshot | Nothing new on the lab VM | The operator's machine carries every snapshot, and no collection runs without an operator session |

## Decision

The hosts collect, and the tool service stores the snapshot per job.

1. **A command on the orchestrator collects for one job.** `collect-netbox-evidence JOB` runs as root. It runs the configured half itself, with the collector's token, and the observed half on the lab VM. It refuses a job ID it has collected for before.
2. **The lab VM runs the observed half for the orchestrator only.** A new account there follows the update account of [0036](0036-target-packages-through-a-port-the-orchestrator-forwards.md): a key file that root owns, the orchestrator's address and `restrict` on the key line, no forwarding, no TTY, and a forced command that runs an installed copy of the collector through sudo, for that one command. The orchestrator sends the contract on standard input. The check run compares the installed copy, and the orchestrator's copy of the contract, with the files in the two repositories.
3. **The snapshot holds the facts, not the verdicts.** For each account: each permission's ID, object types, actions, and constraints, and whether it comes through the user or a group. The records each read returns, by the contract's key for them: a device's name, an address. The status of each expected denial. The contract's grants, reads, and denials go with them. Permission and group names, descriptions, comments, and other free text from NetBox are left out. A record's key is NetBox's text too, so the schema holds it to a pattern. The verdicts and their reasons stay on the orchestrator beside the snapshot, for the workflow's comparison. The job never reads them.
4. **The store is per job.** The command writes the snapshot into a ConfigMap for the target, keyed by the job ID and the reference. The tool service mounts it as a directory of its own, so a new key appears without a restart. `get_evidence` reads only the keys named for the job's own ID, which comes from the job's registered scope, never from the call (#45).
5. **The tool hands the model only what its schema names.** The policy gives each kind of evidence a schema: its fields, and a pattern for each value. A file with another field, or a value outside its pattern, is refused with the tool's own message (#152).
6. **On request.** The operator runs the command, then submits the workflow with its name set to the same job ID. The workflow passes the target to the dispatch step, and the policy lists NetBox's target with the evidence tool.

## Trade-offs

- **Collection is not a workflow step.** A job starts from a collection the operator ran first. A schedule, or a workflow that starts its own collection, needs a host rule exception or a trigger on the host, in a new record.
- **The job ID is the operator's choice.** Argo refuses a second workflow under a live name, the tool service refuses a job ID it still holds, until an hour after that job expires or until it restarts, and the command refuses an ID it has used. A workflow submitted under another name than the collection's finds no evidence, and its job fails.
- **The orchestrator gets a second key into the lab VM.** A compromised orchestrator can run the observed half at will. It already holds the collector's token and the update key, and the forced command runs nothing else.
- **The observed half parses NetBox's answers as root on the lab VM,** as the checks already do. The collector follows no link and no redirect, and builds every URL itself.
- **The model sees no free-text field, which is not the same as no words.** A record's key or a constraint can still carry words joined by hyphens, dots, or underscores, inside its pattern. If a finding rests on a name or a description, the schema has to name that field, and #152's injection risk comes back in full.
- **The model does not get the verdicts,** so its verdict is its own and the comparison means something. How the workflow reads the orchestrator's verdicts is decided with the comparison step.
- **A ConfigMap holds at most 1 MiB.** The command removes the oldest jobs' keys from it. The orchestrator keeps every snapshot.
- **The transcript keeps what the job read** for 24 hours ([0030](0030-how-a-job-reaches-the-worker.md)). NetBox's inventory is synthetic, so that rule still holds.
- **Not seen:** a new key in a ConfigMap reaching a running pod's mounted directory, and how long that takes. `argo submit --from` with `--name` under the template restriction. Standard input through a forced command that runs sudo.
