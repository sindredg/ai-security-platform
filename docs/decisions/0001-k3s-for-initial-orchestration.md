# 0001. K3s on one VM for initial orchestration

Status: Accepted
Date: 2026-10-10

## Context

The platform needs a Kubernetes API for Argo Workflows and a small set of trusted services. The subscription allows 4 vCPUs per region. The same region must also hold a VM for AI workers.

The AKS documentation states that a system node pool must contain at least two nodes, each with at least 4 vCPUs and 4 GB of memory, and that B-series sizes are not supported for system pools ([Manage system node pools](https://learn.microsoft.com/azure/aks/use-system-pools)). That is 8 vCPUs before any workload. A second page states a lower floor of 2 vCPUs and 4 GB below which sizes may be rejected ([AKS quotas and SKUs](https://learn.microsoft.com/azure/aks/quotas-skus-regions)). Which limit the API enforces was not tested.

## Options

| Option | vCPUs for the control plane | Fit |
| --- | --- | --- |
| AKS at the documented system pool minimum | 8 | Does not fit a 4-vCPU region |
| AKS with one small system node | 2 to 4 | Outside the documented requirement, behavior unverified, no upgrade headroom |
| K3s server on one VM | 2 | Fits, leaves 2 vCPUs for the worker VM |
| No Kubernetes, workflows as systemd units or CI jobs | 0 to 2 | Fits, but gives up Argo, its UI, and the Kubernetes skills the project is meant to exercise |

## Decision

Run a single K3s server on one 2-vCPU VM. It hosts trusted orchestration only. AI workers run elsewhere, see [0005](0005-ai-workers-on-a-separate-vm.md).

Avoid distribution-specific assumptions in workload definitions where practical, so that a managed cluster remains a later deployment profile.

## Trade-offs

- **Operations move to the project.** OS patching, K3s upgrades, backup, and restore are not managed by the provider.
- **No high availability.** One server and one datastore. A VM failure stops orchestration until it restarts.
- **Managed add-ons are unavailable.** Managed workload identity, managed ingress, and managed monitoring have no direct equivalent and must be designed separately.
- **Tight capacity.** K3s documents a minimum of 2 cores and 2 GB for a server, before workloads ([K3s requirements](https://docs.k3s.io/installation/requirements)). Component footprint is measured before optional components are added.
