# 09. Traffic analytics refuses a flow log written by the platform identity

Date: 2026-10-18
Milestone: 3a, edge network and monitoring

## Symptom

The platform apply with the alert rules and the flow logs created 16 of 18 resources. Both flow logs failed with `TAUserDoesNotHavePermissions` ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-applies-4)). The platform identity held a custom role with the flow log actions on both network watchers at the time. Azure kept both flow logs, in state `Failed`.

## Cause

Confirmed from the error and the Azure state. Traffic analytics creates a data collection rule and endpoint of its own for each flow log, prefixed `NWTA`, and Azure checks the right to create them on the workspace's subscription. The platform identity is Contributor on the platform group only ([ADR 0008](../decisions/0008-deployment-identities-and-bootstrap-scope.md)), so a role on the watchers is not enough. Granting it collection rule and endpoint writes on the whole subscription would have reached past its group for the first time, into the targets' group too.

## Fix

Write the flow logs and their storage in the bootstrap root, as the operator ([ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md)). The flow logs Azure kept in state `Failed` block the new ones under the same names, so delete them first:

```bash
az network watcher flow-log delete --location REPLACE_WITH_REGION --name REPLACE_WITH_FLOW_LOG_NAME
cd infra/bootstrap
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
```

The custom role and its assignments were removed in the same change. The [monitoring runbook](../runbooks/monitoring.md) step 10 applies the flow logs from the bootstrap root.

## Verification

The bootstrap apply ended with `2 added`, and plans of both roots read `No changes`. `O.16` reads both flow logs enabled, with traffic analytics on every 10 minutes, and passes. Traffic analytics then created its `NWTA` resources and processed the edge's flow log. It has never processed the platform's, which is a separate problem: an [accepted gap](../security/accepted-risks.md), with no known cause.
