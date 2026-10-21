# 13. The denied flow alert matches no public address

Date: 2026-10-21
Milestone: 3, toolchain integration

## Symptom

Traffic analytics began processing the platform network's flow log at 20:43 UTC on 2026-10-20, and `O.17` failed on it as written ([worklog](../worklogs/0003-toolchain-integration.md#fix-the-denied-flow-alert)). By 04:33 UTC on 2026-10-21, four of its rows were denied flows from the orchestrator (`10.40.0.4`) and the worker (`10.40.0.36`) to `1.1.1.1:443`, made by the checks `C.1` and `E.12`. `denied-flow-to-internet` fired on none of them. The alerts of the last day were `ssh-login-accepted`, `squid-refused-orchestrator`, and `fetch-window-opened`.

## Cause

Confirmed from the rows. For a public destination, traffic analytics leaves `DestIp` empty and lists the address in `DestPublicIps`:

```text
SrcIp        DestIp   DestPublicIps
10.40.0.4    (empty)  1.1.1.1|5|0|0|0|0|0
10.40.0.36   (empty)  1.1.1.1|5|0|0|0|0|0
```

The rule tested `not(ipv4_is_private(DestIp))`. On an empty string, `ipv4_is_private` returns null, `not` keeps it null, and `where` drops the row. The rule could not match a public address at all.

Nothing showed it before. While traffic analytics processed none of the platform's flows, the rule had no rows to try, and the drill on 2026-10-18 could not tell an empty table from a wrong query ([worklog 0004](../worklogs/0004-edge-network-and-monitoring.md#the-drills)). Query validation would not have caught it either: the query is valid and matches nothing.

## Fix

The rule tests `isnotempty(DestPublicIps)` instead. Over 20:00 UTC on 2026-10-20 to 05:00 on 2026-10-21, the old query counts 0 rows and the new one counts the 4 denied flows. The new one counts 0 for a source range outside the two subnets, and 0 for allowed flows.

## Verification

The rule was applied at about 14:08 UTC on 2026-10-21, and read back from Azure with the new query. The next denied flows came from a check run and a probe: the orchestrator to `1.1.1.1:443` from 15:19:54 UTC, and the worker from 15:21:16. Traffic analytics wrote them at 15:33:29, and `denied-flow-to-internet` fired at 15:40:45, 21 minutes after the first flow. It is the first time the rule fired ([worklog](../worklogs/0003-toolchain-integration.md#the-alert-fires)).
