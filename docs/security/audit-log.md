# Audit log

Where the tool service's audit lines are stored, and who can change them. What a line holds is on the [tool service](tool-service.md#the-audit-line) page. The design is ADRs [0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) and [0019](../decisions/0019-how-the-audit-lines-and-the-worker-journal-are-copied.md).

State: **Written.** The copier, its unit, and its install script are in `platform/logs/`, tested in the pipeline, and in the orchestrator's first-boot template. Not installed on the running orchestrator, so not tested there. The checks are `L.1` to `L.7` on [validation](../validation/audit-log.md).

The worker's journal is the second log in ADR 0019. It is not written yet.

## The path of a line

1. The tool service prints the line on standard output. It opens no file.
2. The container runtime writes it to the pod's log under `/var/log/pods/`, with a time stamp and the stream name in front. The kubelet rotates that log at 10 MiB and keeps five files, and deletes it with the pod. Both are K3s defaults that this project does not set. They were not read from the running kubelet.
3. Every two seconds, `aisec-audit-copy` reads the pod's log files, current and rotated, and appends each new line to `/var/log/aisec/tool-audit.jsonl`.

## Who can change what

| Who | The pod's log | The audit file |
| --- | --- | --- |
| The tool service, or a worker that took it | Adds lines, through standard output. Cannot rewrite them | Nothing. No pod mounts the folder (`L.5`) |
| `aisec-audit-copy` | Reads, through a default ACL for its group | Appends. Cannot truncate, rewrite, delete, or remove the append-only attribute, because it is not root and holds no capability |
| Root on the orchestrator | Everything | Everything, after removing the attribute. Accepted in [lab against production](lab-vs-production.md#detection-and-response) |

The file is `0620 root:aisec-audit-copy` with `chattr +a` (`L.3`). The copier runs without a network, with a read-only view of the system except for its state folder and `/var/log/aisec`, and with 256 MiB of memory.

## What the copier refuses

The copier reads text that a compromised worker shapes, on the trusted machine. It copies a line as it is only when the runtime marks it as a whole line on standard output and it parses as one JSON object. Anything else becomes a marker line with the reason, the runtime's time stamp, and the size. The original is not copied. `L.7` fails on any marker.

A pass fails, and the copier's health file is not touched, when no log file of the service is found, a file cannot be read, or a time stamp from the runtime does not parse. Each of these means the layout changed. `L.4` fails when the copier has not succeeded for ten seconds.

## Completeness

| Loss | What shows it |
| --- | --- |
| A line in the middle of a start | A hole in `seq` (`L.6`) |
| The first line of a start | `seq` does not begin at 1 (`L.6`) |
| The copier stopped | `L.1`, `L.4`, and `HO.1` |
| The pod was deleted between a line and the next pass | Nothing, unless it was the deploy. `deploy.sh` waits for a whole copier pass after the old pod's last line before it replaces the pod, and is run with no job active |
| The file reached 2 GiB | A marker line, a failed unit (`L.1`, `HO.1`), and `L.7` |

## Limits

- **The last lines of a start can be lost without a trace.** A pod that crashes, or a deploy during a job, can take up to two seconds of lines with it, and a missing tail leaves no hole.
- **A full file stops the record.** The cap protects the disk K3s needs. Requests without a token are not rate-limited yet ([open item](accepted-risks.md#open-items), T20), so a flood of refusals can fill it. Archiving is a manual procedure.
- **A rebuild of the orchestrator deletes the file.** Archive it first. See [lab against production](lab-vs-production.md#detection-and-response).
- **The copier depends on the runtime's file layout.** A K3s release that changes the path, the line prefix, or the file mode makes the copier fail, and `L.4` with it. That is by design, and it also means an upgrade can stop the record until the copier is fixed.
- **The ACL is reasoned, not observed.** That the default entries reach every new pod folder and rotated file is tested on the first deployment.
- **Nothing alerts.** A failure shows when someone runs the checks.
