# Audit log

The tool service prints one audit line per decision. A host unit on the orchestrator copies the lines into an append-only file that no pod mounts. These checks test the copier and the file. The design is [ADR 0019](../decisions/0019-how-the-audit-lines-and-the-worker-journal-are-copied.md). What the file holds and who can change it is on the [audit log page](../security/audit-log.md).

Status: **configured, not tested** on the live system. The copier is not installed on the orchestrator yet, so every check below fails there today. The fail side of `L.5` to `L.7` was seen with stubs: the probe's own lines, run on a workstation against made-up files and mount lists ([worklog](../worklogs/0003-toolchain-integration.md#the-checks-against-stubs)). The checks are in `validation/platform-checks.sh`.

## On the orchestrator

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `L.1` | The audit copier is active | No copier, no record. A full file stops it on purpose, and this check fails then too | `systemctl is-active aisec-audit-copy` |
| `L.2` | The audit copier starts at boot | A reboot must not end the record | `systemctl is-enabled aisec-audit-copy` |
| `L.3` | The audit file is root's and append-only | The copier can add lines and cannot change or remove them | Owner `root`, group `aisec-audit-copy`, mode `620`, and the `a` attribute from `lsattr` |
| `L.4` | The copier succeeded in the last 10 seconds | A copier that stopped working looks like a quiet service. Ten seconds is five times its interval | The age of `/var/lib/aisec-audit-copy/ok`, which the copier writes after every pass that found a log file of the service and read it |
| `L.5` | No pod mounts the audit folder | A pod with the folder mounted can read the record. A pod is the worker's way onto this machine ([T22](../security/threat-model.md)) | No `hostPath` volume in any namespace is `/`, `/var`, `/var/log`, or `/var/log/aisec` or below it |
| `L.6` | No audit line is missing | A hole in the sequence is a lost line ([ADR 0019](../decisions/0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)) | For each `start`, the highest `seq` minus the count of distinct numbers, plus every line that is not JSON. Lines without a `start`, from the image before the sequence, are not counted |
| `L.7` | The copier refused no line | A marker stands for a line that was not one JSON object on standard output, or for a full file | The count of lines with `"event":"copy"` |

## Not checked

- **The ACL on the pod logs.** `L.4` fails if the copier cannot read a log file, which covers the effect. The entries themselves are not read.
- **That the copier cannot remove the attribute or rewrite the file.** It holds no capability, which the unit file says. A live attempt as the copier's account is a runbook step, not a check, because a successful attempt would damage the record.
- **A missing tail.** Lines lost at the end of a start leave no hole. See the [audit log page](../security/audit-log.md#limits).
