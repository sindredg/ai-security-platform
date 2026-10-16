# 0003. Sweden Central for the platform, Denmark East for targets

Status: Accepted
Date: 2026-10-10

## Context

Platform and targets run in different regions ([0002](0002-separate-platform-and-target-infrastructure.md)). They should be close to each other. West Europe is out because of its capacity history.

Picking from the public region list turned out to be useless. Which VM sizes a subscription may actually deploy differs wildly by region, and each region allows only 4 vCPUs. Norway East, the obvious neighbor, offers this subscription nothing small except memory-heavy FX and storage-heavy L-series sizes. So the choice was made from what the subscription can really use. Commands and full results are in the [preflight worklog](../worklogs/0000-azure-preflight.md).

## Options

General-purpose 2-vCPU sizes, read on 2026-10-10.

| Region | VM sizes restricted for the subscription | Usable B-series and D-series 2-vCPU sizes | Zones for those sizes |
| --- | --- | --- | --- |
| Sweden Central | 300 of 1252 | B v2, D v5, D v6, D v7, including Arm | 1, 2, 3 |
| Denmark East | 216 of 722 | B v2, D v5, D v6 | 1, 2, 3 |
| Poland Central | 341 of 1045 | B v2, D v5, D v6, D v7 | 3 only |
| Norway East | 793 of 865 | None. Only FX (42 GB) and L-series (16 GB) | 2, 3 |
| Germany West Central | 937 of 1297 | D v7 only | Not checked |
| North Europe | 1163 of 1303 | None | Not applicable |

Every region listed has a limit of 4 vCPUs with none in use.

## Decision

- **Platform: Sweden Central.** The widest choice of small sizes nearby, including Arm sizes that give two physical cores per 2 vCPUs. That matters for CPU inference.
- **Targets: Denmark East.** The closest region where ordinary B-series and D-series sizes are unrestricted, in all three zones. [0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md) moves the targets to Poland Central and puts an edge VM in Denmark East.
- **Fallback for targets: Poland Central**, if Denmark East has no capacity on the day.

## Trade-offs

- **Listed is not the same as available.** An unrestricted size can still fail to allocate. That is what the fallback is for.
- **Denmark East is a newer region** with narrower service coverage. Virtual networks, storage, Key Vault, and Bastion are listed there. Anything else gets checked when it is needed.
- **B-series prices for Denmark East are missing from the retail price API.** `Standard_D2as_v5` is listed at USD 0.104 per hour there, against USD 0.092 in Sweden Central. Target sizes get priced again before provisioning.
- **Cross-region traffic is metered.** Global peering is listed at USD 0.035 per GB in each direction for both regions.
- **Restrictions move.** They are specific to the subscription, and one region's list changed during the preflight. Read them again before each compute milestone.
