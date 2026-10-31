# Host audit

The audit daemon and AIDE on the orchestrator and the worker ([ADR 0054](../decisions/0054-an-audit-daemon-and-aide-on-both-vms-with-their-records-off-the-machine.md)). The daemon records writes to the platform's own files and the programs jobs and the operator run, and sends each record to syslog; AIDE compares the file system with a baseline daily. The procedure is the [host audit runbook](../runbooks/host-audit.md), and the drill `validation/drills/host-audit.sh` shows each catching something.

Status: **tested** on the live system on 2026-10-31. `F.1` to `F.7` failed before the install on empty values at 05:32 UTC and passed at 06:41 UTC after the third pass; `O.18` failed at 05:32 UTC on its own query, which read the facility and the level as two lines, and passed after the fix; `F.8` and `F.9` read 11 executable scripts before the change at 07:07 UTC and `0` after, 439 of 439 at 07:34 UTC ([worklog](../worklogs/0007-operational-and-containment-drills.md#slice-8-the-host-audit)).

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `F.1` | The orchestrator's audit daemon runs the rules in this checkout and sends its records to syslog | A daemon that is stopped, runs other rules, or keeps its records on the machine records nothing anyone sees | `auditd` is `active` and enabled in the kernel, `augenrules --check` reads `No change`, the plugin's process runs, and the rules and plugin files hash as the checkout's |
| `F.2` | The orchestrator's AIDE timer runs, with the configuration and commands in this checkout | A check that never runs, or runs another scope, finds nothing | The timer is `active` and `enabled`, and the configuration, the two commands, the unit, and the timer hash as the checkout's |
| `F.3` | The orchestrator is at its AIDE baseline, checked within a day | A difference nobody looked at is either an unnoticed change or a stale baseline. Both need the operator | The database is `root 600`, and the last `check` line in the journal within 25 hours reads `added=0 removed=0 changed=0` |
| `F.4` to `F.6` | The same on the worker | The worker is the machine the design assumes compromised | The same probes on the worker |
| `F.7` | The worker's AIDE baseline is the copy the orchestrator holds | A baseline written on the worker alone, by root there, would make root's changes the baseline | The SHA-256 of `/var/lib/aisec/aide/aide.db` on the worker equals that of `/var/lib/aisec/aide/worker-aide.db` on the orchestrator |
| `F.8`, `F.9` | No message-of-the-day script runs at a login, on the orchestrator and the worker | PAM runs each executable script there as root at every login, the machine accounts' included: code nobody reads, and about forty records a login | No file under `/etc/update-motd.d` has an execute bit |

`O.18` on the [monitoring page](monitoring.md) reads that the collection rule collects `local6`, and `O.14` that the three alert rules exist. `F.3` and `F.6` fail after a package upgrade or an install step until the operator reads the report and writes a new baseline ([runbook](../runbooks/host-audit.md)), which is the point of them.

## Broken inputs

Each check's probe, run before the install on 2026-10-31, read nothing: no daemon, no rules file, no timer, no baseline, no copy, and every one failed on its empty value. `O.18`'s first form read the facility and the level as two lines and failed on the live rule at 05:32 UTC; its query with a source name the rule lacks errors and reads empty, run locally on 2026-10-31. `F.3` and `F.6` would fail on a check line with a count, as the first run's lines had; no check run saw that, since the first run stopped before its checks.
