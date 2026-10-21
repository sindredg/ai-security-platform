# Monitoring: operator procedure

Status: Implemented on 2026-10-17 to 2026-10-19. Steps 1 to 8 ran once, on the live platform, between 22:50 and 23:50 UTC on 2026-10-17. Steps 9 to 13 ran on 2026-10-18 from a script with the same commands. Results are in the [milestone 3a worklog](../worklogs/0004-edge-network-and-monitoring.md#monitoring). The first platform apply stopped on two unregistered resource providers. Step 1 was added for that and ran before the second apply. Steps 6 to 8 ran with the same queries in a longer form. Steps 14 to 17 ran on 2026-10-19 between 13:53 and 14:23 UTC. The drill in step 16 ran about three hours before the reset hour. Its advice to run 30 minutes before the reset hour is reasoned from that run and has not been run ([troubleshooting 10](../troubleshooting/10-raising-the-daily-cap-leaves-ingestion-flapping.md)). The `denied-flow-to-internet` drill of step 11 fired on 2026-10-21, after a fix to the rule's query, from the connections a check run makes ([worklog](../worklogs/0003-toolchain-integration.md#the-alert-fires)).

This builds the log store of [ADR 0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md), as changed by [ADR 0027](../decisions/0027-how-the-monitoring-is-built.md): a Log Analytics workspace that takes ingestion only through a private endpoint, and the Azure Monitor Agent on the orchestrator, the edge, and the router. The worker gets nothing.

## Inputs and access

| Input | Notes |
| --- | --- |
| `az`, signed in as the operator | Owner, for the resource provider registration in step 1, and for the queries |
| The platform deployment identity | `REPLACE_WITH_CRED_DIR/platform.env`, as in the [platform compute runbook](platform-compute.md) |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md) |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-worker`, `aisec-router`, and `aisec-edge` |
| The router and the edge VM, built | The [router](mesh-router.md) and [edge VM](edge-vm.md) runbooks |

## Build

1. Register the two resource providers, from the bootstrap root as the operator. Neither deployment identity can register a provider, and azurerm 5 registers none by itself.

   ```bash
   cd REPLACE_WITH_CHECKOUT/infra/bootstrap
   export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
   terraform plan -out=bootstrap.tfplan
   terraform apply bootstrap.tfplan
   ```

   Expected: the plan adds `azurerm_resource_provider_registration.this["Microsoft.Insights"]` and `["Microsoft.OperationalInsights"]` and nothing else. Each takes about three minutes. Then upload the bootstrap state copy, as in the [network foundation runbook](network-foundation.md#apply-the-bootstrap-root).

2. Plan and apply the platform root as the platform identity.

   ```bash
   cd ../platform
   source REPLACE_WITH_CRED_DIR/platform.env
   terraform plan -out=monitoring.tfplan
   terraform apply monitoring.tfplan
   ```

   Expected on a running platform: 31 to add and 6 to change in place, nothing replaced. The changes are a system-assigned identity on the orchestrator, the edge, and the router, and one outbound rule in each of their security groups. The apply ends with the three run commands and the three agent extensions.

3. Read what the hosts script did on each VM.

   ```bash
   for vm in orchestrator edge router; do
     az vm run-command show -g rg-aisec-platform --vm-name "vm-aisec-$vm" --run-command-name aisec-monitor-hosts \
       --expand instanceView --query "instanceView.[executionState, exitCode, output]" -o tsv
   done
   ```

   Expected: `Succeeded`, `0`, and `wrote 17 entries` for each. 17 is the endpoint's names on 2026-10-17: three for each collection endpoint, three for the workspace, and the scope's shared names.

## Check

4. Run the checks.

   ```bash
   validation/platform-checks.sh
   ```

   Expected: every check passes, `O.1` to `O.13` included. `O.10` and `O.11` can fail for the first ten minutes after the apply, while the agents start.

5. Make one refused tool call from the worker, so the audit copy gets a line.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'curl -s -o /dev/null -w "%{http_code}\n" -X POST -d "{}" \
     --cacert /etc/aisec/tool-service.crt https://tool-service.aisec.internal:30443/mcp'
   ```

   Expected: `401`. The orchestrator's audit file gets a line with `"decision":"refused"`.

6. Find each kind of row in the workspace, with the operator's sign-in.

   ```bash
   WS=$(az monitor log-analytics workspace show -g rg-aisec-platform -n log-aisec --query customerId -o tsv)
   kql() {
     az rest --method post --resource https://api.loganalytics.io \
       --url "https://api.loganalytics.io/v1/workspaces/$WS/query" \
       --body "$(python3 -c 'import json, sys; print(json.dumps({"query": sys.argv[1]}))' "$1")" \
       --query "tables[0].rows" -o tsv
   }
   kql "union withsource=T AisecToolAudit_CL, AisecWorkerJournal_CL, AisecSquidAccess_CL, Syslog, Perf, Heartbeat
        | summarize n = count() by T, Computer | order by T asc"
   kql "AisecSquidAccess_CL | where RawData has 'TCP_DENIED' | take 1"
   ```

   Expected: rows for each table, from the orchestrator for the two copies, from the edge for Squid, and from all three for the rest. Squid's table has a `TCP_DENIED` line: the checks request hosts the worker may not reach. A new custom table took about eight minutes for its first row on 2026-10-17.

7. Compare one stored audit row with the file. Take the `seq` of the line from step 5.

   ```bash
   kql "AisecToolAudit_CL | where RawData has_cs '\"seq\":REPLACE_WITH_SEQ,' | project RawData"
   REPLACE_WITH_SSH aisec-orchestrator 'sudo grep "\"seq\":REPLACE_WITH_SEQ," /var/log/aisec/tool-audit.jsonl'
   ```

   Expected: the same line from both.

8. Probe the metadata service and the private endpoint from a new pod on the orchestrator, with the probe from the [orchestrator hardening runbook](orchestrator-hardening.md), step 1, and these targets:

   ```python
   for host, port in (("169.254.169.254", 80), ("REPLACE_WITH_WORKSPACE_ENDPOINT_IP", 443), ("10.40.0.4", 6443)):
   ```

   Expected: `169.254.169.254:80 timeout`, the endpoint `timeout`, and `10.40.0.4:6443 open`. The API server is the control: it shows that the pod ran and has a network. The same two connections from the orchestrator itself open.

## Alert rules, flow logs, and drills

9. Apply the platform root as the platform identity: the 13 alert rules, the workbook, and the drill file in the audit collection rule.

   ```bash
   cd REPLACE_WITH_CHECKOUT/infra/platform
   source REPLACE_WITH_CRED_DIR/platform.env
   terraform plan -out=alerts.tfplan
   terraform apply alerts.tfplan
   ```

   Expected: 14 added and 1 changed in place, the audit collection rule.

10. Apply the bootstrap root as the operator: the four Activity Log rules, then the flow logs and their storage. Platform identity variables left in the shell make Terraform sign in as that identity, which is refused, so clear them first. The flow logs read the networks and the workspace by name, so the platform root comes first.

    ```bash
    cd ../bootstrap
    unset ARM_CLIENT_ID ARM_CLIENT_CERTIFICATE_PATH ARM_TENANT_ID
    export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
    terraform plan -out=monitoring.tfplan
    terraform apply monitoring.tfplan
    ```

    Expected: 8 added: four Activity Log rules, two storage accounts, two flow logs. Upload the state copy, as in step 1.

11. Fire each alert once. Each drill is put back after it.

    | Rule | Drill | Put back |
    | --- | --- | --- |
    | `role-assignments` | Any role assignment written or deleted. On 2026-10-18, the flow log role's assignments, before the flow logs moved to this root | Nothing to put back |
    | `security-groups` | `az network nsg update -g rg-aisec-platform -n nsg-aisec-platform-monitoring --set tags.aisec-drill=1` | `--remove tags.aisec-drill` |
    | `security-rules` | `az network nsg rule update ... -n allow-agents-from-router --description "alert drill"` | The description it had |
    | `policy-assignments` | `az policy assignment update -n deny-public-ip-on-interface -g rg-aisec-platform --description "alert drill"` | The description it had |
    | `heartbeat-missing` | On the router, `sudo systemctl stop azuremonitoragent azuremonitor-coreagent azuremonitor-agentlauncher azuremonitor-astextension` for 21 minutes | `start` the same units |
    | `journal-missing` | On the orchestrator, `sudo systemctl stop aisec-journal-pull.timer` for 21 minutes | `start` the timer |
    | `disk-or-memory` | On the edge, `fallocate` a file in `/var/tmp` that takes `/` to 87 percent, for 21 minutes | Delete the file |
    | `audit-sequence`, `copy-marker` | On the orchestrator, create `/var/log/aisec/alert-drill.jsonl` empty, then append two lines of one `drill-` start with `seq` 1 and 3, and one line with `"event":"copy"` | The lines stay: the file is the drill's record |
    | `squid-refused-orchestrator` | From the orchestrator, `curl -x http://10.45.0.4:3128 https://example.com/` | Nothing |
    | `fetch-window-opened` | On the edge, `sudo aisec-fetch-window open 1`, then `close` | Closed by the drill |
    | `denied-flow-to-internet` | From the worker and the orchestrator, a TCP connection to `1.1.1.1:443` | Nothing |
    | `ssh-login-accepted`, `ssh-login-failed` | Any login, and one with an expired certificate offered | Nothing |
    | `tool-refusal-burst` | 25 calls without a token from the worker | Nothing |
    | `failed-unit` | On the edge, `sudo systemd-run --unit=aisec-alert-drill /bin/false`, then `systemctl reset-failed` | Reset by the drill |

    Expected: nothing visible yet. Each rule needs its window and ingestion time.

12. List what fired, with the operator's sign-in.

    ```bash
    SUB=$(az account show --query id -o tsv)
    az rest --method get \
      --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview&timeRange=1d" \
      --query "value[].[properties.essentials.alertRule, properties.essentials.monitorCondition, properties.essentials.startDateTime]" -o tsv
    ```

    Expected: one alert for each rule in step 11, within 40 minutes of its drill. The stateful rules resolve once the drill is put back.

13. Run the checks.

    Expected: every check passes, `O.14` to `O.17` included. `O.17` needs traffic analytics' first write from both flow logs, up to an hour after step 10.

## Daily cap

The cap is three times one measured day ([ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md)). Measure a day with no change to the VMs and the usual runs of the checks in it, since the checks repeat every day.

14. Read the day's billable volume, with the operator's sign-in. `REPLACE_WITH_DAY_START` is the start of the 24 hours, in UTC. Each `Usage` row covers one hour and its `TimeGenerated` is the end of it, so select hours by `StartTime`.

    ```bash
    WS=$(az monitor log-analytics workspace show -g rg-aisec-platform -n log-aisec --query customerId -o tsv)
    az rest --method post --resource https://api.loganalytics.io \
      --url "https://api.loganalytics.io/v1/workspaces/$WS/query" \
      --body '{"query":"Usage | where StartTime >= datetime(REPLACE_WITH_DAY_START) and StartTime < datetime(REPLACE_WITH_DAY_START) + 1d | where IsBillable == true | summarize MB = sum(Quantity) by DataType"}' \
      --query 'tables[0].rows' -o tsv
    ```

    Expected: one row for each billable table. On 2026-10-19, 66.60 MB in all, two thirds of it the worker's journal. An empty answer or 0 means the window is wrong: the agents send every minute.

15. Read the log agent's footprint across the same day, on the orchestrator, the edge, and the router. The worker has no agent.

    ```bash
    for vm in orchestrator edge router; do
      REPLACE_WITH_SSH "aisec-$vm" 'systemctl show -p Id,ActiveEnterTimestamp,CPUUsageNSec,MemoryCurrent,MemoryPeak \
        azuremonitoragent azuremonitor-coreagent azuremonitor-agentlauncher azuremonitor-astextension metrics-extension metrics-sourcer; free -m'
    done
    ```

    Expected: every unit started before the day did, so its counters cover the day. Add up the six units on each VM. CPU is `CPUUsageNSec` over the time since `ActiveEnterTimestamp`. On 2026-10-19, under 0.6 percent of one core on each VM, and about 290 MiB on the orchestrator, 250 MiB on the edge, and 220 MiB on the router.

16. Drill the cap before setting it. Read the reset hour, then plan and apply the platform root with a cap of 23 MB, about 30 minutes before the reset hour. By then the workspace has taken more than that since the last reset. After step 17 raises the cap, ingestion can start and stop for a while: 44 minutes on 2026-10-19 ([troubleshooting 10](../troubleshooting/10-raising-the-daily-cap-leaves-ingestion-flapping.md)). The reset hour should end that at the latest, which limits the loss. That part is reasoned, not observed.

    ```bash
    az monitor log-analytics workspace show -g rg-aisec-platform -n log-aisec \
      --query workspaceCapping.quotaNextResetTime -o tsv
    cd REPLACE_WITH_CHECKOUT/infra/platform
    source REPLACE_WITH_CRED_DIR/platform.env
    terraform plan -var log_daily_cap_gb=0.023 -out=cap-drill.tfplan
    terraform apply cap-drill.tfplan
    ```

    Expected: the plan changes `daily_quota_gb` on `log-aisec` and nothing else. Then a `Warning` row in `_LogOperation`, category `Ingestion`, with `OverQuota` in its detail, and the workspace's `dataIngestionStatus` reads `OverQuota`: 10 minutes after the apply on 2026-10-19. `daily-cap` fires within 15 minutes of the row, from the rule's frequency, and fired after 6 on 2026-10-19. `journal-missing` fired 23 minutes after the last journal row. `heartbeat-missing` did not fire: heartbeats are not billable and kept arriving.

17. Once `daily-cap` has fired, set the cap. Write three times the day, in GB (MB divided by 1,000) and rounded up to the next 0.01 GB, as the default of `log_daily_cap_gb` in `infra/platform/variables.tf`, then plan and apply without the variable.

    ```bash
    terraform plan -out=cap.tfplan
    terraform apply cap.tfplan
    ```

    Expected: the plan changes `daily_quota_gb` from 0.023 to the new cap and nothing else. Ingestion may start and stop again: for 44 minutes on 2026-10-19. After its last start, `_LogOperation` has no new `OverQuota` row and rows arrive from all three VMs. On 2026-10-19, `journal-missing` resolved 24 minutes after the last start and `daily-cap` 46 minutes after it. Then run the checks, as in step 13.

## Undo

18. To take the monitoring away, remove `monitoring.tf`, `alerts.tf`, `flow-logs.tf`, and `workbook.tf` from the platform root and `monitoring.tf` from the bootstrap root, the `monitoring` subnet, the `allow_monitoring_out` rules, and the identity block, and apply. Azure refuses to delete a workspace or collection endpoint that is still in a Private Link Scope. Terraform removes the scoped resources first, from the dependency order.

   Expected: the agents are removed with their extensions. The hosts block stays in `/etc/hosts` until it is removed by hand. It points names nobody uses at an address nothing answers on.

## Rebuild

A VM rebuilt from its template gets its identity, its run command, and its agent in the same apply, because each depends on the VM. This is reasoned from the dependencies and has not run.
