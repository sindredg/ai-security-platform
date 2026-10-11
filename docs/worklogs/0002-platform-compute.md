# 0002. Platform compute

Date: 2026-10-11
Milestone: 2, platform compute

## Summary

The public address policy, the NAT gateway, both VMs, the mesh VPN, and K3s exist and work. The milestone is not finished: the gate table shows what is open. The procedure is in the [platform compute runbook](../runbooks/platform-compute.md).

| Gate | Result |
| --- | --- |
| Both VMs are reachable over the mesh VPN and have no public address | Met |
| Effective rules match the configured rules, and the denied paths are tested with traffic | Met |
| K3s comes back healthy after a VM restart | Met. Node `Ready` within about 20 seconds of boot |
| The worker cannot reach the target network or the internet, and cannot resolve a public name | Met |
| A public address on a network interface is refused by policy in both workload resource groups | Met |
| Idle CPU and memory use is measured | Met |
| Every credential is in the inventory, and each long-lived one has a rotation that has been run once | Met. The SSH keys, the cluster token, and the mesh VPN node key were each rotated once |
| Hardening benchmark results are recorded, and each failed check is fixed or accepted | Partly met. Kubernetes benchmark run: 3 fails, 2 fixed, 1 accepted. The operating system got a Lynis audit, not a CIS run. Its findings are fixed, accepted with a reason, or listed as open |
| `main` takes changes only through a pull request with passing checks, and a pushed secret is refused | Met in an earlier change. Not re-tested here |
| Pull requests run static checks and a secret scan, with no cloud credentials | Met in an earlier change |
| Version pins get automated update pull requests | Configured, not yet seen. `.github/dependabot.yml` covers the providers and the pipeline actions weekly. `gh pr list --state all --author app/dependabot` returns nothing, and every pin is current |

Two things failed on the way and are written up: [an image pin that only existed in the daily offer](../troubleshooting/01-image-version-only-in-daily-offer.md), and [SSH through the subnet router stalling](../troubleshooting/02-ssh-through-subnet-router-stalls.md).

## Versions

Read from the official sources on 2026-10-11 and pinned exactly.

| Component | Version | Source |
| --- | --- | --- |
| Terraform and providers | Unchanged from [worklog 0001](0001-network-foundation.md) | Same sources, read again |
| Ubuntu image | `Canonical:ubuntu-26_04-lts`, `server` and `server-arm64`, `26.04.202610070` | `az vm image list`, filtered on the exact offer and SKU |
| Mesh VPN agent | 1.104.1 | The vendor's stable package repository |
| K3s | `v1.36.5+k3s1` | The `stable` channel in the K3s repository's `channel.yaml`. The newest release is `v1.37.1+k3s1`, which the stable channel does not point at yet |
| kube-bench | 0.16.0, released 2026-08-05 | GitHub releases. Archive checked against the release checksum file |

The K3s binary and its install script are both pinned by SHA-256 in `infra/platform/variables.tf` and checked on the VM before either runs.

## Sizes and quota

```bash
az vm list-skus -l swedencentral --resource-type virtualMachines \
  --query "[?name=='Standard_B2as_v2' || name=='Standard_D2ps_v6'].{name:name, zones:join(',',locationInfo[0].zones), restrictions:length(restrictions)}" -o table
az vm list-usage -l swedencentral \
  --query "[?contains(name.value,'cores') || contains(name.value,'Basv2') || contains(name.value,'Dpsv6')].{name:name.value, used:currentValue, limit:limit}" -o table
```

| Size | Used for | Zones | Restrictions |
| --- | --- | --- | --- |
| `Standard_B2as_v2` | Orchestrator, x64 | 1, 2, 3 | 0 |
| `Standard_D2ps_v6` | AI worker, Arm64 | 1, 2, 3 | 0 |

| Quota, after the build | Used | Limit |
| --- | --- | --- |
| `cores` | 4 | 4 |
| `standardBasv2Family` | 2 | 4 |
| `StandardDpsv6Family` | 2 | 4 |

The regional core quota is full. A third VM in this region needs a quota increase or a different region.

## Applies

Every apply used a saved plan that was read first.

| Root | Identity | Plan | Result |
| --- | --- | --- | --- |
| `infra/bootstrap` | Operator | 3 to add | 3 added: the policy assignments |
| `infra/platform`, first apply | Platform | 8 to add, 2 to change | NAT gateway, public address, two associations, and two network interfaces added. Two security groups changed. Both VMs failed with `PlatformImageNotFound` |
| `infra/platform`, after the image pin fix | Platform | 2 to add | 2 added: the VMs |
| `infra/targets` | Targets | 0 to add, 4 to change | 4 changed: two deny rules on each target security group |

```bash
terraform plan -detailed-exitcode
```

Exit `0` for all three roots after the last apply.

The first attempt at the bootstrap apply stopped at `Unsupported Terraform Core version`. The `terraform` on `PATH` was a distribution package at 1.15.8. The runbook now starts by putting the pinned binary first.

## The VMs

```bash
az vm list -g rg-aisec-platform -d --query "[].{name:name, power:powerState, private:privateIps, public:publicIps, size:hardwareProfile.vmSize}" -o table
az vm show -g rg-aisec-platform -n vm-aisec-orchestrator \
  --query "{type:securityProfile.securityType, secureBoot:securityProfile.uefiSettings.secureBootEnabled, vtpm:securityProfile.uefiSettings.vTpmEnabled, hostEncryption:securityProfile.encryptionAtHost, passwordOff:osProfile.linuxConfiguration.disablePasswordAuthentication}"
az feature show --namespace Microsoft.Compute --name EncryptionAtHost --query properties.state -o tsv
```

| VM | State | Private address | Public address | Size |
| --- | --- | --- | --- | --- |
| `vm-aisec-orchestrator` | Running | `10.40.0.4` | None | `Standard_B2as_v2` |
| `vm-aisec-worker` | Running | `10.40.0.36` | None | `Standard_D2ps_v6` |

The orchestrator is a Trusted Launch VM with Secure Boot and a vTPM, and password authentication is off. Encryption at host is not set: the feature reads `NotRegistered` on the subscription.

First boot, from the serial logs through boot diagnostics:

| VM | cloud-init finished | Notes |
| --- | --- | --- |
| Orchestrator | 54 seconds after boot | Mesh VPN agent 1.104.1 installed, joined, K3s binary checksum `OK`, `k3s.service` started |
| Worker | 72 seconds after boot | Installs nothing. It has no path to fetch anything |

Read on the orchestrator:

```bash
ls /var/lib/aisec-first-boot.done; cloud-init status; ls /run/aisec
sudo tailscale status
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl get pods -A
sudo k3s secrets-encrypt status
```

| Check | Result |
| --- | --- |
| First boot marker | Present. `status: done` |
| Auth key file in `/run/aisec` | Gone |
| Mesh VPN | Joined as `aisec-orchestrator`, advertising `10.40.0.0/20` and `10.50.0.0/20` |
| Workstation connection | Relayed, not direct. [ADR 0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md) expected this behind the NAT gateway |
| Node | `Ready`, `v1.36.5+k3s1`, Ubuntu 26.04.1 LTS, containerd 2.3.4 |
| Pods | `coredns`, `local-path-provisioner`, `metrics-server` running |
| Secrets encryption | `Enabled`, all hashes match |
| API server | `--anonymous-auth=false`, `--authorization-mode=Node,RBAC`, `--etcd-servers=unix://kine.sock` |

The host keys were taken from the serial log and compared with a key scan before the first login. Both matched.

The orchestrator's feed key was generated on the VM at first boot. Its public half was added to the worker by hand, and `ssh -i ~/.ssh/aisec-feed aisec@aisec-worker hostname` from the orchestrator returned `aisec-worker`.

## Paths tested with traffic

Each test opens a TCP connection with a 5 second limit.

```bash
t() { timeout 5 bash -c "</dev/tcp/$1/$2" 2>/dev/null && echo "$1:$2 OPEN" || echo "$1:$2 no connection"; }
```

| From | To | Result |
| --- | --- | --- |
| Worker | `1.1.1.1:443` | No connection |
| Worker | A GitHub address on 443 | No connection |
| Worker | `10.50.0.4:22`, `10.50.1.4:22` in the target network | No connection |
| Worker | `168.63.129.16:53`, the platform resolver | No connection |
| Worker | `getent hosts example.com` | Timed out |
| Worker | Orchestrator on 22 and 6443 | No connection |
| Orchestrator | `1.1.1.1` on 443 and 80 | Open |
| Orchestrator | Worker on 22 | Open |
| Orchestrator | Worker on 80 | No connection |
| Orchestrator | `getent hosts example.com` | Resolved |

The target network has no machines yet, so a timeout to a target address proves little by itself. IP flow verify names the rule:

```bash
az network watcher test-ip-flow -g rg-aisec-platform --vm vm-aisec-worker --direction Outbound \
  --protocol TCP --local 10.40.0.36:50000 --remote <address:port> --query "[access,ruleName]" -o tsv
```

| Remote | Access | Rule |
| --- | --- | --- |
| `10.50.0.4:22` | Deny | `deny-to-targets` |
| `1.1.1.1:443` | Deny | `deny-to-internet` |
| `168.63.129.16:53` | Not testable | The tool refuses the address as restricted address space. The traffic test above covers it |

The address the orchestrator leaves from, read with a request to a public echo service, equals the NAT gateway's address from `az network public-ip show`.

## Effective rules

```bash
az network nic list-effective-nsg -g rg-aisec-platform -n nic-aisec-<vm>
az network nsg show -g rg-aisec-platform -n nsg-aisec-platform-<subnet>
```

Compared by direction, priority, access, and name, leaving out the built-in defaults.

| Network interface | Configured | Effective | Difference |
| --- | --- | --- | --- |
| `nic-aisec-orchestrator` | 9 | 10 | `DefaultIPv6OutboundDeny`, outbound, priority 0 |
| `nic-aisec-worker` | 7 | 8 | The same rule |

The extra rule is not from this configuration. It arrives as a second effective rule set associated through a network manager, and it denies. Nothing configured is missing or overridden.

Configured rules on the two security groups after this milestone:

| Security group | Priority | Direction | Access | Rule |
| --- | --- | --- | --- | --- |
| Orchestrator | 100 | Inbound | Deny | `deny-from-targets` |
| Orchestrator | 1000 | Outbound | Allow | `allow-ssh-to-worker` |
| Orchestrator | 1010 | Outbound | Allow | `allow-ssh-to-targets` |
| Orchestrator | 1100 | Outbound | Allow | `allow-https-to-internet` |
| Orchestrator | 1110 | Outbound | Allow | `allow-http-to-internet` |
| Orchestrator | 1120 | Outbound | Allow | `allow-mesh-stun` |
| Orchestrator | 1130 | Outbound | Allow | `allow-mesh-direct` |
| Worker | 100 | Inbound | Deny | `deny-from-targets` |
| Worker | 1000 | Inbound | Allow | `allow-ssh-from-orchestrator` |
| Worker | 100 | Outbound | Deny | `deny-to-targets` |
| Worker | 110 | Outbound | Deny | `deny-to-internet` |
| Worker | 120 | Outbound | Deny | `deny-to-azure-dns` |
| Both | 4096 | Both | Deny | `deny-all-inbound`, `deny-all-outbound` |

The orchestrator has no inbound allow. Administration arrives inside the mesh VPN tunnel, which the orchestrator opens outbound.

## Public address policy

Tested without creating anything: a template is validated, and the policy answers at validation.

```bash
az deployment group validate -g <resource-group> --template-file <template>.json
```

| Template | Resource group | Result | Assignment named |
| --- | --- | --- | --- |
| Network interface with a public address | `rg-aisec-platform` | `RequestDisallowedByPolicy` | `deny-public-ip-on-interface` |
| Network interface with a public address | `rg-aisec-targets` | `RequestDisallowedByPolicy` | `deny-public-ip-on-interface` |
| Public IP address | `rg-aisec-targets` | `RequestDisallowedByPolicy` | `deny-public-ip-resources` |

Afterwards `az resource list` found no test resource in either group.

## Restart

```bash
az vm restart -g rg-aisec-platform -n vm-aisec-orchestrator
```

| Time, UTC | Event |
| --- | --- |
| 15:58:48 | Restart requested |
| 15:59:14 | Boot time reported by the VM |
| 15:59:33 | Restart command returned |
| 15:59:36 | Node `Ready` on the first check over the mesh VPN |

`k3s`, `tailscaled`, and `aisec-mss-clamp` were `active`. The three pods showed `Unknown` on the first read and were `Running` with one restart each about a minute later. The worker was reachable through the orchestrator again. Secrets encryption was still `Enabled`.

## Idle use

Read about 20 minutes after boot, with `free -m` and three 10 second `vmstat` samples.

| VM | Memory used | Memory total | CPU idle | Disk used |
| --- | --- | --- | --- | --- |
| Orchestrator | 1005 MiB | 7881 MiB | 98 to 99 % | 2.9 GB of 61 GB |
| Worker | 524 MiB | 7905 MiB | 99 to 100 % | 2.0 GB of 61 GB |

## Kubernetes benchmark

kube-bench 0.16.0 with its newest K3s profile, `k3s-cis-1.9`. Run twice: on the cluster as built, and after the two fixes.

First run:

| Section | Pass | Fail | Warn | Info |
| --- | --- | --- | --- | --- |
| 1. Control plane security configuration | 42 | 2 | 6 | 9 |
| 2. Etcd node configuration | 0 | 0 | 7 | 0 |
| 3. Control plane configuration | 1 | 0 | 4 | 0 |
| 4. Worker node security configuration | 17 | 0 | 2 | 5 |
| 5. Kubernetes policies | 3 | 1 | 31 | 0 |
| Total | 63 | 3 | 50 | 14 |

| Failed check | Finding | Answer |
| --- | --- | --- |
| 1.2.26, `--etcd-cafile` is set | The API server has no such argument | Accepted. There is no etcd. The datastore is SQLite behind `kine`, and the API server reaches it over a local socket: `--etcd-servers=unix://kine.sock` |
| 5.1.5, default service accounts are not used | `automountServiceAccountToken` is unset in all four namespaces | Fixed. Set to `false` on the default service account of every namespace, runbook step 17 |
| 1.1.20, certificate files are `600` or stricter | All 13 `.crt` files under `server/tls` are `644` | Fixed. Set to `600`, runbook step 18. K3s kept the mode across a service restart |

After the fixes and a restart of `k3s.service`, read back on the orchestrator: 13 certificate files at `600`, the node `Ready`, three pods `Running`, and `false` for the default service account in `default`, `kube-node-lease`, `kube-public`, and `kube-system`.

Second run:

| Section | Pass | Fail | Warn | Info |
| --- | --- | --- | --- | --- |
| 1. Control plane security configuration | 43 | 1 | 6 | 9 |
| 2. Etcd node configuration | 0 | 0 | 7 | 0 |
| 3. Control plane configuration | 1 | 0 | 4 | 0 |
| 4. Worker node security configuration | 17 | 0 | 2 | 5 |
| 5. Kubernetes policies | 4 | 0 | 31 | 0 |
| Total | 65 | 1 | 50 | 14 |

The one fail left is 1.2.26, accepted above.

The 50 warnings are checks the tool cannot decide by itself. They have not been reviewed one by one. The service account fix is a patch, not configuration: a namespace created later starts without it.

## Operating system audit

The plan was a CIS benchmark run. No open tool can do one for this release yet.

| Tool | Checked on 2026-10-11 | Result |
| --- | --- | --- |
| CIS Ubuntu Linux 26.04 LTS Benchmark | The CIS monthly update for October 2026 | Exists, v1.0.0, published the month before |
| OpenSCAP with ComplianceAsCode content 0.1.82 | The `ubuntu2604` product in the release | Ships a `default` profile only. No CIS profile |
| Ubuntu Security Guide | `apt-cache policy usg` on the orchestrator, and the vendor documentation | Not installable without an Ubuntu Pro subscription attached. The documentation does not say whether it covers 26.04 |
| Lynis 3.1.7 | The publisher's download page | Runs anywhere as a shell script. Not a CIS benchmark |

Lynis was run on both VMs. It is a general hardening audit with its own score, so the numbers below are not CIS results. The archive's SHA-256 matched the value on the publisher's download page. The worker got the archive from the orchestrator over the feed path. The tool was removed from both VMs afterwards.

```bash
sudo ./lynis audit system --quiet --no-colors --logfile <dir>/lynis.log --report-file <dir>/lynis-report.dat
```

| VM | Tests | Hardening index | Warnings | Suggestions |
| --- | --- | --- | --- | --- |
| Orchestrator | 252 | 60 | 2 | 42 |
| Worker | 248 | 66 | 0 | 40 |

| Warning on the orchestrator | Answer |
| --- | --- |
| `PKGS-7388`, no security repository found | Accepted as a false positive. `/etc/apt/sources.list.d/ubuntu.sources` lists the `resolute-security` suite. The tool does not find it in that file format |
| `PKGS-7392`, vulnerable packages found | Fixed. Three packages had security updates pending: `libpng16-16t64`, `libxml2-16`, `sudo`. `sudo unattended-upgrade` installed them. `unattended-upgrades` is enabled, so they would have gone in within a day. No restart was required, and K3s and the mesh VPN agent stayed `active` |

### Triage

The suggestions were sorted into fixed, accepted, and open. The fixes are in both cloud-init templates and were applied by hand on the running VMs, then the audit was run again.

| VM | Hardening index before | After | Warnings after | Suggestions before | After |
| --- | --- | --- | --- | --- | --- |
| Orchestrator | 60 | 76 | 1, the false positive above | 42 | 27 |
| Worker | 66 | 77 | 0 | 40 | 30 |

Fixed:

| Finding | Fix |
| --- | --- |
| `SSH-7408`, SSH daemon options | `/etc/ssh/sshd_config.d/10-aisec.conf`: no root login, no agent or X11 forwarding, 3 authentication tries, 2 sessions, client alive checks, verbose logging. TCP forwarding is off on the orchestrator and `remote` on the worker |
| `KRNL-6000`, kernel settings | `/etc/sysctl.d/90-aisec-hardening.conf`: SysRq off, kernel pointers hidden, no core dumps from setuid programs, protected FIFOs and regular files, hardened BPF JIT, no source routing, no ICMP redirects in or out, martian packets logged |
| `NETW-3200`, `USB-1000`, unused protocols and USB storage | `/etc/modprobe.d/aisec-unused.conf` stops `dccp`, `sctp`, `rds`, `tipc`, and `usb-storage` from loading |
| `PKGS-7392`, pending updates | Installed on the orchestrator, above |

Checked after the change: `sshd -t` passed on both VMs, new logins worked, the feed path and the routed path to the worker worked, K3s reported the node `Ready` with three pods running.

Accepted:

| Finding | Reason |
| --- | --- |
| `KRNL-6000`, what is left: IP forwarding on, loose reverse path filter, module loading allowed | The orchestrator is the subnet router. Strict reverse path filtering breaks the tunnel and the pod network. K3s and the mesh VPN agent load modules after boot |
| `SSH-7408`, port 22 | Moving the port hides nothing from anyone who can reach these machines |
| `SSH-7408` on the worker, remote forwarding allowed | Package updates arrive through a forward the orchestrator opens, by [ADR 0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md) |
| `AUTH-9230`, `AUTH-9262`, `AUTH-9286`, `AUTH-9328`, password policy | No account has a password. Login is by key only |
| `AUTH-9284`, locked account | The administrator account has no password on purpose |
| `BOOT-5122`, boot loader password | The only console is the cloud serial console, behind the subscription's access control |
| `FILE-6310`, separate `/home` and `/var` | The disk layout comes from the image |
| `NAME-4404`, `NAME-4028`, name resolution | The fed machines have no DNS by design. They use a hosts file |
| `FIRE-4513`, unused firewall rules | K3s and the mesh VPN agent own those rules |
| `PKGS-7370`, `PKGS-7394`, `PKGS-7398`, `HRDN-7230`, package audit tools and a malware scanner | More installed software on machines kept small on purpose. Image and dependency scanning belongs to the pipeline |
| `BANN-7126`, `BANN-7130`, legal banners | One operator |
| `TOOL-5002`, no automation tool found | Terraform and cloud-init do that job, and the audit does not recognize them |
| `PKGS-7388`, no security repository | False positive, above |

Open:

| Finding | Why it is open |
| --- | --- |
| `ACCT-9628`, `ACCT-9622`, `LOGG-2154`, `FINT-4350`: no `auditd`, no process accounting, no remote logging, no file integrity tool | Real gaps. They belong with the audit log decision in milestone 3, where logs get a place out of the worker's reach |
| `BOOT-5264`, `BOOT-5180`, service hardening | Not reviewed |
| `FILE-7524`, file permissions | Not reviewed |
| `HRDN-7222`, compilers present | Not reviewed |

### Updates on the worker

The worker's clean result on packages in the first run means nothing. The audit runs `apt-get update` first, and on the worker that hung for about six minutes and then failed, as designed: the worker has no path to a package repository. Its package lists are the ones from the image, so it does not know what is outdated. The second run skipped that test.

[ADR 0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md) already says how the worker gets packages: through a SOCKS forward carried by an SSH session that the orchestrator opens. That procedure has not been run. Until it has, the worker runs the packages its image shipped with.

## Rotations

Each long-lived credential on the VMs was rotated once, with the procedures in the [runbook](../runbooks/platform-compute.md#rotate-a-credential). Each run ended with a test that the old credential is refused.

| Credential | What changed | Old credential afterwards | New credential afterwards |
| --- | --- | --- | --- |
| Feed SSH key | New key pair on the orchestrator. New public half on the worker, old one removed | `ssh` with the old key: refused | `ssh -i ~/.ssh/aisec-feed aisec@aisec-worker` returns `aisec-worker` |
| Cluster token | `k3s token rotate` with a new random token, then one restart of `k3s.service` | HTTP `401` from the server's bootstrap endpoint | Not `401`. Node `Ready`, three pods `Running`, secrets encryption `Enabled` |
| Operator SSH key | New key pair on the workstation, used for this project only. Swapped on both VMs | `Permission denied (publickey)` on both VMs | Login to both VMs |

Two things the rotations showed:

- **The token rotation needs no configuration change.** `k3s token rotate` rewrote `/var/lib/rancher/k3s/server/token`, and the restart picked it up. The datastore, the old token file, and the credentials directory were copied to a root-only directory first and deleted after the checks.
- **Terraform cannot push a new operator key.** A changed `admin_ssh_key` plans a replacement of both VMs: `2 to add, 0 to change, 2 to destroy`. The VM resource now ignores changes to that key, the same way it ignores custom data. After that change, and with the new public key in the local variables file, `terraform plan -detailed-exitcode` exits `0`.

After the rotations, the certificate files were still `600` and the feed path still worked.

The mesh VPN node key was rotated too, by enrolling the orchestrator again with a new single-use auth key and `tailscale up --force-reauth`. The node key changed. The node kept its address, its tag, and its approved routes, and the worker stayed reachable through it.

## Limitations

- **The milestone is not closed.** See the gate table for what is open.
- **The benchmark profile is older than the cluster.** `k3s-cis-1.9` was written for K3s 1.27 to 1.29. The cluster runs 1.36. A newer profile does not ship with the tool.
- **The running orchestrator differs from its template in how it got one fix.** The segment size clamp was installed by hand with the same content as the cloud-init template. A VM built from the template has not been booted with it.
- **The worker cannot open any connection to the orchestrator.** That is containment today. It decides how dispatch and results travel in milestone 3: the orchestrator has to initiate.
- **The worker has had no security updates since its image.** The update path from ADR 0009 is decided and has not been run.
- **No CIS result for the operating system.** No open tool ships a CIS profile for Ubuntu 26.04 yet. The audit that ran is not a CIS benchmark.
- **No audit daemon, remote logging, or file integrity monitoring on either VM.** Open until the audit log decision in milestone 3.
- **The hardening on the running VMs was applied by hand.** Same content as the templates, but no VM has been built from them.
- **Mesh VPN connections are relayed.** Fine for administration, slow for bulk transfer.
- **Node signing is off.** The mesh VPN's coordination service could add a node to the network without the operator. Turning signing on needs a second signing device.
- **No encryption at host.** The feature is not registered on the subscription.
- **The regional core quota is full.**
- **Built once.** The runbook was written from this build. A rebuild from scratch and a removal have not been run.
