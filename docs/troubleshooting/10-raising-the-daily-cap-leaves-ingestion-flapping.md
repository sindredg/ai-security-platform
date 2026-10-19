# 10. Raising the daily cap leaves ingestion flapping

Date: 2026-10-19
Milestone: 3a, edge network and monitoring

## Symptom

The cap drill lowered the workspace's daily cap to 0.023 GB at 14:05 UTC, and ingestion stopped at 14:14:59 ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-drill)). The real cap of 0.21 GB was applied at 14:22:43. `_LogOperation` recorded a start, `quota increased`, and a stop 12 seconds later. Eight more starts and eight more stops followed until 14:57:34, then a last start at 15:06:20. The workspace's status flipped between `RespectQuota` and `OverQuota` with them. The quota day held about 57 MB, 27 % of the new cap.

The billable tables lost most of their rows until about 15:10: the worker's journal has none from 14:10:58 to 15:10:58, and `Perf` only part of the minutes from 14:40. Heartbeats and the traffic analytics tables are not under the cap and kept arriving. The log agents saw no error: the edge's agent counted every minute's rows as uploaded, with none dropped and no retries.

## Cause

Not confirmed. Hypothesis: the service keeps its cap state in more than one place, and some of it still held the drill's 0.023 GB for about 40 minutes. Each start after the first gives the reason as `new day starting - daily limit reset`, at hours that are not the reset hour, which fits a state that is reset and then read again from a stale copy. Azure's documentation says only that collection resumes at the reset hour, or when the cap is raised.

## Fix

Wait. Raising the cap further, or removing it, was not tried. Either is a third change to the workspace while the state behind the second one is unknown.

For a later drill, apply the low cap about 30 minutes before the reset hour and the real cap once the alert has fired. The reset hour should then end the flapping at the latest. That is reasoned, not observed. The [monitoring runbook](../runbooks/monitoring.md#daily-cap), step 16, says so.

## Verification

No stop followed the start at 15:06:20, through the reset hour at 17:00, read at 17:10. Rows arrive again from all three VMs: `Perf` from each from 14:40 to 14:44, every minute from about 15:20, and the worker's journal from 15:10:58. `journal-missing` resolved at 15:30:01 and `daily-cap` at 15:52:29. The checks passed at 16:25, `G.2` aside ([worklog](../worklogs/0004-edge-network-and-monitoring.md#checks-6)).
