# 08. The first monitoring apply stops on unregistered resource providers

Date: 2026-10-17
Milestone: 3a, edge network and monitoring

## Symptom

The first platform apply with the log store, from a saved plan, stopped on four errors ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-applies-3)):

```text
MissingSubscriptionRegistration: The subscription is not registered to use namespace 'Microsoft.OperationalInsights'.
MissingSubscriptionRegistration: The subscription is not registered to use namespace 'microsoft.insights'.
```

The first error came from the workspace. The other three came from the Private Link Scope and the two data collection endpoints. The resources that do not need either provider, the subnet, its security group, the rules, and the identities, were created.

## Cause

Confirmed from the error and the provider's documentation. A resource provider has to be registered on the subscription before anything of its type can be created. azurerm 5 registers no provider unless told to, and the platform identity has no right to register one: its role covers the platform group only ([ADR 0008](../decisions/0008-deployment-identities-and-bootstrap-scope.md)). Milestones 1 and 2 used only providers the subscription already had registered, so nothing showed this before.

## Fix

Register the two providers in the bootstrap root, as the operator, with `azurerm_resource_provider_registration`. Then apply the platform root again:

```bash
cd infra/bootstrap
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
cd ../platform
terraform plan -out=platform.tfplan
terraform apply platform.tfplan
```

The [monitoring runbook](../runbooks/monitoring.md) step 1 does this before the first platform apply.

## Verification

The bootstrap plan read `Plan: 2 to add`, and each registration took about three minutes. The second platform apply ended with `Apply complete! Resources: 28 added, 0 changed, 0 destroyed.`, and the full check run after it read `252 passed, 0 failed`. The order in the runbook, registrations first, has not run on an empty subscription.
