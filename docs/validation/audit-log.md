# Audit log

The tool service prints one audit line per decision. A host unit on the orchestrator copies the lines into an append-only file that no pod mounts. These checks test the copier and the file. The design is [ADR 0019](../decisions/0019-how-the-audit-lines-and-the-worker-journal-are-copied.md). What the file holds and who can change it is on the [audit log page](../security/audit-log.md).

Status: **tested** on the live system on 2026-10-16: every check below passes. `L.1`, `L.3`, `L.4`, and `L.5` failed when their condition was broken, and `L.2`, `L.6`, and `L.7` before the install ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)). `L.8` was added after the rollout, with a fix to the copier. On the live system it failed with the fix in the checkout and the earlier copier installed, and passed with the earlier copier in the checkout ([worklog](../worklogs/0003-toolchain-integration.md#fix-whole-lines-only)). After the fix was installed, it passed. `L.5` failed on 2026-10-26 with `0 1`, in a copy of the script that asked kubectl for a verb that does not exist, where before the change for #173 it passed ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-counting-checks-fail-on-a-broken-command)). The fail side of `L.6` and `L.7` was also seen with stubs: the probe's own lines, run on a workstation against made-up files and mount lists ([worklog](../worklogs/0003-toolchain-integration.md#the-checks-against-stubs)). The checks are in `validation/platform-checks.sh`.

## On the orchestrator

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `L.1` | The audit copier is active | No copier, no record. A full file stops it on purpose, and this check fails then too | `systemctl is-active aisec-audit-copy` |
| `L.2` | The audit copier starts at boot | A reboot must not end the record | `systemctl is-enabled aisec-audit-copy` |
| `L.3` | The audit file is root's and append-only | The copier can add lines and cannot change or remove them | Owner `root`, group `aisec-audit-copy`, mode `620`, and the `a` attribute from `lsattr` |
| `L.4` | The copier succeeded in the last 10 seconds | A copier that stopped working looks like a quiet service. Ten seconds is five times its interval | The age of `/var/lib/aisec-audit-copy/ok`, which the copier writes after every pass that found a log file of the service and read it |
| `L.5` | No pod mounts the audit folder | A pod with the folder mounted can read the record. A pod is the worker's way onto this machine ([T22](../security/threat-model.md)) | No `hostPath` volume in any namespace is `/`, `/var`, `/var/log`, or `/var/log/aisec` or below it. The count comes with the command's exit status, which has to be 0, so a query that fails no longer reads as none found ([#173](https://github.com/sindredg/ai-security-platform/issues/173)) |
| `L.6` | No audit line is missing | A hole in the sequence is a lost line ([ADR 0019](../decisions/0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)) | For each `start`, the highest `seq` minus the count of distinct numbers, plus every line that is not JSON. Lines without a `start`, from the image before the sequence, are not counted |
| `L.7` | The copier refused no line | A marker stands for a line that was not one JSON object on standard output, or for a full file | The count of lines with `"event":"copy"` |
| `L.8` | The audit copier installed is the one in this checkout | A fix to the copier protects nothing until it is installed, and nothing else shows the difference | The SHA-256 of the installed program and unit, read in that order, equals the same files in this checkout. A missing file changes the hash |

## The worker's journal

Status: **tested** on the live system on 2026-10-16: every check below passes. `J.1`, `J.2`, `J.3`, `J.5`, `J.7`, `J.8`, and `J.9` failed when their condition was broken, and all nine before the install ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)). `J.5` was wrong on its first run and is fixed in commit `0c1eba2`. `J.4` and `J.6` were not broken on purpose: `J.4` fails on a marker line, which the puller's tests cover, and the other side of `J.6`, an answer to a cursor, was seen. `J.10` was added later: it passed on the live system, and failed with one line added to the timer in the checkout.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `J.1` | The pull timer is active and starts at boot | No timer, no copy | `systemctl is-active` and `is-enabled` on `aisec-journal-pull.timer` |
| `J.2` | The journal file is root's and append-only | The puller can add lines and cannot change them | Owner `root`, group `aisec-journal-pull`, mode `620`, and the `a` attribute |
| `J.3` | A pull succeeded in the last 25 minutes | A puller that stopped looks like a quiet worker. 25 minutes is five intervals | The age of `/var/lib/aisec-journal-pull/ok` |
| `J.4` | The puller refused no line | A marker is a line that was not a journal entry, or a full file | The count of lines with `"event":"copy"` |
| `J.5` | The puller pins the worker's host key | Otherwise the first answer on the worker's address is trusted | The pinned key equals the key `ssh-keyscan` gets from the worker now. A missing pin is a failure |
| `J.6` | The export key runs nothing but the export | The key lives on the trusted machine and logs in to the untrusted one. It must not give a shell either way | An SSH command `id` with the key, as the puller's account, ends with status 2, the export's refusal. 255 is SSH failing, 0 a command that ran |
| `J.10` | The journal puller installed is the one in this checkout | As for `L.8` | The SHA-256 of the installed program, unit, and timer equals the same files in this checkout |

On the worker:

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `J.7` | The export key is restricted to the orchestrator and the export | `from=`, `restrict`, and the forced command are the whole limit on the key | One line in the account's `authorized_keys`, owned by root with mode `644`, with exactly those options |
| `J.8` | The export account reads the journal and nothing more | `systemd-journal` is the group that reads it. `sudo` would undo the rest | `id -nG aisec-logexport` |
| `J.9` | The worker runs the reviewed export command | The command is the boundary on the worker | Its SHA-256 equals the copy in this checkout |

## Not checked

- **The ACL on the pod logs.** `L.4` fails if the copier cannot read a log file, which covers the effect. The entries themselves are not read.
- **That the copier cannot remove the attribute or rewrite the file.** It holds no capability, which the unit file says. A live attempt as the copier's account is a runbook step, not a check, because a successful attempt would damage the record.
- **A missing tail.** Lines lost at the end of a start leave no hole. See the [audit log page](../security/audit-log.md#limits).
