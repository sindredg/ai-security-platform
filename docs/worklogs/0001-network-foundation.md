# 0001. Network foundation

Date: 2026-10-10
Milestone: 1, network foundation

## Summary

State storage, two deployment identities, both virtual networks, their security groups, and the peering exist. No compute was created. The procedure is in the [network foundation runbook](../runbooks/network-foundation.md).

| Gate | Result |
| --- | --- |
| `terraform plan` is clean for both roots after apply | Met. Exit `0` for both roots and for the bootstrap root |
| Peering state is `Connected` in both directions | Met. Both `Connected` and `FullyInSync` |
| Effective rules show default deny between the networks | Partly met. Configured rules verified on all six subnets. Effective rules need a network interface, so that check moves to milestone 2 |
| Neither root's identity can modify the other side | Met. Eight denied operations per identity, two allowed controls |

## Versions

Read from the official sources on 2026-10-10 and pinned exactly.

| Tool | Version | Source |
| --- | --- | --- |
| Terraform | 1.16.5 | `checkpoint-api.hashicorp.com/v1/check/terraform`, binary checked against the release `SHA256SUMS` |
| `hashicorp/azurerm` | 5.9.0 | `registry.terraform.io/v1/providers/hashicorp/azurerm` |
| `hashicorp/azuread` | 3.10.0 | `registry.terraform.io/v1/providers/hashicorp/azuread` |
| `hashicorp/random` | 3.9.1 | `registry.terraform.io/v1/providers/hashicorp/random` |

The lock files carry hashes for `linux_amd64` and `linux_arm64`.

azurerm 5.x changed two things this work depends on. It registers no resource providers unless told to, so registration is an explicit step. And `azurerm_storage_container` takes `storage_account_id`, which creates the container through the management API and needs no data-plane role for the operator.

## Resource providers

```bash
az provider register -n Microsoft.Network --wait
az provider register -n Microsoft.Storage --wait
```

| Provider | State |
| --- | --- |
| `Microsoft.Network` | Registered |
| `Microsoft.Storage` | Registered |

## Bootstrap root

Run as the operator, with local state.

```bash
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
terraform plan -detailed-exitcode
```

| Step | Result |
| --- | --- |
| Plan | 23 to add, 0 to change, 0 to destroy |
| Apply | `Apply complete! Resources: 23 added, 0 changed, 0 destroyed.` |
| Plan after apply | `No changes.` Exit `0` |

The certificate end date was one variable for both sides at apply time. It is now one variable per side, so a rotation touches one credential. With both set to the applied value, `terraform plan -detailed-exitcode` reports `No changes.` and exits `0`.

State accounts, read back:

```bash
az storage account list --query "[?starts_with(name,'staisec')].{rg:resourceGroup, loc:location, sharedKey:allowSharedKeyAccess, publicBlob:allowBlobPublicAccess, tls:minimumTlsVersion, sku:sku.name}" -o table
```

| Resource group | Region | Shared key access | Public blob access | Minimum TLS | SKU |
| --- | --- | --- | --- | --- | --- |
| `rg-aisec-platform-state` | `swedencentral` | False | False | TLS1_2 | Standard_LRS |
| `rg-aisec-targets-state` | `denmarkeast` | False | False | TLS1_2 | Standard_LRS |

Role assignments, read back with `az role assignment list --all --assignee <object-id>`:

| Identity | Role | Scope |
| --- | --- | --- |
| `aisec-platform-deploy` | Contributor | `rg-aisec-platform` |
| `aisec-platform-deploy` | Storage Blob Data Contributor | Platform state account |
| `aisec-platform-deploy` | `aisec-virtual-network-peer` | `rg-aisec-targets` |
| `aisec-targets-deploy` | Contributor | `rg-aisec-targets` |
| `aisec-targets-deploy` | Storage Blob Data Contributor | Target state account |
| `aisec-targets-deploy` | `aisec-virtual-network-peer` | `rg-aisec-platform` |

Neither identity has any other assignment.

## Network roots

Each root ran as its own identity, authenticated by certificate, with state in its own account.

| Apply | Identity | Plan | Result |
| --- | --- | --- | --- |
| Platform, without peering | Platform | 7 to add | 7 added |
| Targets, with peering | Targets | 14 to add | 14 added |
| Platform, peering only | Platform | 1 to add | 1 added |

```bash
terraform plan -detailed-exitcode
```

| Root | Resources in state | Plan after apply |
| --- | --- | --- |
| `infra/platform` | 9 | `No changes.` Exit `0` |
| `infra/targets` | 15 | `No changes.` Exit `0` |
| `infra/bootstrap` | 25 | `No changes.` Exit `0` |

The counts are `terraform state list` entries, data sources included: one resource group in each network root, and the subscription and client configuration in the bootstrap root. That is why the bootstrap apply reports 23 resources and its state lists 25.

## Peering

```bash
az network vnet peering list -g rg-aisec-<side> --vnet-name vnet-aisec-<side> \
  --query "[].{name:name, state:peeringState, sync:peeringSyncLevel, vnetAccess:allowVirtualNetworkAccess, forwarded:allowForwardedTraffic, gwTransit:allowGatewayTransit}" -o table
```

| Peering | State | Sync | Network access | Forwarded traffic | Gateway transit |
| --- | --- | --- | --- | --- | --- |
| `peer-platform-to-targets` | Connected | FullyInSync | True | False | False |
| `peer-targets-to-platform` | Connected | FullyInSync | True | False | False |

The custom role with only `Microsoft.Network/virtualNetworks/peer/action` on the remote side was enough. Neither identity needed read access to the other network.

## Subnets and rules

```bash
az network vnet subnet list -g rg-aisec-<side> --vnet-name vnet-aisec-<side> \
  --query "[].{subnet:name, prefix:addressPrefix || addressPrefixes[0], nsg:networkSecurityGroup.id, defaultOutbound:defaultOutboundAccess}" -o tsv
```

| Subnet | Range | Security group | Default outbound access |
| --- | --- | --- | --- |
| `snet-orchestrator` | `10.40.0.0/27` | `nsg-aisec-platform-orchestrator` | False |
| `snet-worker` | `10.40.0.32/27` | `nsg-aisec-platform-worker` | False |
| `snet-netbox` | `10.50.0.0/27` | `nsg-aisec-targets-netbox` | False |
| `snet-consumer` | `10.50.0.32/27` | `nsg-aisec-targets-consumer` | False |
| `snet-unintended` | `10.50.0.64/27` | `nsg-aisec-targets-unintended` | False |
| `snet-rehearsal` | `10.50.1.0/27` | `nsg-aisec-targets-rehearsal` | False |

Configured rules, in priority order:

```bash
az network nsg show -g <resource-group> -n <security-group> \
  --query "sort_by(securityRules,&priority)[].[priority,direction,access,protocol,sourceAddressPrefix,destinationAddressPrefix,destinationPortRange,name]" -o tsv
```

| Security group | Priority | Direction | Access | Protocol | Source | Destination | Port | Rule |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Orchestrator | 100 | Inbound | Deny | Any | `10.50.0.0/20` | Any | Any | `deny-from-targets` |
| Orchestrator | 1000 | Outbound | Allow | TCP | `10.40.0.0/27` | `10.40.0.32/27` | 22 | `allow-ssh-to-worker` |
| Orchestrator | 1010 | Outbound | Allow | TCP | `10.40.0.0/27` | `10.50.0.0/20` | 22 | `allow-ssh-to-targets` |
| Worker | 100 | Inbound | Deny | Any | `10.50.0.0/20` | Any | Any | `deny-from-targets` |
| Worker | 100 | Outbound | Deny | Any | Any | `10.50.0.0/20` | Any | `deny-to-targets` |
| Worker | 110 | Outbound | Deny | Any | Any | `Internet` | Any | `deny-to-internet` |
| Worker | 1000 | Inbound | Allow | TCP | `10.40.0.0/27` | `10.40.0.32/27` | 22 | `allow-ssh-from-orchestrator` |
| Each of the four target groups | 1000 | Inbound | Allow | TCP | `10.40.0.0/27` | The group's own subnet | 22 | `allow-ssh-from-orchestrator` |
| All six | 4096 | Inbound | Deny | Any | Any | Any | Any | `deny-all-inbound` |
| All six | 4096 | Outbound | Deny | Any | Any | Any | Any | `deny-all-outbound` |

The built-in rules that the baseline overrides are still there, at lower precedence: `AllowVnetInBound` and `AllowVnetOutBound` at 65000, `AllowAzureLoadBalancerInBound` and `AllowInternetOutBound` at 65001. With peering in place, the `VirtualNetwork` tag in the first two covers the other network. The 4096 rules are what make the peering deny-by-default.

```bash
az network public-ip list --query "length(@)"
az network nic list --query "length(@)"
```

Both return `0`.

## Identity separation

Each identity signed in with its certificate in a throwaway CLI profile and ran the same set of commands. The commands are in step 12 of the runbook, except the rule addition, which was `az network nsg rule create` with an allow-all inbound rule against one security group on the other side.

| Operation | Expected | Platform identity | Target identity |
| --- | --- | --- | --- |
| Read own virtual network | Allowed | Exit 0 | Exit 0 |
| List blobs in own state container | Allowed | Exit 0 | Exit 0 |
| Read the other side's virtual network | Denied | `AuthorizationFailed` | `AuthorizationFailed` |
| Create a security group in the other side's resource group | Denied | `AuthorizationFailed` | `AuthorizationFailed` |
| Add a rule to one of the other side's security groups | Denied | `AuthorizationFailed` | `AuthorizationFailed` |
| Delete the other side's peering | Denied | `AuthorizationFailed` | `AuthorizationFailed` |
| List blobs in the other side's state container | Denied | Permission error, exit 1 | Permission error, exit 1 |
| List the keys of its own state account | Denied | `AuthorizationFailed` | `AuthorizationFailed` |
| Create a resource group | Denied | `AuthorizationFailed` | `AuthorizationFailed` |
| Assign a role in its own resource group | Denied | `AuthorizationFailed` | `AuthorizationFailed` |

The blob listing fails in the data plane, so the CLI prints "You do not have the required permissions needed to perform this operation" instead of an error code.

Afterwards, read as the operator: no `nsg-probe` security group exists, `rg-aisec-probe` does not exist, and both peerings are still `Connected`.

## Limitations

- **Effective rules were not read.** Azure computes them per network interface, and there are none. The configured rules and subnet associations are verified. Milestone 2 has to read the effective rules on a real interface and test the denied paths with traffic.
- **Only SSH is open.** The architecture lists more allowed flows: collection, tool services, dispatch, the inventory API. Their ports are not decided, so no rule exists for them yet. Each arrives with the service that listens on it.
- **Nothing stops a public IP address in a workload resource group.** Each identity is Contributor on its own group and could create one. No policy outside the roots denies it yet.
- **State accounts accept connections from any network.** Access needs a Microsoft Entra token with a data role, and shared keys are off, but there is no network restriction. Adding one would put an operator address in configuration.
- **State is locally redundant.** It survives the workstation, not the region.
- **The bootstrap state is a local file.** It has no copy yet.
- **Built once.** The runbook was written from this build. Rotation, removal, and a rebuild from scratch have not been run.
- **Deployment keys have no passphrase.** File permissions on the operator machine are their only protection.
