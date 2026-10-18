# Audit log

Where the tool service's audit lines are stored, and who can change them. What a line holds is on the [tool service](tool-service.md#the-audit-line) page. The design is ADRs [0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) and [0019](../decisions/0019-how-the-audit-lines-and-the-worker-journal-are-copied.md).

State: **Verified** on 2026-10-16. The copier, its unit, and its install script are in `platform/logs/` and the orchestrator's first-boot template. It runs on the orchestrator, and each check was seen to fail, on a broken condition or before the install ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)). The checks are `L.1` to `L.7` on [validation](../validation/audit-log.md).

The worker's journal is the second log in ADR 0019. See [the worker's journal](#the-workers-journal) below.

![The two copies on the orchestrator: the tool service pod writes audit lines to standard output, the container runtime keeps them in the pod log, and the audit copier reads that log every two seconds and appends each line to an append-only audit file. The journal pull asks the worker's forced export command for journal lines after a saved cursor, over SSH every five minutes, and appends them to an append-only journal file. The orchestrator's log agent sends each line of both files over Private Link to a Log Analytics workspace where no VM holds a role](../diagrams/log-copies.svg)

The diagram source is [`diagrams/log-copies.html`](../diagrams/log-copies.html).

## The path of a line

1. The tool service prints the line on standard output. It opens no file.
2. The container runtime writes it to the pod's log under `/var/log/pods/`, with a time stamp and the stream name in front. The kubelet rotates that log at 10 MiB and keeps five files, and deletes it with the pod. Both are K3s defaults that this project does not set. They were not read from the running kubelet.
3. Every two seconds, `aisec-audit-copy` reads the pod's log files, current and rotated, and appends each new line to `/var/log/aisec/tool-audit.jsonl`. It skips the file the kubelet writes while it compresses a rotated log (`NAME.tmp`, renamed to `NAME.gz` when whole). The rotated file stays until then, so the lines are read from it.

## Who can change what

| Who | The pod's log | The audit file |
| --- | --- | --- |
| The tool service, or a worker that took it | Adds lines, through standard output. Cannot rewrite them | Nothing. No pod mounts the folder (`L.5`) |
| `aisec-audit-copy` | Reads, through a default ACL for its group. The ACL is on `/var/log/pods`, so it reads every pod's log on the host, not only the tool service's. It has no network to send them anywhere | Appends. Cannot truncate, rewrite, delete, or remove the append-only attribute, because it is not root and holds no capability |
| Root on the orchestrator | Everything | Everything, after removing the attribute. Accepted in [lab against production](lab-vs-production.md#detection-and-response) |

The file is `0620 root:aisec-audit-copy` with `chattr +a` (`L.3`). The copier runs without a network, with a read-only view of the system except for its state folder and `/var/log/aisec`, and with 256 MiB of memory.

## What the copier refuses

The copier reads text that a compromised worker shapes, on the trusted machine. It copies a line as it is only when the runtime marks it as a whole line on standard output and it parses as one JSON object. Anything else becomes a marker line with the reason, the runtime's time stamp, and the size. The original is not copied. `L.7` fails on any marker. A last line without its newline is left for the next pass: the runtime may still be writing it, and a pass that read half of it would make a marker and move past the whole line for good.

A pass fails, and the copier's health file is not touched, when no log file of the service is found, a file cannot be read, or a time stamp from the runtime does not parse. Each of these means the layout changed. `L.4` fails when the copier has not succeeded for ten seconds.

## Completeness

| Loss | What shows it |
| --- | --- |
| A line in the middle of a start | A hole in `seq` (`L.6`) |
| The first line of a start | `seq` does not begin at 1 (`L.6`) |
| The copier stopped | `L.1`, `L.4`, and `HO.1` |
| The pod was deleted between a line and the next pass | Nothing, unless it was the deploy. `deploy.sh` waits for a whole copier pass after the old pod's last line before it replaces the pod, and is run with no job active |
| The file reached 2 GiB | A marker line, a failed unit (`L.1`, `HO.1`), and `L.7` |

## The worker's journal

State: **Verified** on 2026-10-16. The account and the command on the worker are in `worker/log-export/`, the puller in `platform/logs/`, and both in the first-boot templates. Both ends run on the live VMs ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)). The checks are `J.1` to `J.9` on [validation](../validation/audit-log.md#the-workers-journal).

Every five minutes, `aisec-journal-pull` on the orchestrator connects to the worker as `aisec-logexport` and appends what it gets to `/var/log/aisec/worker-journal.jsonl`.

| Piece | What holds it |
| --- | --- |
| The key | Made on the orchestrator at first boot, readable by the puller's account only. On the worker its line carries `from=` the orchestrator's address, `restrict`, and a forced command, in a file root owns (`J.7`) |
| The forced command | Accepts nothing, for the whole journal, or one cursor in the journal's format, for what came after it. Anything else is refused with exit status 2 (`J.6`). It must match the reviewed copy (`J.9`) |
| The worker's host key | Pinned in a root-owned file outside the puller's folder, so the puller cannot pin another (`J.5`) |
| The worker's answer | Read as hostile input: 16 MiB a pull, 64 KiB a line, standard error not read. A line is kept only as one JSON object with a cursor in the journal's format. Anything else is a marker (`J.4`) |
| The file | `0620 root:aisec-journal-pull`, append-only (`J.2`), 2 GiB |

What it does not do:

- **It does not make the worker honest.** Root on the worker can forge entries, and erase what was written since the last pull, up to five minutes.
- **A worker that stops sending stalls a pull** until the unit's start timeout of 180 seconds ends it. `J.3` fails after 25 minutes without a successful pull.
- **The first pull copies the whole journal,** 16 MiB at a time, one pull every five minutes.

## Limits

- **The last lines of a start can be lost without a trace.** A pod that crashes, or a deploy during a job, can take up to two seconds of lines with it, and a missing tail leaves no hole.
- **A full file stops the record.** The cap protects the disk K3s needs. Past a limit per minute, requests without a valid token get no line, so a flood of them cannot fill it. Tested on the live system on 2026-10-16 ([worklog](../worklogs/0004-edge-network-and-monitoring.md#on-the-live-system)). Archiving is a manual procedure.
- **A rebuild of the orchestrator deletes the file.** Archive it first. See [lab against production](lab-vs-production.md#detection-and-response).
- **The copier depends on the runtime's file layout.** A K3s release that changes the path, the line prefix, or the file mode makes the copier fail, and `L.4` with it. That is by design, and it also means an upgrade can stop the record until the copier is fixed.
- **The ACL is reasoned, not observed.** That the default entries reach every new pod folder and rotated file is tested on the first deployment.
- **Alerts wait for someone to look.** Since 2026-10-17 each line also reaches Azure Monitor, and since 2026-10-18 a hole in a start's sequence or a marker line raises an alert in the portal ([monitoring](../components/monitoring.md#alert-rules)). Nothing is sent.
