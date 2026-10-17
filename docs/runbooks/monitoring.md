# Monitoring: operator procedure

Status: Implemented on 2026-10-17. Run once, on the live platform, between 22:50 and 23:50 UTC. Results are in the [milestone 3a worklog](../worklogs/0004-edge-network-and-monitoring.md#monitoring). The first platform apply stopped on two unregistered resource providers. Step 1 was added for that and ran before the second apply. Steps 6 to 8 ran with the same queries in a longer form. The alert rules, flow logs, and the workbook are not part of this procedure yet.

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

## Undo

9. To take the monitoring away, remove `monitoring.tf`, the `monitoring` subnet, the `allow_monitoring_out` rules, and the identity block, and apply. Azure refuses to delete a workspace or collection endpoint that is still in a Private Link Scope. Terraform removes the scoped resources first, from the dependency order.

   Expected: the agents are removed with their extensions. The hosts block stays in `/etc/hosts` until it is removed by hand. It points names nobody uses at an address nothing answers on.

## Rebuild

A VM rebuilt from its template gets its identity, its run command, and its agent in the same apply, because each depends on the VM. This is reasoned from the dependencies and has not run.
