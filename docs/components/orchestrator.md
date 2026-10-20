# Orchestrator

The one trusted machine. It runs the cluster, copies software to the other machines, and is the only one that downloads for them. It is not on the mesh VPN: operator sessions reach it through the router.

| | |
| --- | --- |
| State | Built on 2026-10-11, rebuilt from its template on 2026-10-13 ([worklog](../worklogs/0002-platform-compute.md#orchestrator-rebuild)). Verified by the `HO`, `K`, `E`, and `A` checks, which passed in the run on 2026-10-19 ([last run](../validation/README.md#last-run)) |
| Where | Sweden Central, `snet-orchestrator`, fixed private address `10.40.0.4` |
| Size | `Standard_B2as_v2`: 2 vCPUs, 8 GiB, x64 |
| Image | Ubuntu 26.04 LTS, `Canonical:ubuntu-26_04-lts:server` |
| Disk | 64 GB, Standard SSD |
| Boot | Trusted Launch with Secure Boot and a virtual TPM |
| Defined in | `infra/platform/compute.tf`, `infra/platform/cloud-init/orchestrator.yaml.tftpl` |
| Decisions | [0001](../decisions/0001-k3s-for-initial-orchestration.md), [0005](../decisions/0005-ai-workers-on-a-separate-vm.md), [0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md), [0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) |
| Way out | None of its own. `apt`, the operator's fetches, and containerd's image pulls go through Squid on the edge, since 2026-10-17 ([package proxy](package-proxy.md)) |

## What runs on it

| Service | Job | Page |
| --- | --- | --- |
| `k3s` | The cluster. One server. The tool service runs in it | [K3s](k3s.md) |
| `aisec-pod-egress` | Loads the host rule that drops forwarded traffic from pods to anything but pods, and traffic from pods to the host except ports 6443 and 10250 | [ADR 0018](../decisions/0018-a-host-rule-keeps-pods-off-the-internet.md), [ADR 0023](../decisions/0023-the-host-rule-limits-what-pods-reach-on-the-host.md), [containment](../validation/containment.md#the-orchestrators-side) |
| `aisec-audit-copy` | Copies the tool service's audit lines into an append-only file. Running since 2026-10-16 (`L.1`) | [Audit log](../security/audit-log.md) |
| `aisec-journal-pull.timer` | Pulls the worker's journal every five minutes into an append-only file. Running since 2026-10-16 (`J.1`) | [Audit log](../security/audit-log.md#the-workers-journal) |
| `ssh` | Administration. The administrator account takes only the operator's certificate, and may forward to the API server on loopback and nowhere else, since 2026-10-16 (`HO.17`, `A.8`) | [Validation: host hardening](../validation/host-hardening.md), [access](../validation/access.md) |

## First boot

cloud-init writes every configuration file, then one script does the rest in order: kernel settings, file modes, K3s from a binary and an install script that are both fetched through the edge and checked against pinned checksums, two cluster settings the Kubernetes benchmark asks for, the `baseline` label on `kube-system`, the audit copier once the kubelet has made `/var/log/pods`, the journal puller with its own key, and a key pair for copying files to the other machines.

The two cluster settings wait for the API: no token on the default service account of each namespace K3s creates, and mode `600` on the certificate files. If the API never answers, the script stops and leaves no `/var/lib/aisec-first-boot.done`. Tested on the live system: the VM was rebuilt from the template on 2026-10-13, and checks `K.5` and `K.6` passed with neither setting applied by hand. The first two tries found no service account yet, and the retry carried it. The failure path, an API that never answers, has not been seen on the live system.

The K3s download needs a fetch window open on the edge, so a rebuild starts with one ([edge runbook](../runbooks/edge-vm.md#rebuild-the-orchestrator)). The template without the mesh agent and without Squid has not run on a first boot.

Custom data is ignored after creation. A change to the template does not reach a running VM. It takes a rebuild, or the same change by hand.

## Measured

About 20 minutes after boot, with an empty cluster: 1.0 of 7.9 GiB memory used, CPU 98 to 99 % idle, 2.9 GB of disk. cloud-init finished 54 seconds after boot. On the rebuild of 2026-10-13, with the two cluster settings in the script, it finished after 78 seconds.

## Validation

`A`, `K`, `E`, `P.12` to `P.15`, `U.1`, `U.10`, `U.11`, `T`, `L`, `J`, and `HO` in the [validation pages](../validation/README.md).

## Limits

- **It is the supply chain.** What it copies to the worker and the targets is what runs there.
- **A compromise of it is not contained.** It holds every credential that matters. Its mesh node moved to the router, and its way out to the edge, on 2026-10-17 ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md), [ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md), [worklog](../worklogs/0004-edge-network-and-monitoring.md#the-edge-vm)). During a fetch window it can still upload to a listed host (T40).
- **No encryption at host.** The subscription feature is not registered.
- **Rebuilt once, with an empty cluster.** The [rebuild](../worklogs/0002-platform-compute.md#orchestrator-rebuild) on 2026-10-13 proves the template. It says nothing about bringing workloads back.

## Official documentation

- [Trusted Launch for Azure VMs](https://learn.microsoft.com/azure/virtual-machines/trusted-launch)
- [Boot diagnostics](https://learn.microsoft.com/azure/virtual-machines/boot-diagnostics)
- [cloud-init](https://cloudinit.readthedocs.io/en/latest/)
- [Ubuntu automatic updates](https://documentation.ubuntu.com/server/how-to/software/automatic-updates/)
