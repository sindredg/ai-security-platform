# 0054. An audit daemon and AIDE on both VMs, with their records off the machine

Status: Accepted
Date: 2026-10-30

## Context

The hardening page has carried two open rows since milestone 2: nothing records what ran on the orchestrator or the worker, and a changed binary or configuration file goes unnoticed ([hardening](../security/hardening.md#open)). [0014](0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) moved both to milestone 6, with the drills that would use them. What exists is the record of tool calls, the worker's journal copied to the orchestrator every five minutes ([0019](0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)), and the orchestrator's own logins and warnings in the workspace ([0021](0021-monitoring-in-azure-monitor-over-private-link.md)).

The roadmap asks for an audit daemon and file integrity monitoring on both VMs, each shown catching something. The worker opens no connection but the tool port and the proxy, and runs no log agent ([0021](0021-monitoring-in-azure-monitor-over-private-link.md)). Both VMs take packages from Ubuntu's archive through Squid, which serves the archive hosts at any time, and no Ubuntu package is pinned ([0011](0011-package-proxy-for-the-worker.md)).

## Options

Linux has one audit daemon, so the choice there is what it records and how the records leave the machine.

| Records leave by | Worker's path | Trade-off |
| --- | --- | --- |
| The daemon's syslog plugin, on a facility of its own | The journal copy the orchestrator already pulls | One new syslog source in the collection rule; the orchestrator's lines and the worker's land in two tables |
| A collected copy of the daemon's log file | A second puller for the worker's file | A new custom table, a new copier, and a second file to keep append-only |
| The daemon's remote plugin to the orchestrator | A new connection from the worker | A listening daemon on the orchestrator, and a path the design forbids the worker |

For file integrity monitoring:

| Option | Trade-off |
| --- | --- |
| AIDE from Ubuntu's archive | Packaged and maintained. Compares mode, owner, size, times, hashes, and attributes. Needs a baseline, and a new one after each install step, kept on the machine it guards |
| A hash list kept by a script of the project's own | Nothing new installed. Reinvents the attributes and the report. The same baseline problem |
| An agent product such as Wazuh or osquery | Central rules and a console. A server to run, and an agent on the worker that needs a network path the worker does not have |

## Decision

**The audit daemon runs on both VMs with three kinds of rule.** Writes to the platform's own files, which only a runbook step changes: the platform's configuration, the SSH daemon's, the units, the sudo and account files, `/usr/local`, and on the worker the model, the agent, and the homes of the three accounts the orchestrator logs in to (key `aisec-config`). Programs run in a session of one of those accounts or as a dynamic user, which is how a job runs (key `aisec-exec`), and programs run as root in a login session, which is the operator's sudo (key `aisec-root`).

Not the whole of `/etc` or `/var`: a package upgrade and the copiers write there on their own. The rules are loaded, not locked: a locked set would need a reboot for every change, and root on the VM is trusted by design.

**Every record goes to syslog on `local6` through the daemon's plugin, as text.** The orchestrator's log agent collects `local6` into the `Syslog` table; the worker's lines land in its journal, which the orchestrator pulls into the worker journal table. The daemon's own log stays on each machine for `ausearch`.

**AIDE from Ubuntu's archive, without `aide-common`.** Its configuration is the project's, `/etc/aisec/aide.conf`: the boot files, `/etc`, the system's programs and libraries, `/usr/local`, and the platform's own paths, less the files the system rewrites by itself. A baseline is written once, by hand, and a timer runs the check daily and after boot.

The check logs one line to `local6` with the three counts and the database's SHA-256. A new baseline is written by hand after an install step, once the report shows that step's changes and nothing else, and the worker's baseline is copied to the orchestrator.

**Three alert rules.** `audit-config-write` fires on a write to a platform file on either VM, `aide-report` on a check that found a difference, failed, or wrote a baseline, and `aide-check-missing` when either machine has sent no check line for 26 hours.

## Trade-offs

- Root on a VM can stop the daemon, change the rules, or write a new baseline. The stop and the rules change are recorded until the stop, the baseline's new hash is in its line, the worker's baseline has a copy on the orchestrator, and silence from either machine is an alert after a day. What root does between a pull and the next is still root's to erase on the worker ([0019](0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)).
- A package upgrade changes files in the scope. The next check reports them and the alert fires, until the operator compares the report with the upgrade log and writes a new baseline. A baseline written without that look makes the change the baseline.
- Every install step and every check run as root adds records. The operator's commands are recorded on purpose; the volume counts against the daily cap, and the first day's volume is read in the milestone 6 worklog.
- Not seen when this was written: a rebuilt VM's first boot with the install in it, a day of records, and a package upgrade day's report ([worklog](../worklogs/0007-operational-and-containment-drills.md#slice-8-the-host-audit)).
