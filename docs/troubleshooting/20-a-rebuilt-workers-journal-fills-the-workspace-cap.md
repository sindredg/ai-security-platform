# 20. A rebuilt worker's journal fills the workspace's daily cap

Date: 2026-11-01
Milestone: 6, operational and containment drills

## Symptom

After the worker's rebuild, every check passed but `O.11`, "The worker's journal copy reached the workspace in the last 25 minutes", at 15:43 UTC. The workspace read `OverQuota`, with its next reset at 17:00 UTC:

```text
Name       QuotaGb    Reset                 Ingestion
log-aisec  0.21       2026-11-01T17:00:00Z  OverQuota
```

The journal pull itself had worked. The orchestrator's copy grew by about 80,000 lines.

## Cause

Confirmed from the pull's journal and the workspace's rows.

- **The rebuild asks for the whole new journal.** Step 13 of the [audit log runbook](../runbooks/audit-log.md#after-a-worker-rebuild) sets the old cursor aside, so the first pull asks for everything since the new worker's first boot. The first boot, the first update, the model build, and the installs wrote about 80,000 lines in 25 minutes.
- **Each pull takes 16 MiB and the timer runs every five minutes.** Seven pulls from 15:11 to 15:42 UTC stopped at the limit, then the eighth caught up. The collection rule sends each new line of the copy to the workspace.
- **The cap stops all ingestion.** The workspace's rows from the copy end in the 15:10 bin, with 24,511 rows, the first two pulls' 12,507 and 12,006. The day's copy rows came to 134 MB of the 0.21 GB cap, before the other tables.

From the cap to the reset, about 100 minutes, the workspace took no rows from any table, so no alert could fire on new data. The orchestrator's copy kept every line. The lines written during those minutes do not reach the workspace after the reset: the collection rule sends a line once.

## Fix

The procedure, not the code. Step 13 of the audit log runbook now says what the catch-up costs, with two ways to run it:

- Rebuild just after the 17:00 UTC reset, so the catch-up fits in a day's cap with room for the rest.
- Or keep the cap for the rest: put the new worker's current cursor in place of the old one, and the copy starts at the rebuild. First boot's lines then stay on the worker only.

A higher cap, or a per-pull pace, is the other option. Each needs an apply or a code change, and the [monitoring page](../components/monitoring.md#limits) gives the cap's reasoning.

## Verification

Reasoned, not yet observed: after the 17:00 UTC reset, new lines from the copy reach the workspace and `O.11` passes. The result goes to the [milestone 6 worklog](../worklogs/0007-operational-and-containment-drills.md#the-worker-rebuild).
