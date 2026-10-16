# 0019. How the audit lines and the worker's journal are copied

Status: Accepted
Date: 2026-10-16

## Context

[0014](0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) decided where the two logs go. The tool service prints one JSON line per decision, and the host appends the lines to a root-owned file with the append-only attribute. The orchestrator pulls the worker's journal over SSH on a timer, with a key that can only run the export. It left the mechanics open, and the mechanics decide whether the logs are complete.

Four things found while designing them:

**Deleting a pod deletes its log.** The container runtime writes a pod's output under `/var/log/pods/<namespace>_<pod>_<uid>/`, and the kubelet removes that directory with the pod. Read on 2026-10-16: the tool service pod started at 17:17 on 2026-10-15 holds 8 lines. The lines from the round trips run before it, on pods that were replaced, are gone. A copier that runs once a minute loses up to a minute of lines at every rollout.

**Both copiers read text that an attacker shapes.** The worker's journal comes from the machine the design assumes is compromised. Audit lines carry a job name and a reason that a caller influences. Both land on the trusted machine, which has one disk shared with K3s.

**Nothing can show that a line is missing.** The audit line has a time to the second and no order. A copy with a hole in it looks the same as a complete one.

**The pod logs are root's.** `/var/log/pods` is `0750 root:root`, and each log file is `0640 root:root`. A copier that is not root needs a way in.

## Options

How the audit lines leave the runtime:

| Option | Lines lost at a pod deletion | Privilege | Cost |
| --- | --- | --- | --- |
| A timer that reads the pod log files every minute | Up to a minute | Reads root's files | Nothing new |
| A follower that reads the pod log files every two seconds | Up to two seconds, and none when the deploy runs a copy first | Reads root's files | A process that stays up |
| A log agent such as Fluent Bit | About the same as a follower | Usually root | A binary to pin, scan, and configure, for one file |
| `kubectl logs` from the host | Everything after the pod is gone. The API serves the current and previous container only | A Kubernetes credential on the host | A credential for a log copy |

How a non-root copier reads root's files:

| Option | What the copier can read | Cost |
| --- | --- | --- |
| Run as root | Everything | The text it parses is shaped by the worker |
| `CAP_DAC_READ_SEARCH` | Every file on the machine, including the cluster token, unless a mount namespace hides each one | A list of hidden paths that has to stay complete |
| A default ACL on `/var/log/pods` that gives the copier's group read | Pod logs only | The `acl` package. Depends on the runtime creating files with group read, which `0640` does |

How the journal is stored on the orchestrator:

| Option | Cost |
| --- | --- |
| `systemd-journal-remote`, as a journal file | A package. Cursor tracking across pulls is not built for a stream on standard input |
| JSON lines from `journalctl -o json` | Nothing new. The copy is searched with `grep` and `python3 -m json.tool`, not `journalctl` |

## Decision

**The audit line gets a sequence.** Each line carries `start`, a random identifier made when the service starts, and `seq`, which counts from 1 within that start. A hole in `seq` within one `start` is a lost line, and a check looks for it.

**A follower copies the audit lines.** A Python script that uses only the standard library, run by a systemd unit on the orchestrator.

- Every two seconds it reads the tool service's log files under `/var/log/pods/tool-services_*`, current and rotated, and appends each new line to `/var/log/aisec/tool-audit.jsonl`. "New" is decided by the runtime's own nanosecond timestamp, kept in a state file.
- It keeps the service's line as it is. A line that is not a complete JSON object on standard output, including one the runtime split because it was too long, is not copied. A marker line with its size and timestamp is copied in its place, so nothing disappears without a trace.
- The deploy procedure runs one pass before the old pod goes.

**The journal is pulled as JSON lines.** A systemd timer on the orchestrator runs every five minutes.

- On the worker, an account `aisec-logexport` in the `systemd-journal` group, with no password and no `sudo`. Its key's `authorized_keys` entry carries `restrict`, `from=` the orchestrator's address, and `command=` a wrapper. The wrapper accepts nothing or one journal cursor that matches the cursor format, and runs `journalctl -o json --after-cursor`. Anything else is refused.
- On the orchestrator, the puller treats the stream as hostile. It reads at most 16 MiB per pull and lines of at most 64 KiB, keeps only JSON objects with a cursor, and stores the last cursor it kept.
- The key is made on the orchestrator at first boot, like the feed key. Its private half never passes through Terraform. The worker's host key is pinned in the puller's `known_hosts`, from the same runbook step that pins it for the feed key.

**Each copier runs as its own user.** `aisec-audit-copy` and `aisec-journal-pull`. Neither runs as root or holds a capability.

- The audit copier reads the pod logs through a default ACL on `/var/log/pods` that gives its group read. The `acl` package sets it.
- Each unit has no network, except the puller's connection to the worker on port 22, and can write only to its own state folder and `/var/log/aisec`.

**The files are root's, append-only, and capped.**

- Both files are `root`-owned, `0620`, writable by the copier's group, with `chattr +a`. The copier can append. It cannot truncate, rewrite, or delete, and it cannot remove the attribute. No pod mounts `/var/log/aisec`.
- Each file stops at 2 GiB. The copier writes one marker line, stops, and its unit fails. A check fails on it. The disk has 49 GB free, read on 2026-10-16.
- Retention is a runbook procedure: root removes the attribute, moves the file aside, and starts a new one.

**Health is when a copier last succeeded.** Each copier touches a state file after every pass, with or without new lines. A check fails when that file is older than five times the interval. Silence from the service is not a failure. Silence from the copier is. A pass that finds no log file of the tool service is a failed pass, because the service always runs: a moved path must not look like a quiet day.

## Trade-offs

- **A rebuild of the orchestrator deletes both copies.** The runbook archives them off the VM before a rebuild. [Lab against production](../security/lab-vs-production.md) carries it.
- **The copier depends on the runtime's file layout.** A path, a line prefix, or a file mode that changes with a K3s release breaks it. It fails loudly. A moved path finds no file and the pass fails. An unreadable file fails the pass. A changed prefix turns every line into a marker line. In each case the state file goes stale, or the markers show, and a check fails.
- **The ACL relies on how the runtime creates files.** That the default ACL reaches every new pod directory and log file, including the rotated ones, is reasoned. The first deployment tests it on a new pod. If it does not hold, the fallback is a capability in a narrowed mount namespace, and that is a new record.
- **The sequence finds holes, not a missing tail.** Lines lost at the end of a start, before a copy, leave no hole. The two-second interval and the pass before a deploy keep that window short. They do not close it.
- **A full file stops the record.** At the cap, new audit lines stay in the runtime's rotation until it drops them. A flood of refused requests can reach the cap, and requests without a token are not rate-limited yet (T20, an [open item](../security/accepted-risks.md#open-items)). The cap protects the disk K3s needs, and gives up completeness to do it.
- **The worker can still lie.** Root on the worker can forge entries, and erase what was written since the last pull, which can be up to five minutes. 0014 accepted this.
- **Root on the orchestrator can still edit both copies.** 0014 accepted this as a lab limit.
- **Nothing alerts.** A failed copier shows up in `HO.1` and in the new log checks, and only when someone runs them.
