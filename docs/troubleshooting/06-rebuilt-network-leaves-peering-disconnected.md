# 06. A rebuilt network leaves the other half of the peering disconnected

Date: 2026-10-17
Milestone: 3a, edge network and monitoring

## Symptom

The target network was destroyed in Denmark East and built again in Poland Central, with the same name in the same resource group ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-targets-in-poland-central)). The apply created the network, the subnets, the security groups, and the associations, then failed on the target half of the peering:

```text
Error: waiting for Virtual Network Peering (... Virtual Network Peering Name: "peer-targets-to-platform") to be created:
unexpected status 400 (400 Bad Request) with error: RemotePeeringIsDisconnected: Cannot create or update peering
... because remote peering .../vnet-aisec-platform/virtualNetworkPeerings/peer-platform-to-targets referencing parent
virtual network .../vnet-aisec-targets is in Disconnected state.
```

A plan of the platform root reported no changes.

## Cause

Confirmed from the error and from Azure's state. Deleting the target network turned the platform half of the peering to `Disconnected` (read with `az network vnet peering show` after the destroy). The rebuilt network has the same resource ID, because the ID is built from the subscription, the group, and the name. So the platform half still names the right network, Terraform sees nothing to change, and Azure keeps the half disconnected. A disconnected half does not reconnect. It has to be re-created before the other side can create its half.

## Fix

Re-create the platform half with a forced replacement, then apply the target root again:

```bash
cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/platform
terraform plan -replace='module.network.azurerm_virtual_network_peering.this[0]' -out=platform.tfplan
terraform apply platform.tfplan
cd "$TARGETS"
terraform plan -out=targets.tfplan
terraform apply targets.tfplan
```

The [network foundation runbook](../runbooks/network-foundation.md#rebuild-the-target-network) now has this order as a procedure. In that order, the target apply should not fail. That is reasoned from the error, not run in that order.

## Verification

The platform plan showed 1 to add and 1 to destroy, the peering only. After its apply the platform half read `Initiated`. The target plan then showed 1 to add, and after its apply both halves read `Connected`. `Z.15` checks both halves and passed in the next full run, 159 of 159.
