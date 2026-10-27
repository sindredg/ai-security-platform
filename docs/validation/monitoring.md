# Monitoring

The orchestrator, the edge, and the router run the Azure Monitor Agent and send to one Log Analytics workspace, through a private endpoint. The worker sends nothing. The design is [ADR 0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md), with the changes in [ADR 0027](../decisions/0027-how-the-monitoring-is-built.md). The component is described on the [monitoring page](../components/monitoring.md).

Status: **tested** on the live system for `O.1` to `O.17`. `O.1` to `O.13` passed on 2026-10-17 at 23:39 UTC, after failing before the apply on absence, and `O.4`, `O.5`, and `O.13` also on a changed value ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-fail-side-of-each-new-check-5)). `O.14` to `O.16` passed on 2026-10-18 at 09:07 UTC and failed on a changed input ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-fail-side-of-each-new-check-6)). `O.17` checks both flow logs since 2026-10-21, when traffic analytics began processing the platform network's. It passed live and failed on an hour with the edge's rows alone and on no answer ([worklog](../worklogs/0003-toolchain-integration.md#the-query-and-the-check-tested)). The checks are in `validation/platform-checks.sh`.

## On the VMs

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `O.1` | The log agent is installed and active on the orchestrator | No agent, no record outside the machine. A stopped agent is also what a compromised machine would do first ([T42](../security/threat-model.md)) | The `azuremonitoragent` package's status, and `systemctl is-active azuremonitoragent` |
| `O.2` | The same on the edge | The edge's record is Squid's log, refusals included | The same |
| `O.3` | The same on the router | The router's record is its logins and the mesh agent's warnings | The same |
| `O.4` | No log agent on the worker | The worker is the untrusted side. An agent would give it an identity and a path to Azure ([ADR 0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md)) | The package is not installed |

## In Azure

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `O.5` to `O.7` | Each monitored VM's hosts entries are the private endpoint's | The VMs have no private DNS zone. A missing or stale entry sends the agent to a public name, which the workspace refuses | The SHA-256 of the sorted lines between the markers in each VM's `/etc/hosts`, against the same form built from the endpoint's `customDnsConfigs`. No record from Azure, or a VM not reached, is a failure |
| `O.8` | The workspace takes no public ingestion and no shared key | Ingestion from a public network is the path Private Link closes. A shared key would be a credential outside Entra | `publicNetworkAccessForIngestion` is `Disabled`, query access `Enabled`, and `features.disableLocalAuth` is `true` |
| `O.9` | The Private Link Scope takes ingestion only from its private endpoint | With `Open`, a VM on the network could still send to a workspace outside the scope ([private link design](https://learn.microsoft.com/azure/azure-monitor/fundamentals/private-link-design#access-modes)) | `accessModeSettings`: ingestion `PrivateOnly`, query `Open` |
| `O.10` | A heartbeat from each log agent in the last 10 minutes | Proves the whole path: hosts entries, private endpoint, scope, rules, and agent | A query on `Heartbeat`, distinct computers in the last 10 minutes, with the operator's sign-in |
| `O.11` | The worker's journal copy reached the workspace in the last 25 minutes | The journal's only way out is the orchestrator's agent | A count on `AisecWorkerJournal_CL` in the last 25 minutes, five pull intervals |
| `O.12` | The log agents' identities hold no role | An identity with a role on the workspace could read or delete what it sent | `az role assignment list --all --assignee` for each VM's principal. No identity is a failure |
| `O.13` | The worker has no managed identity | An identity on the worker is a token any process on it can ask for | `identity.type` of the worker VM is empty |
| `O.14` | Every alert rule in this checkout is on, resolves itself, and sends nothing | A rule that is off, or missing, is silence that looks like calm. A rule with an action group would send data out ([ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md)) | The rule names from `infra/platform/alerts.tf`, against the scheduled query rules in the platform group: `enabled`, `autoMitigate`, and no action group, each |
| `O.15` | Four Activity Log rules watch the controls and send nothing | A change to a security group, a rule, a role assignment, or a policy assignment is the change an attacker with a deployment identity makes first | The Activity Log rules in the platform state group: names, `enabled`, and no action group |
| `O.16` | Flow logs are on for both networks, with traffic analytics every 10 minutes | Flow logs are the record of what the security groups decided, on every subnet | `az network watcher flow-log list` in each region: enabled, traffic analytics enabled, interval 10 |
| `O.17` | Traffic analytics wrote flows from both flow logs in the last hour | Flow logs that are on but never processed alert on nothing. `denied-flow-to-internet` reads the platform's rows | The distinct flow log names in `NTANetAnalytics` rows of the last hour: `fl-aisec-edge fl-aisec-platform` |

A failed Azure call prints nothing, and nothing equals no expected value here. `O.5` to `O.7` compare hashes, so a check that got no record says so in its expected value instead of comparing two empty answers.

## Not checked

- **That the audit lines arrive.** Audit lines come only from tool calls, and nothing calls the tool service (an MCP server) between exercises. The runbook makes one call and finds its line.
- **That Squid's log arrives.** The runbook requests a host off the list and finds the refusal.
- **That a pod cannot reach the instance metadata service.** A procedure step in the runbook, like the egress probe in [ADR 0018](../decisions/0018-a-host-rule-keeps-pods-off-the-internet.md).
- **That the agent sends nothing over the internet.** The orchestrator has no route there ([containment](containment.md)), so there it holds by construction. The edge and the router have outbound TCP 443, and nothing checks that their agents use only the private endpoint.
