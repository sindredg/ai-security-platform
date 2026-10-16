# 0021. Monitoring in Azure Monitor, over Private Link, with alerts in the portal

Status: Accepted
Date: 2026-10-16

Adds to [0019](0019-how-the-audit-lines-and-the-worker-journal-are-copied.md): where the copies go after the orchestrator. Builds on [0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md), which removes the orchestrator's way out.

## Context

Nothing records what happens on the platform outside the machine it happens on. The audit lines and the worker's journal end up in files on the orchestrator ([0019](0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)), where root can edit them (T21). Nothing alerts. A failure shows only when someone runs the checks.

The design assumes the orchestrator can be compromised. Monitoring that runs on the orchestrator can be switched off by whoever compromised it, and so can its alerts. A self-hosted stack has a second cost: it competes with K3s and Argo for the orchestrator's 8 GB.

After [0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md), the orchestrator has no way out except the edge proxy, and no public DNS. Whatever ships its logs has to work inside that.

A hostname allowlist does not help here either. The Azure Monitor ingestion names are wildcards shared by every tenant (`*.ods.opinsights.azure.com`, `*.ingest.monitor.azure.com`). A compromised machine allowed to reach them can send data to a workspace of its own. The [Azure Monitor Private Link documentation](https://learn.microsoft.com/azure/azure-monitor/fundamentals/private-link-security) names this as the exfiltration risk Private Link removes.

The operator watches the portal. Alerts are not sent anywhere.

Read on 2026-10-16:

- The Azure Monitor Agent supports Ubuntu 26.04 on x64 and Arm64 ([supported systems](https://learn.microsoft.com/azure/azure-monitor/agents/azure-monitor-agent-supported-operating-systems)).
- With Private Link, the agent uses only private data collection endpoints, and every data collection rule has to name one ([network configuration](https://learn.microsoft.com/azure/azure-monitor/agents/azure-monitor-agent-network-configuration)).
- The Linux VM agent installs extensions through `168.63.129.16` on ports 80 and 32526, without internet access ([extensions for Linux](https://learn.microsoft.com/azure/virtual-machines/extensions/features-linux)).
- Analytics logs include 31 days of retention in the ingestion price ([retention](https://learn.microsoft.com/azure/azure-monitor/logs/data-retention-configure)). Activity Log collection and alerting have no charge ([cost and usage](https://learn.microsoft.com/azure/azure-monitor/fundamentals/cost-usage)).
- Virtual network flow logs need a storage account in the same region as the network ([flow logs](https://learn.microsoft.com/azure/network-watcher/vnet-flow-logs-overview)).
- Retail prices in Sweden Central: Analytics log ingestion USD 2.99 per GB, a log alert rule at one-minute frequency USD 3 per month, flow logs USD 0.50 per GB collected. The API returned no price for the private endpoint.

## Options

| Option | Survives root on the orchestrator | Orchestrator footprint | Cost |
| --- | --- | --- | --- |
| Prometheus, Loki, and Alertmanager in K3s | No. Root stops them and edits what they hold | The largest | Memory and upkeep |
| The same stack on the edge | Yes, for the orchestrator. The edge then holds every log, and it was meant to hold no secrets | None | A larger edge |
| Azure Monitor, agent through the edge proxy | Yes | One agent | The proxy has to allow the shared ingestion names, which reopens the path to any workspace |
| Azure Monitor, agent over Private Link | Yes | One agent | A private endpoint, a scope, and a data collection endpoint |

Name resolution for the private endpoint.

| Option | Problem |
| --- | --- |
| Private DNS zones linked to the networks | The orchestrator would need Azure DNS, which 0020 denies. The zones also take over resolution of every name they hold, in every linked network |
| A resolver on the edge that forwards only the private zones | A second service on the edge, and the orchestrator depends on the edge for its logs too |
| Hosts entries, written from Terraform | Microsoft documents hosts entries for testing. If Azure adds an endpoint name, the agent fails to reach it, and the missing heartbeat shows it |

## Decision

Logs, metrics, and alerts go to Azure Monitor. The orchestrator, the edge, and the router ([0025](0025-the-mesh-node-on-its-own-vm.md)) ship them over Private Link. The worker ships nothing.

**Where the data goes**

- One Log Analytics workspace, in Sweden Central, in the platform resource group. Analytics plan for every table, 31 days of retention. Volume is small enough that the cheaper plans save little and lose alerting.
- An Azure Monitor Private Link Scope with the workspace and one data collection endpoint. Ingestion access is private only. Query access stays open, so the operator reads it in the portal.
- One private endpoint for the scope, in a new subnet of the platform network, `10.40.0.64/27`. The edge and the router reach it over the peering.
- The orchestrator, the edge, and the router get hosts entries for the endpoint's names, from Terraform. No private DNS zone.
- Their security groups allow TCP 443 to the private endpoint subnet, and nothing else new.

**What is collected**

| Machine | Source | Table |
| --- | --- | --- |
| Orchestrator | `/var/log/aisec/tool-audit.jsonl`, the audit copy | A custom table, one row per audit line |
| Orchestrator | `/var/log/aisec/worker-journal.jsonl`, the worker's journal copy | A custom table |
| Orchestrator | Syslog: `auth`, `authpriv`, `kern`, and `daemon` at warning and above | `Syslog` |
| Orchestrator, edge, router | CPU, memory, and disk, every 60 seconds | `Perf` |
| Edge | Squid's access log, both clients, and the fetch window's opens and closes | A custom table, and `Syslog` |
| Edge, router | Syslog, the same facilities. On the router this includes the mesh agent's own log | `Syslog` |
| Both networks | Flow logs, to a storage account per region, with traffic analytics into the workspace | `NTANetAnalytics` |
| Subscription | The Activity Log, where Azure keeps it | Not copied. Alert rules read it directly |

**The worker gets no agent.** It is the untrusted side. It gets no managed identity and no path to Azure. Its journal arrives through the orchestrator's pull ([0019](0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)) and leaves with the orchestrator's agent.

**Identities.** The orchestrator, the edge, and the router each get a system-assigned managed identity, used by the agent and associated with the data collection rules. None of them gets a role on the workspace, so none can read or delete what it sent. Pods cannot ask for the orchestrator's token: [0018](0018-a-host-rule-keeps-pods-off-the-internet.md)'s host rule drops forwarded traffic from pods to `169.254.169.254`, as to anything outside the pod network. A check proves it.

**Alerts.** Rules have no action group. A fired alert shows under **Monitor → Alerts** in the portal, with its severity and history. Nothing is sent.

| Rule | Reads | Severity |
| --- | --- | --- |
| No heartbeat from the orchestrator, the edge, or the router for 10 minutes | `Heartbeat` | 1 |
| A hole in `seq`, or a `start` whose first line is not 1 | The audit table | 1 |
| A marker line in either copy | Both custom tables | 1 |
| No worker journal rows for 15 minutes | The journal table | 2 |
| Squid refused a request from the orchestrator | Squid's table | 1 |
| A fetch window opened | Syslog on the edge | 3 |
| A denied flow from the orchestrator or worker subnet to the internet | `NTANetAnalytics` | 1 |
| An SSH login, accepted or failed, on the orchestrator, the edge, or the router | `Syslog` | 3 for accepted, 2 for failed |
| More than 20 tool service refusals in 5 minutes | The audit table | 2 |
| The daily cap was reached | `_LogOperation` | 1 |
| A disk over 85 percent, memory over 90 percent, or a failed unit | `Perf`, `Syslog` | 2 |
| A write or delete of a security group, rule, role assignment, or policy assignment | The Activity Log | 1 |

Log rules run every 5 minutes, except the cap and the disk, which run every 15. The Activity Log rules are free and belong to the bootstrap root, because they watch the whole subscription.

**A workbook** in the platform resource group shows the rest: tool calls and refusals over time, Squid traffic per client, flows per subnet, and each VM's load. It is a Terraform resource, so it is reviewed like the rules.

**The daily cap** starts at 1 GB. Milestone 3a measures a week of volume and sets the cap from it.

**Checks**

- The agent runs on the orchestrator, the edge, and the router, and reports a heartbeat in the last 10 minutes. Read from the workspace with the operator's Azure sign-in.
- The workspace refuses ingestion from the public network: the scope's ingestion mode is private only, read from Azure.
- A pod's connection to `169.254.169.254:80` gets no answer. A procedure step, like the egress probe in 0018.
- Each alert rule fires once on purpose before 3a is done: an agent stopped, a line removed from a test copy, a request for a host off the list, and so on. The runbook lists each trigger.

## Trade-offs

- **Root on the orchestrator can still lie.** It can stop the agent, which the heartbeat rule shows. It can add false lines. It cannot change or delete what has arrived. The operator can, as Owner (T30).
- **A flood can blind the record.** A compromised orchestrator can push volume until the daily cap stops ingestion for the rest of the day. The cap rule fires first, and the audit file on the orchestrator keeps the lines. Raising the cap trades that risk against cost.
- **Alerts wait for someone to look.** No notification is sent. A fired alert at night is seen in the morning.
- **Hosts entries are not the documented production path.** A new endpoint name from Azure breaks ingestion until the entries are updated. The heartbeat rule catches it.
- **Monitoring is a recurring bill tied to volume.** Ingestion, flow logs, traffic analytics, the private endpoint, and the rules. The cap bounds the largest part. The private endpoint's price was not in the retail API and is read before apply.
- **Whether the agent needs Azure Resource Manager is not known.** Microsoft lists the `AzureResourceManager` service tag as required on the public path. On the private path the documentation says the agent uses only the private endpoints. The first install, with Resource Manager unreachable, settles it. If the agent needs it, that is a new record: Resource Manager accepts requests for any tenant, so allowing it is another way out.
- **Flow logs cover what the security groups decide, not what the edge proxies.** A denied flow is recorded at its source. A refused proxy request is in Squid's table instead. Neither sees inside TLS.
- **The workspace is one more thing in Sweden Central.** If the region is down, so is the record of it.
- **The edge's and the router's agents cross the peering** to the private endpoint. Their volume is small.
