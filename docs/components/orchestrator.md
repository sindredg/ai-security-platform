# Orchestrator

The one trusted machine. It runs the cluster, routes for the mesh VPN, feeds the other machines, and is the only one that reaches the internet.

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
| `k3s` | The cluster. One server, nothing deployed yet | [K3s](k3s.md) |
| `tailscaled` | Mesh VPN agent and subnet router for both networks | [Mesh VPN](mesh-vpn.md) |
| `aisec-mss-clamp` | Rewrites the TCP segment size on routed connections | [Mesh VPN](mesh-vpn.md) |
| `squid` | Package proxy for the worker | [Package proxy](package-proxy.md) |
| `ssh` | Administration, key only | [Validation: host hardening](../validation/host-hardening.md) |

## First boot

cloud-init writes every configuration file, then one script does the rest in order: kernel settings, the segment size clamp, file modes, the mesh VPN agent from its signed repository, the proxy, K3s from a binary and an install script that are both checked against pinned checksums, two cluster settings the Kubernetes benchmark asks for, and a key pair for feeding the other machines.

The two cluster settings wait for the API: no token on the default service account of each namespace K3s creates, and mode `600` on the certificate files. If the API never answers, the script stops and leaves no `/var/lib/aisec-first-boot.done`. This part is configured, not tested: it went into the template on 2026-10-12, after the running VM was built, and was applied there by hand.

Custom data is ignored after creation. A change to the template does not reach a running VM. It takes a rebuild, or the same change by hand.

## Measured

About 20 minutes after boot, with an empty cluster: 1.0 of 7.9 GiB memory used, CPU 98 to 99 % idle, 2.9 GB of disk. cloud-init finished 54 seconds after boot.

## Validation

`A`, `K`, `R`, `E`, `P`, `U`, and `HO` in the [validation pages](../validation/README.md).

## Limits

- **It is the supply chain.** What it pushes is what runs on the fed machines.
- **A compromise of it is not contained.** It holds every credential that matters and reaches any host on port 443.
- **No encryption at host.** The subscription feature is not registered.
- **Not rebuilt from the current template.** The running VM got several changes by hand.

## Official documentation

- [Trusted Launch for Azure VMs](https://learn.microsoft.com/azure/virtual-machines/trusted-launch)
- [Boot diagnostics](https://learn.microsoft.com/azure/virtual-machines/boot-diagnostics)
- [cloud-init](https://cloudinit.readthedocs.io/en/latest/)
- [Ubuntu automatic updates](https://documentation.ubuntu.com/server/how-to/software/automatic-updates/)
