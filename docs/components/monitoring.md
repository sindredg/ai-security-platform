# Monitoring

Logs and load from the orchestrator, the edge, and the router, kept in a Log Analytics workspace that none of them can read or delete from. They send over a private endpoint, and the workspace refuses ingestion from anywhere else. The worker sends nothing: its journal leaves with the orchestrator's copy.

| | |
| --- | --- |
| State | Built on 2026-10-17 and 2026-10-18. Verified by `O.1` to `O.18` ([validation](../validation/monitoring.md), [worklog](../worklogs/0004-edge-network-and-monitoring.md#monitoring)) |
| Drills | Each alert rule fired once on purpose: the first thirteen by 2026-10-21 ([drills](../worklogs/0004-edge-network-and-monitoring.md#the-drills), [worklog](../worklogs/0003-toolchain-integration.md#the-alert-fires)), the three host audit rules on 2026-10-31 ([worklog](../worklogs/0007-operational-and-containment-drills.md#slice-8-the-host-audit)) |
| Cap and flows | The cap is set from a measured day ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-measured-day-and-the-daily-cap)). Traffic analytics processes the platform network's flows since 2026-10-20 ([troubleshooting 13](../troubleshooting/13-the-denied-flow-alert-matches-no-public-address.md)) |
| Runs on | The Azure Monitor Agent on the orchestrator, the edge, and the router. The workspace, the Private Link Scope, and both collection endpoints are Azure resources in the platform group |
| Software | Azure Monitor Agent, extension `1.45`. Azure served `1.45.1` on 2026-10-17 |
| Version | The minor version is pinned in `monitor_agent_version`, with automatic upgrades off. Azure picks the patch release within it, which the extension cannot pin |
| Network | Private endpoint `pe-aisec-monitoring` in `10.40.0.64/27`. The orchestrator, the edge, and the router reach it on TCP 443, the edge and the router over the peering. Nothing else is allowed in, and the subnet starts nothing |
| Names | A block in each monitored VM's `/etc/hosts`, written by `platform/monitoring/aisec-monitor-hosts` through the VM agent, from the endpoint's own record. No private DNS zone |
| Configuration | `infra/platform/monitoring.tf` |
| Decisions | [0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md), with the changes in [0027](../decisions/0027-how-the-monitoring-is-built.md) |

## What is collected

| Machine | Source | Table |
| --- | --- | --- |
| Orchestrator | `/var/log/aisec/tool-audit.jsonl`, the audit copy | `AisecToolAudit_CL` |
| Orchestrator | `/var/log/aisec/worker-journal.jsonl`, the worker's journal copy | `AisecWorkerJournal_CL` |
| Edge | `/var/log/squid/access.log`, both clients, refusals included | `AisecSquidAccess_CL` |
| All three | `auth` and `authpriv` from info, `user` from notice, `kern` and `daemon` from warning | `Syslog` |
| Orchestrator | `local6` from info: the audit daemon's records and the AIDE check's lines ([host audit](../validation/host-audit.md)). The worker's are in its journal copy | `Syslog` |
| All three | CPU, memory, and disk use, every 60 seconds | `Perf` |
| All three | The agent's own heartbeat | `Heartbeat` |

Each line of a copied file is one row, unchanged, in `RawData`, with `Computer` and `FilePath`. Nothing is parsed at ingestion, so a line the agent cannot parse still arrives. Queries parse it:

```kusto
AisecToolAudit_CL
| extend line = parse_json(RawData)
| project TimeGenerated, start = tostring(line.start), seq = tolong(line.seq), event = tostring(line.event), decision = tostring(line.decision)
```

The agent starts reading a file at its end. Lines written before the install are in the files on the orchestrator and the edge, not in the workspace.

## Alert rules

In `infra/platform/alerts.tf`, on the workspace. Each fires once when its condition starts and resolves when it ends. None has an action group: a fired alert shows under **Monitor, Alerts** in the portal, and nothing is sent ([ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md)).

| Rule | Fires when | Severity | Runs every, over |
| --- | --- | --- | --- |
| `heartbeat-missing` | The orchestrator, the edge, or the router sent no heartbeat for 10 minutes | 1 | 5 min, 10 min |
| `audit-sequence` | An audit start has a hole in its sequence, or a new start does not begin at 1 | 1 | 5 min, 2 days |
| `copy-marker` | A marker line in the audit copy or the journal copy | 1 | 5 min, 15 min |
| `journal-missing` | No row from the worker's journal copy | 2 | 5 min, 15 min |
| `squid-refused-orchestrator` | Squid refused a request from the orchestrator | 1 | 5 min, 15 min |
| `fetch-window-opened` | A just-in-time (JIT) egress window opened on the edge | 3 | 5 min, 15 min |
| `denied-flow-to-internet` | A denied flow from the orchestrator or worker subnet to a public address | 1 | 10 min, 30 min |
| `ssh-login-accepted` | An SSH login was accepted | 3 | 5 min, 15 min |
| `ssh-login-failed` | An SSH login failed, or a certificate was refused | 2 | 5 min, 15 min |
| `tool-refusal-burst` | More than 20 tool service (an MCP server) refusals in one 5-minute bin | 2 | 5 min, 15 min |
| `daily-cap` | The daily cap was reached | 1 | 15 min, 15 min |
| `disk-or-memory` | `/`, `/boot`, or `/boot/efi` over 85 percent, or memory over 90 percent | 2 | 15 min, 15 min |
| `failed-unit` | A systemd unit failed | 2 | 5 min, 15 min |
| `audit-config-write` | The audit daemon recorded a write to one of the platform's own files, on either VM | 2 | 5 min, 15 min |
| `aide-report` | The AIDE check found a difference, failed, or a baseline was written, on either VM | 2 | 15 min, 30 min |
| `aide-check-missing` | No AIDE check line from the orchestrator or the worker for 26 hours | 2 | 1 h, 2 days |

A check run fires `squid-refused-orchestrator`, `ssh-login-accepted`, and `denied-flow-to-internet` on purpose: `P.15`, the logins themselves, and the connections to `1.1.1.1:443` in `C.1` and `E.12`. An install step that writes a platform file fires `audit-config-write`, and a new AIDE baseline `aide-report` ([host audit runbook](../runbooks/host-audit.md)).

The audit lines that fire `audit-sequence` and `copy-marker` in a drill go to `/var/log/aisec/alert-drill.jsonl`, which the same rule collects into the audit table. Their `start` begins with `drill-`. The real copy keeps no false line.

## Activity Log rules

In `infra/bootstrap/monitoring.tf`, in the platform state group, where neither deployment identity holds a role. Each watches the whole subscription for a successful write or delete of one kind of control: security groups, security rules, role assignments, and policy assignments. They cost nothing and have no action group. The portal shows them without a severity: Activity Log rules have none.

## Flow logs

Virtual network flow logs on the platform and edge networks, version 2, kept 90 days in a storage account in each network's region, with Entra authentication only. Traffic analytics processes both every 10 minutes into `NTANetAnalytics`, the platform's only since 2026-10-20 ([worklog](../worklogs/0003-toolchain-integration.md#fix-the-denied-flow-alert)). For a public destination it leaves `DestIp` empty and lists the address in `DestPublicIps`. The flow logs are in the bootstrap root, `infra/bootstrap/monitoring.tf`, written as the operator: the platform identity cannot enable traffic analytics, and cannot turn the flow logs off. The storage accounts are in the platform state group ([ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md)).

Traffic analytics creates a collection rule and endpoint of its own in the platform group, prefixed `NWTA`. Terraform does not manage them.

## Workbook

"AI security platform", in the platform group: tool calls by decision, Squid requests by client and result, flows by source subnet and status, and CPU and memory by VM. It is `infra/platform/workbook.tf`, so a change to it is reviewed like a rule.

## Who can do what

| Identity | Can | Cannot |
| --- | --- | --- |
| Each monitored VM's system-assigned identity | Send through the rules associated with that VM | Read or delete anything in the workspace. It holds no role (`O.12`) |
| The worker | Nothing. It has no identity (`O.13`) and no agent (`O.4`) | |
| A pod on the orchestrator | Nothing. The host rule drops its traffic to the metadata service and to the private endpoint, so it cannot ask for the VM's token or send | |
| The platform deployment identity | Change or delete the workspace, the rules, and the agents. Contributor on the platform group | |
| The operator | Read and query from the portal. Query access is open to the internet, with an Entra sign-in | |

The workspace takes no shared key (`O.8`). Every writer and reader is an Entra identity.

## Footprint

Read across one day to 2026-10-19 10:00 UTC, from the systemd counters of the agent's six units, added up. CPU is over the units' whole run. Memory is `MemoryCurrent` at 13:53 UTC, which counts page cache too ([worklog](../worklogs/0004-edge-network-and-monitoring.md#footprint-1)):

| VM | CPU, of one core | Memory | Share of the VM's memory |
| --- | --- | --- | --- |
| Orchestrator | 0.42 % | 290 MiB | 4 % |
| Edge | 0.55 % | 253 MiB | 7 % |
| Router | 0.51 % | 223 MiB | 27 % |

The router is the tight one. Its lowest available memory in any minute of the day was 339 MB of 836 MB.

On the orchestrator, read again across 15.3 hours to 2026-10-24: 411 MiB and 0.44 % of one core ([worklog](../worklogs/0003-toolchain-integration.md#orchestrator-footprint)). `MemoryCurrent` both times, so page cache moves it.

## Limits

- **Alerts wait for someone to look.** Nothing is sent. A fired alert at night is seen in the morning.
- **Root on a monitored VM can stop its agent or send false lines.** It cannot change or delete what arrived ([T42](../security/threat-model.md)).
- **The daily cap stops ingestion until the reset hour, 17:00 UTC.** It is 0.21 GB, 2.56 times the busiest day measured, 81.90 MB on 2026-10-25, where the rule asks for three ([#175](https://github.com/sindredg/ai-security-platform/issues/175), [ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md), [T41](../security/threat-model.md)). The journal pull's own logins are a third of a day's volume ([#164](https://github.com/sindredg/ai-security-platform/issues/164)). Rows sent after it is reached are lost, and the agents see no error. On 2026-10-19, ingestion came back 44 minutes after the cap was raised, after nine more stops ([troubleshooting 10](../troubleshooting/10-raising-the-daily-cap-leaves-ingestion-flapping.md)).
- **A new endpoint name from Azure breaks ingestion** until the hosts block is written again. A plan shows the change, and `O.5` to `O.7` fail.
- **The edge and the router have outbound TCP 443.** Nothing stops root on either from sending to another workspace over the internet. Private Link closes that path for the orchestrator only, which has no other way out.
- **Nothing from the targets arrives.** They have no agent and no path to the private endpoint (`VN.19`, `VL.19`). What a target logs stays on it and goes with a rebuild. The router logs each new SSH connection from the mesh to a target (`R.8`), and its line reaches the workspace as a `Syslog` row ([milestone 6 drill](../worklogs/0007-operational-and-containment-drills.md#operator-sessions-to-the-targets), T04).

## Vendor documentation

- [Azure Monitor Agent network configuration](https://learn.microsoft.com/azure/azure-monitor/agents/azure-monitor-agent-network-configuration)
- [Data collection endpoints](https://learn.microsoft.com/azure/azure-monitor/data-collection/data-collection-endpoint-overview)
- [Configure Private Link for Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/fundamentals/private-link-configure)
- [Collect a text file with the agent](https://learn.microsoft.com/azure/azure-monitor/vm/data-collection-log-text)
