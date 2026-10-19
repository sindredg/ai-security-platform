# Hardening

What has been tightened on the machines and the cluster, what was left alone on purpose, and what is still open. The history is in the [milestone 2 worklog](../worklogs/0002-platform-compute.md). This page is the current state, and it changes with every milestone that adds something to harden.

## Baseline

| Layer | What is applied | Held in place by |
| --- | --- | --- |
| Azure | No public address on any VM, refused by policy. Trusted Launch with Secure Boot and a virtual TPM. Password login off | [`Z` checks](../validation/azure-policy.md) |
| Network | Deny by default in both directions on every subnet. Explicit denies for the internet and Azure DNS on the orchestrator and the worker, and for the target network on the worker. Only the router and the edge have an outbound method | [`C` and `Z` checks](../validation/containment.md) |
| SSH daemon | Keys only, and only a certificate for the administrator account. No root login, three tries. No forwarding, except the administrator's tunnel to the API server on the orchestrator | [`HO`, `HW`, `HR`, and `HE` checks](../validation/host-hardening.md), [`A.8` to `A.10`, `A.14`, `A.17`](../validation/access.md) |
| Kernel | SysRq off, pointers hidden, no redirects or source routing, hardened BPF JIT, five unused modules kept from loading | The same |
| Files and packages | Cron and SSH configuration closed to group and world. No compiler, assembler, or linker. Unattended security upgrades | The same, and the [`U` checks](../validation/package-proxy.md) |
| K3s | Secrets encryption, kernel default protection, audit log at metadata level, no anonymous access to the API server or the kubelet, certificate files at `600`, no token on default service accounts. Pod security `restricted` for every namespace without a label, `baseline` in `kube-system`, no exemption. Verified on 2026-10-16 ([worklog](../worklogs/0004-edge-network-and-monitoring.md#slice-a-orchestrator-hardening)) | [`K` checks](../validation/cluster.md) |
| Workloads | The tool service pod runs as user 65532 with no service account token, no privilege escalation, no capabilities, and a read-only root file system. Both workload namespaces enforce the restricted pod security level and deny by default. Node ports answer on the private address only. A host rule drops forwarded traffic from pods to anything but pods, and traffic from pods to the host except the API server and the kubelet. Verified on 2026-10-16 | [`T` checks](../validation/tool-service.md), `E.6` to `E.8` on [containment](../validation/containment.md) |
| Audit copier | Its own user, no network, no capabilities, a read-only view of the system except its state folder and `/var/log/aisec`, and 256 MiB of memory. It appends to a file with the append-only attribute. Verified on 2026-10-16 ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)) | [`L` checks](../validation/audit-log.md) |
| Journal pull | Its own user, a 256 MiB limit, a read-only view of the system except `/var/log/aisec`, and IP traffic only to the worker's address (`IPAddressAllow=10.40.0.36`). Verified on 2026-10-16 ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)) | [`J` checks](../validation/audit-log.md#the-workers-journal) |
| Package proxy | Squid on the edge VM, in a systemd sandbox (`4.3 OK`). Two hosts for the worker and one for the orchestrator, `GET` and `HEAD` on port 80. Tunnels only for the orchestrator, only during a fetch window. Verified on 2026-10-17 ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-edge-vm)). Since 2026-10-18 the sandbox drop-in is compared with the template, `P.21` ([worklog](../worklogs/0004-edge-network-and-monitoring.md#before-the-ai-part)) | [`P` checks](../validation/package-proxy.md) |

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
| IP forwarding on the router | It is the subnet router. K3s turns it on for the orchestrator's pod network |
| Loose reverse path filtering | Strict mode breaks the tunnel and the pod network |
| Module loading after boot | K3s and the mesh VPN agent load modules |
| `k3s`, `tailscaled`, and `ssh` without a systemd sandbox | Each needs root and broad access to do its job |
| Password policy, boot loader password, legal banners | No account has a password, the only console is behind cloud access control, and there is one operator |
| No malware scanner or package audit tool on the VMs | Machines kept small. Scanning belongs in the pipeline |

## Open

| Gap | Why it matters | Lands with |
| --- | --- | --- |
| No `auditd`, no process accounting | Nothing records what ran on a machine | Milestone 6, with the drills ([ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)) |
| Logs stay on the machine they describe | A compromised machine can alter its own logs | Milestone 3 for the worker: the orchestrator pulls its journal every five minutes ([audit log](audit-log.md#the-workers-journal)), verified on 2026-10-16. Milestone 3a: a copy of the audit lines, the worker's journal, and the orchestrator's, the edge's, and the router's logins and warnings in Azure Monitor, since 2026-10-17 ([monitoring](../components/monitoring.md)). What a VM logged before its agent read it can still be altered on the VM. Once the daily cap is reached, the billable tables get nothing until the reset hour, or until a while after the cap is raised ([T41](threat-model.md)) |
| No file integrity monitoring | A changed binary or configuration file goes unnoticed | Milestone 6 |
| No CIS result for the operating system | The audit that ran is not the benchmark the plan named | When a tool supports Ubuntu 26.04 |
| The 50 kube-bench warnings are not reviewed one by one | Some are manual checks that could be real findings | Milestone 3, when the cluster has workloads |
| Held and pinned software gets no security fix until someone moves the pin | The mesh VPN agent and K3s run all the time. `U.7` fails when the agent is behind the stable release. Nothing does the same for K3s | Each milestone start, from the [version table](../components/README.md#versions) |
| Nothing alerts when updates stop | Silent failure until someone runs the [checks](../validation/README.md) (`U` checks). A failed unit and a full disk raise an alert in the portal since 2026-10-18 ([monitoring](../components/monitoring.md#alert-rules)) | Not planned. A rule on the package lists' age would need the lists in the workspace |

One row left this table on 2026-10-16: one long-lived operator SSH key on every VM. The administrator account now takes only a certificate that expires after 12 hours ([worklog](../worklogs/0004-edge-network-and-monitoring.md#rollout-1)).
