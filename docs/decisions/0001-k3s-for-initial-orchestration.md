# 0001. K3s on one VM for initial orchestration

Status: Accepted
Date: 2026-10-10

## Context

The platform needs a Kubernetes API for Argo Workflows and a handful of trusted services. The subscription allows 4 vCPUs per region, and the same region also has to hold the AI worker VM.

AKS was the first plan. It does not fit. The AKS documentation says a system node pool must have at least two nodes, each with at least 4 vCPUs and 4 GB of memory, and that B-series sizes are not supported for system pools ([Manage system node pools](https://learn.microsoft.com/azure/aks/use-system-pools)). That is 8 vCPUs before a single workload runs.

A second page gives a lower floor of 2 vCPUs and 4 GB, below which sizes may be rejected ([AKS quotas and SKUs](https://learn.microsoft.com/azure/aks/quotas-skus-regions)). The two pages read as "what is supported" and "what the API refuses". Which one the API actually enforces was not tested, and building on the gap between them would be building on a guess.

Capacity is not the only argument. This is a security platform, and a managed cluster hides the layers a security platform most wants to shape. On AKS the control plane belongs to the provider: no access to the API server's flags, its audit policy, or the datastore. The nodes are reachable but not really owned either. They run the provider's image, and an upgrade replaces them. A self-managed cluster on a plain VM puts the OS, the kernel settings, the host firewall, and every control plane setting in the project's hands.

## Options

| Option | vCPUs for the control plane | Fit |
| --- | --- | --- |
| AKS at the documented system pool minimum | 8 | Does not fit a 4-vCPU region |
| AKS with one small system node | 2 to 4 | Outside the documented requirement, behavior unverified, no upgrade headroom |
| K3s server on one VM | 2 | Fits, and leaves 2 vCPUs for the worker VM |
| No Kubernetes, workflows as systemd units or CI jobs | 0 to 2 | Fits, but gives up Argo, its UI, and the Kubernetes work this project exists to exercise |

## Decision

Run a single K3s server on one 2-vCPU VM. It hosts trusted orchestration and nothing else. AI workers run elsewhere, see [0005](0005-ai-workers-on-a-separate-vm.md).

Two reasons, in order. It fits the compute budget, which AKS at its documented minimum does not. And it gives control down to the operating system: host hardening, API server and audit configuration, and the service account issuer are all set by the project instead of inherited from a managed service.

Keep distribution-specific assumptions out of workload definitions where practical, so a managed cluster stays possible later.

## Trade-offs

- **Control cuts both ways.** OS patching, K3s upgrades, backup, and restore are no longer the provider's problem.
- **No high availability.** One server, one datastore. If the VM dies, orchestration stops until it is back.
- **No managed add-ons.** Managed workload identity, ingress, and monitoring have no drop-in equivalent and each needs its own design.
- **It is tight.** K3s documents a minimum of 2 cores and 2 GB for a server, before any workload ([K3s requirements](https://docs.k3s.io/installation/requirements)). Optional components wait until the footprint is measured.
