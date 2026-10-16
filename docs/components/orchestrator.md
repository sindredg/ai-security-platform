# Orchestrator

The one trusted machine. It runs the cluster, routes for the mesh VPN, copies software to the other machines, and is the only one that reaches the internet.

| | |
| --- | --- |
| State | Built |
| Where | Sweden Central, `snet-orchestrator`, fixed private address `10.40.0.4` |
| Size | `Standard_B2as_v2`: 2 vCPUs, 8 GiB, x64 |
| Image | Ubuntu 26.04 LTS, `Canonical:ubuntu-26_04-lts:server` |
| Disk | 64 GB, Standard SSD |
| Boot | Trusted Launch with Secure Boot and a virtual TPM |
| Defined in | `infra/platform/compute.tf`, `infra/platform/cloud-init/orchestrator.yaml.tftpl` |
| Decisions | [0001](../decisions/0001-k3s-for-initial-orchestration.md), [0005](../decisions/0005-ai-workers-on-a-separate-vm.md), [0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md) |

## What runs on it

| Service | Job | Page |
| --- | --- | --- |
| `k3s` | The cluster. One server. The tool service runs in it | [K3s](k3s.md) |
| `tailscaled` | Mesh VPN agent and subnet router for both networks | [Mesh VPN](mesh-vpn.md) |
| `aisec-mss-clamp` | Rewrites the TCP segment size on routed connections | [Mesh VPN](mesh-vpn.md) |
| `aisec-pod-egress` | Loads the host rule that drops forwarded traffic from pods to anything but pods | [ADR 0018](../decisions/0018-a-host-rule-keeps-pods-off-the-internet.md), [containment](../validation/containment.md#the-orchestrators-side) |
| `squid` | Package proxy for the worker | [Package proxy](package-proxy.md) |
| `aisec-audit-copy` | Copies the tool service's audit lines into an append-only file. Running since 2026-10-16 (`L.1`) | [Audit log](../security/audit-log.md) |
| `aisec-journal-pull.timer` | Pulls the worker's journal every five minutes into an append-only file. Running since 2026-10-16 (`J.1`) | [Audit log](../security/audit-log.md#the-workers-journal) |
| `ssh` | Administration, key only | [Validation: host hardening](../validation/host-hardening.md) |

## First boot

cloud-init writes every configuration file, then one script does the rest in order: kernel settings, the segment size clamp, file modes, the mesh VPN agent from its signed repository, the proxy, K3s from a binary and an install script that are both checked against pinned checksums, two cluster settings the Kubernetes benchmark asks for, the audit copier once the kubelet has made `/var/log/pods`, the journal puller with its own key, and a key pair for copying files to the other machines.

The two cluster settings wait for the API: no token on the default service account of each namespace K3s creates, and mode `600` on the certificate files. If the API never answers, the script stops and leaves no `/var/lib/aisec-first-boot.done`. Tested on the live system: the VM was rebuilt from the template on 2026-10-13, and checks `K.5` and `K.6` passed with neither setting applied by hand. The first two tries found no service account yet, and the retry carried it. The failure path, an API that never answers, has not been seen on the live system.

Custom data is ignored after creation. A change to the template does not reach a running VM. It takes a rebuild, or the same change by hand.

## Measured

About 20 minutes after boot, with an empty cluster: 1.0 of 7.9 GiB memory used, CPU 98 to 99 % idle, 2.9 GB of disk. cloud-init finished 54 seconds after boot. On the rebuild of 2026-10-13, with the two cluster settings in the script, it finished after 78 seconds.

## Validation

`A`, `K`, `R`, `E`, `P`, `U`, `T`, `L`, `J`, and `HO` in the [validation pages](../validation/README.md).

## Limits

- **It is the supply chain.** What it copies to the worker and the targets is what runs there.
- **A compromise of it is not contained.** It holds every credential that matters and reaches any host on TCP 443 and 80. Milestone 3a takes away its way out and its mesh node ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md), [ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md)). Not built.
- **No encryption at host.** The subscription feature is not registered.
- **Rebuilt once, with an empty cluster.** The [rebuild](../worklogs/0002-platform-compute.md#orchestrator-rebuild) on 2026-10-13 proves the template. It says nothing about bringing workloads back.

## Official documentation

- [Trusted Launch for Azure VMs](https://learn.microsoft.com/azure/virtual-machines/trusted-launch)
- [Boot diagnostics](https://learn.microsoft.com/azure/virtual-machines/boot-diagnostics)
- [cloud-init](https://cloudinit.readthedocs.io/en/latest/)
- [Ubuntu automatic updates](https://documentation.ubuntu.com/server/how-to/software/automatic-updates/)
