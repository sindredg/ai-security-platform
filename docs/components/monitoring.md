# Monitoring

Logs and load from the orchestrator, the edge, and the router, kept in a Log Analytics workspace that none of them can read or delete from. They send over a private endpoint, and the workspace refuses ingestion from anywhere else. The worker sends nothing: its journal leaves with the orchestrator's copy.

| | |
| --- | --- |
| State | Built on 2026-10-17. Verified by `O.1` to `O.13` ([validation](../validation/monitoring.md), [worklog](../worklogs/0004-edge-network-and-monitoring.md#monitoring)). Alert rules, flow logs, and the workbook are not built |
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
| All three | CPU, memory, and disk use, every 60 seconds | `Perf` |
| All three | The agent's own heartbeat | `Heartbeat` |

Each line of a copied file is one row, unchanged, in `RawData`, with `Computer` and `FilePath`. Nothing is parsed at ingestion, so a line the agent cannot parse still arrives. Queries parse it:

```kusto
AisecToolAudit_CL
| extend line = parse_json(RawData)
| project TimeGenerated, start = tostring(line.start), seq = tolong(line.seq), event = tostring(line.event), decision = tostring(line.decision)
```

The agent starts reading a file at its end. Lines written before the install are in the files on the orchestrator and the edge, not in the workspace.

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

Read once, about ten minutes after the install on 2026-10-17, with `ps`: the agent's processes held about 199 MB on the orchestrator, 192 MB on the edge, and 88 MB on the router, each near 0.3 percent CPU. The router had 396 MB available of 836 MB. A week of readings is still to come ([roadmap](../roadmap.md#3a-edge-network-and-monitoring)).

## Limits

- **No alerts yet.** Nothing fires on a missing heartbeat, a hole in the audit sequence, or a refused request until the alert rules are built.
- **Root on a monitored VM can stop its agent or send false lines.** It cannot change or delete what arrived ([T42](../security/threat-model.md)).
- **The daily cap stops ingestion for the rest of the day.** It is 1 GB until a week of volume is measured ([T41](../security/threat-model.md)).
- **A new endpoint name from Azure breaks ingestion** until the hosts block is written again. A plan shows the change, and `O.5` to `O.7` fail.
- **The edge and the router have outbound TCP 443.** Nothing stops root on either from sending to another workspace over the internet. Private Link closes that path for the orchestrator only, which has no other way out.

## Vendor documentation

- [Azure Monitor Agent network configuration](https://learn.microsoft.com/azure/azure-monitor/agents/azure-monitor-agent-network-configuration)
- [Data collection endpoints](https://learn.microsoft.com/azure/azure-monitor/data-collection/data-collection-endpoint-overview)
- [Configure Private Link for Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/fundamentals/private-link-configure)
- [Collect a text file with the agent](https://learn.microsoft.com/azure/azure-monitor/vm/data-collection-log-text)
