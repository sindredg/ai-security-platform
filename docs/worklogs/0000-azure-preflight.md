# 0000. Azure preflight

Date: 2026-10-10
Milestone: 0, documentation baseline and preflight

## Summary

Read-only checks of the subscription established the compute budget and the regions the design is built on. One change was made: the `Microsoft.Compute` resource provider was registered so that quota could be read. No resources were created.

| Result | Value |
| --- | --- |
| Regional vCPU limit | 4 in every region checked, 0 in use |
| GPU quota | 0 for current GPU families |
| Platform region | Sweden Central |
| Target region | Denmark East, with Poland Central as fallback |
| Existing networks | None, so no address conflicts |

## Subscription state

```bash
az account show --query "{state:state, cloud:environmentName}"
az role assignment list --all --query "[].{role:roleDefinitionName, scope:scope}"
az lock list --query "length(@)"
az policy assignment list --query "length(@)"
az network vnet list --query "length(@)"
```

| Check | Result |
| --- | --- |
| State | Enabled |
| Role of the signed-in user | Owner at subscription scope |
| Resource locks | 0 |
| Policy assignments | 0 |
| Virtual networks, private DNS zones | 0 |

### Resource providers

```bash
az provider list --query "[].{ns:namespace, state:registrationState}" -o table
```

| Provider | State after this work |
| --- | --- |
| `Microsoft.Compute` | Registered (changed in this worklog) |
| `Microsoft.Network` | NotRegistered |
| `Microsoft.Storage` | NotRegistered |
| `Microsoft.KeyVault` | NotRegistered |
| `Microsoft.ManagedIdentity` | NotRegistered |
| `Microsoft.ContainerService` | NotRegistered |

Providers the design needs are registered by the milestone that first uses them.

## Compute quota

Quota was unreadable until `Microsoft.Compute` was registered. See [troubleshooting 0001](../troubleshooting/0001-compute-quota-unreadable-before-provider-registration.md).

```bash
az provider register -n Microsoft.Compute --wait
az vm list-usage -l <region> -o json
```

| Quota | Sweden Central | Denmark East | Poland Central | Norway East | West Europe | West US 2 |
| --- | --- | --- | --- | --- | --- | --- |
| Total regional vCPUs | 0 / 4 | 0 / 4 | 0 / 4 | 0 / 4 | 0 / 4 | 0 / 4 |
| B-series v2 families (`Bsv2`, `Basv2`) | 0 / 4 | 0 / 4 | 0 / 4 | 0 / 4 | 0 / 4 | 0 / 4 |
| D-series v5 (`DASv5`) | 0 / 4 | 0 / 4 | 0 / 4 | 0 / 4 | 0 / 4 | 0 / 4 |
| Spot vCPUs | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 |
| Current GPU families (T4, A10, A100, H100) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

Family limits do not add up. The regional total caps every family in that region. Quota counts deallocated VMs as well as running ones ([Check vCPU quotas](https://learn.microsoft.com/azure/virtual-machines/quotas)).

## VM size restrictions

Sizes can be listed in a region and still be unavailable to a specific subscription. The SKU API reports this as a `NotAvailableForSubscription` restriction.

```bash
az rest --method get \
  --url "https://management.azure.com/subscriptions/<subscription-id>/providers/Microsoft.Compute/skus?api-version=2021-07-01&\$filter=location eq '<region>'"
```

Counts are VM sizes with a location restriction, out of VM sizes listed, read after provider registration.

| Region | Restricted / listed | 2-vCPU sizes without a restriction |
| --- | --- | --- |
| Belgium Central | 128 / 782 | B v2, D v4 to v6 |
| Denmark East | 216 / 722 | B v2, D v5, D v6. Zones 1 to 3 |
| Spain Central | 217 / 1047 | B v2, D v4 to v7, including Arm |
| Austria East | 249 / 785 | B v2, D v5, D v6 |
| Sweden Central | 300 / 1252 | B v2, D v5 to v7, F v6 and v7, including Arm. Zones 1 to 3 |
| Poland Central | 341 / 1045 | B v2, D v5 to v7. Zone 3 only |
| West US 2 | 412 / 1344 | B v2 and D v5 as non-zonal only, v7 in zones 1 to 3 |
| West Europe | 564 / 1427 | Intel B v2, D v5, D v6. Mostly zone 1 only |
| Italy North | 783 / 1154 | D v7 and confidential sizes |
| Norway East | 793 / 865 | FX (42 GB) and `L2s_v4` (16 GB) only |
| UK West | 818 / 921 | FX only |
| France Central | 860 / 1135 | D v7 only |
| Switzerland North | 917 / 1079 | E v7 only |
| Germany West Central | 937 / 1297 | D v7, some F v6, and confidential sizes |
| North Europe | 1163 / 1303 | Confidential sizes only |
| Germany North, Norway West | All | None |

Older families, including `Standard_B2s`, `Standard_D2s_v3`, and `Standard_DS2_v2`, are restricted in Sweden Central, Norway East, West Europe, and West US 2.

An unrestricted listing does not guarantee capacity at deployment time.

## Service availability

```bash
az provider show -n <namespace> \
  --query "resourceTypes[?resourceType=='<type>'].locations | [0]"
```

Virtual networks, storage accounts, Key Vault, and Bastion list Sweden Central, Denmark East, and Poland Central.

## Prices

List prices in USD from the Azure Retail Prices API (`https://prices.azure.com/api/retail/prices`), Linux, pay-as-you-go, read on 2026-10-10.

| Item | Sweden Central | Denmark East | Poland Central |
| --- | --- | --- | --- |
| `Standard_B2as_v2` (2 vCPU, 8 GB) per hour | 0.0778 | Not returned | 0.0864 |
| `Standard_B2als_v2` (2 vCPU, 4 GB) per hour | 0.0389 | Not returned | 0.0432 |
| `Standard_D2as_v5` (2 vCPU, 8 GB) per hour | 0.0920 | 0.1040 | 0.1040 |
| `Standard_D2ps_v6` (Arm, 2 vCPU, 8 GB) per hour | 0.0748 | 0.0913 | 0.0838 |
| Global peering per GB, each direction | 0.035 | 0.035 | Not read |
| Standard SSD 32 GB (E4) per month | 2.40 | Not read | Not read |
| Standard SSD 64 GB (E6) per month | 4.80 | Not read | Not read |

## Limitations

- B-series prices for Denmark East were not returned by the price API. The sizes are listed as unrestricted there. Price them before provisioning.
- Network quotas were not read because `Microsoft.Network` is not registered.
- Capacity was not tested. No VM was created.
- Restrictions are specific to the subscription and changed once during this work. Re-read them before each compute milestone.

## Remaining work for this milestone

- Review of the architecture, roadmap, and decision records.
