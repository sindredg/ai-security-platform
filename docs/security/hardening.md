# Hardening

What has been tightened on the machines and the cluster, what was left alone on purpose, and what is still open. The history is in the [milestone 2 worklog](../worklogs/0002-platform-compute.md). This page is the current state, and it changes with every milestone that adds something to harden.

## Baseline

| Layer | What is applied | Held in place by |
| --- | --- | --- |
| Azure | No public address on any VM, refused by policy. Trusted Launch with Secure Boot and a virtual TPM. Password login off | [`Z` checks](../validation/azure-policy.md) |
| Network | Deny by default in both directions on every subnet. Explicit denies for the internet, the target network, and Azure DNS on the worker | [`C` and `Z` checks](../validation/containment.md) |
| SSH daemon | Keys only, no root login, no forwarding, three tries | [`HO` and `HW` checks](../validation/host-hardening.md) |
| Kernel | SysRq off, pointers hidden, no redirects or source routing, hardened BPF JIT, five unused modules kept from loading | The same |
| Files and packages | Cron and SSH configuration closed to group and world. No compiler, assembler, or linker. Unattended security upgrades | The same, and the [`U` checks](../validation/package-proxy.md) |
| K3s | Secrets encryption, kernel default protection, audit log at metadata level, no anonymous access to the API server or the kubelet, certificate files at `600`, no token on default service accounts. Pod security `restricted` for every namespace without a label, `baseline` in `kube-system`, no exemption. Verified on 2026-10-16 ([worklog](../worklogs/0004-edge-network-and-monitoring.md#slice-a-orchestrator-hardening)) | [`K` checks](../validation/cluster.md) |
| Workloads | The tool service pod runs as user 65532 with no service account token, no privilege escalation, no capabilities, and a read-only root file system. Both workload namespaces enforce the restricted pod security level and deny by default. Node ports answer on the private address only. A host rule drops forwarded traffic from pods to anything but pods, and traffic from pods to the host except the API server and the kubelet. Verified on 2026-10-16 | [`T` checks](../validation/tool-service.md), `E.6` to `E.8` on [containment](../validation/containment.md) |
| Audit copier | Its own user, no network, no capabilities, a read-only view of the system except its state folder and `/var/log/aisec`, and 256 MiB of memory. It appends to a file with the append-only attribute. Verified on 2026-10-16 ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)) | [`L` checks](../validation/audit-log.md) |
| Journal pull | Its own user, a 256 MiB limit, a read-only view of the system except `/var/log/aisec`, and IP traffic only to the worker's address (`IPAddressAllow=10.40.0.36`). Verified on 2026-10-16 ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)) | [`J` checks](../validation/audit-log.md#the-workers-journal) |
| Package proxy | Two hosts, two methods, one port, one client subnet, in a systemd sandbox | [`P` checks](../validation/package-proxy.md) |

## Benchmarks

| Tool | Scope | Result | Date |
| --- | --- | --- | --- |
| kube-bench 0.16.0, `k3s-cis-1.9` | The cluster | 65 pass, 1 fail, 50 warn. The fail asks for an etcd flag and there is no etcd | 2026-10-11 |
| Lynis 3.1.7 | Orchestrator | Hardening index 76, up from 60. One warning, a false positive | 2026-10-11 |
| Lynis 3.1.7 | Worker | Hardening index 77, up from 66. No warnings | 2026-10-11 |
| CIS benchmark for Ubuntu 26.04 | Both VMs | Not run. No tool has a profile for this release | |

Lynis was not run again after the last three fixes, so its numbers are slightly behind the machines.

The orchestrator was rebuilt on 2026-10-13. kube-bench and Lynis have not been run on the new machine, so the cluster row and the orchestrator row describe the one it replaced. The `K` and `HO` checks, which hold the fixes in place, passed on the new machine.

## Left alone on purpose

| Setting | Reason |
| --- | --- |
| IP forwarding on the orchestrator | It is the subnet router |
| Loose reverse path filtering | Strict mode breaks the tunnel and the pod network |
| Module loading after boot | K3s and the mesh VPN agent load modules |
| `k3s`, `tailscaled`, and `ssh` without a systemd sandbox | Each needs root and broad access to do its job |
| Password policy, boot loader password, legal banners | No account has a password, the only console is behind cloud access control, and there is one operator |
| No malware scanner or package audit tool on the VMs | Machines kept small. Scanning belongs in the pipeline |

## Open

| Gap | Why it matters | Lands with |
| --- | --- | --- |
| No `auditd`, no process accounting | Nothing records what ran on a machine | Milestone 6, with the drills ([ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)) |
| Logs stay on the machine they describe | A compromised machine can alter its own logs | Milestone 3 for the worker: the orchestrator pulls its journal every five minutes ([audit log](audit-log.md#the-workers-journal)), verified on 2026-10-16. The orchestrator's own logs stay where they are. [Milestone 3a](../roadmap.md#3a-edge-network-and-monitoring): a copy of both in Azure Monitor, decided in [ADR 0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md) |
| No file integrity monitoring | A changed binary or configuration file goes unnoticed | Milestone 6 |
| No CIS result for the operating system | The audit that ran is not the benchmark the plan named | When a tool supports Ubuntu 26.04 |
| The 50 kube-bench warnings are not reviewed one by one | Some are manual checks that could be real findings | Milestone 3, when the cluster has workloads |
| Held and pinned software gets no security fix until someone moves the pin | The mesh VPN agent and K3s run all the time. `U.7` fails when the agent is behind the stable release. Nothing does the same for K3s | Each milestone start, from the [version table](../components/README.md#versions) |
| One long-lived operator SSH key on every VM | A copy works until it is swapped everywhere, and every login looks the same in the logs | [Milestone 3a](../roadmap.md#3a-edge-network-and-monitoring): certificates that expire after 12 hours ([ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md)) |
| Nothing alerts when updates stop, a service dies, or a disk fills | Silent failure. A failure shows only when someone runs the [checks](../validation/README.md) | [Milestone 3a](../roadmap.md#3a-edge-network-and-monitoring): alert rules in Azure Monitor, shown in the portal. They send no notification |
