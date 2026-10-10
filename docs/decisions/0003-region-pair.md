# 0003. Sweden Central for the platform, Denmark East for targets

Status: Accepted
Date: 2026-10-10

## Context

Platform and targets run in different regions ([0002](0002-separate-platform-and-target-infrastructure.md)). The regions should be close to each other. West Europe is excluded because of its capacity history.

Each region allows 4 vCPUs. VM size availability differs sharply by region for this subscription, so the choice was made from account-specific evidence, not from the public region list. Commands and full results are in the [preflight worklog](../worklogs/0000-azure-preflight.md).

## Options

Results for general-purpose 2-vCPU sizes, read on 2026-10-10.

| Region | VM sizes restricted for the subscription | Usable B-series and D-series 2-vCPU sizes | Zones for those sizes |
| --- | --- | --- | --- |
| Sweden Central | 300 of 1252 | B v2, D v5, D v6, D v7, including Arm | 1, 2, 3 |
| Denmark East | 216 of 722 | B v2, D v5, D v6 | 1, 2, 3 |
| Poland Central | 341 of 1045 | B v2, D v5, D v6, D v7 | 3 only |
| Norway East | 793 of 865 | None. Only FX (42 GB) and L-series (16 GB) | 2, 3 |
| Germany West Central | 937 of 1297 | D v7 only | Not checked |
| North Europe | 1163 of 1303 | None | Not applicable |

All regions listed show a regional limit of 4 vCPUs with none in use.

## Decision

- **Platform: Sweden Central.** The widest choice of small sizes in the area, including Arm sizes with two physical cores per 2 vCPUs for CPU inference.
- **Targets: Denmark East.** The closest region with unrestricted B-series and D-series sizes in all zones.
- **Fallback for targets: Poland Central**, if Denmark East lacks capacity at deployment time.

## Trade-offs

- **Listing is not capacity.** An unrestricted size can still fail to allocate. The fallback exists for that case.
- **Denmark East is a newer region.** Service coverage is narrower than in older regions. Virtual networks, storage, Key Vault, and Bastion are listed there. Other services are checked when they are needed.
- **B-series prices for Denmark East were not returned by the retail price API.** `Standard_D2as_v5` is listed at USD 0.104 per hour there, against USD 0.092 in Sweden Central. Target sizes are priced again before provisioning.
- **Cross-region traffic is metered.** Global peering is listed at USD 0.035 per GB in each direction for both regions.
- **Restrictions can change.** They are specific to the subscription and were observed to change after a resource provider registration. Re-read them before each compute milestone.
