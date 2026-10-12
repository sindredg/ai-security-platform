# 0002. Platform compute

Date: 2026-10-11
Milestone: 2, platform compute

## Summary

The public address policy, the NAT gateway, both VMs, the mesh VPN, K3s, and the worker's package proxy exist and work. The gate is met, with three stated gaps: the operating system has no CIS result, the refusal of a pushed secret is configured and not tested, and no dependency update pull request has been seen yet. The procedure is in the [platform compute runbook](../runbooks/platform-compute.md).

| Gate | Result |
| --- | --- |
| Both VMs are reachable over the mesh VPN and have no public address | Met |
| Effective rules match the configured rules, and the denied paths are tested with traffic | Met |
| K3s comes back healthy after a VM restart | Met. Node `Ready` within about 20 seconds of boot |
| The worker cannot reach the target network or the internet, and cannot resolve a public name | Met |
| A public address on a network interface is refused by policy in both workload resource groups | Met |
| Idle CPU and memory use is measured | Met |
| Every credential is in the inventory, and each long-lived one has a rotation that has been run once | Met. The SSH keys, the cluster token, and the mesh VPN node key were each rotated once |
| Hardening benchmark results are recorded, and each failed check is fixed or accepted | Met, with one stated gap. Kubernetes benchmark run: 3 fails, 2 fixed, 1 accepted. The operating system got a Lynis audit, not a CIS run, because no tool has a CIS profile for this release. Its findings are fixed, accepted with a reason, or carried to milestone 3 |
| `main` takes changes only through a pull request with passing checks, and a pushed secret is refused | The pull request rule is met. The refusal is configured, not tested. Read on 2026-10-11 with `gh api`: ruleset `protect-main` is active with a pull request rule and four required checks, and secret scanning with push protection is enabled. No secret was pushed to prove the refusal, and none will be: a real secret must not go to a public repository to test it |
| Pull requests run static checks and a secret scan, with no cloud credentials | Met. `.github/workflows/checks.yml` runs the four checks on every pull request and holds no cloud credentials |
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

The plan was a CIS benchmark run. No tool can do one for this release yet, the vendor's own included.

| Tool | Checked on 2026-10-11 | Result |
| --- | --- | --- |
| CIS Ubuntu Linux 26.04 LTS Benchmark | The CIS monthly update for October 2026 | Exists, v1.0.0, published the month before |
| OpenSCAP with ComplianceAsCode content 0.1.82 | The `ubuntu2604` product in the release | Ships a `default` profile only. No CIS profile |
| Ubuntu Security Guide | Attached the orchestrator to an Ubuntu Pro subscription and ran `pro enable usg` | `Ubuntu Security Guide is not available for Ubuntu 26.04 LTS (Resolute Raccoon).` The orchestrator was detached again |
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
| `SSH-7408`, SSH daemon options | `/etc/ssh/sshd_config.d/10-aisec.conf`: no root login, no agent or X11 forwarding, 3 authentication tries, 2 sessions, client alive checks, verbose logging. TCP forwarding is off |
| `KRNL-6000`, kernel settings | `/etc/sysctl.d/90-aisec-hardening.conf`: SysRq off, kernel pointers hidden, no core dumps from setuid programs, protected FIFOs and regular files, hardened BPF JIT, no source routing, no ICMP redirects in or out, martian packets logged |
| `NETW-3200`, `USB-1000`, unused protocols and USB storage | `/etc/modprobe.d/aisec-unused.conf` stops `dccp`, `sctp`, `rds`, `tipc`, and `usb-storage` from loading |
| `PKGS-7392`, pending updates | Installed on the orchestrator, above |

Checked after the change: `sshd -t` passed on both VMs, new logins worked, the feed path and the routed path to the worker worked, K3s reported the node `Ready` with three pods running.

Accepted:

| Finding | Reason |
| --- | --- |
| `KRNL-6000`, what is left: IP forwarding on, loose reverse path filter, module loading allowed | The orchestrator is the subnet router. Strict reverse path filtering breaks the tunnel and the pod network. K3s and the mesh VPN agent load modules after boot |
| `SSH-7408`, port 22 | Moving the port hides nothing from anyone who can reach these machines |
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

These three were open after the first triage and were reviewed afterwards:

| Finding | Answer |
| --- | --- |
| `BOOT-5264`, service hardening | Fixed for the one service the untrusted side can reach. Squid got a systemd sandbox: no new privileges, five capabilities, read-only system directories, private `/tmp` and devices, restricted address families and namespaces. `systemd-analyze security squid` went from `9.8 UNSAFE` to `4.3 OK`. Accepted for `k3s`, `tailscaled`, and `ssh`, all at `9.6`: each needs root and broad access to do its job |
| `FILE-7524`, file permissions | Fixed. `/etc/crontab` and `/etc/ssh/sshd_config` from `644` to `600`. The five cron directories from `755` to `700` |
| `HRDN-7222`, compilers present | Fixed. No compiler was installed. The assembler and linker were, through `binutils`, and nothing depended on it. Removed on both VMs |

After these changes Squid still returned 200 for a package host and 403 for another host and for a tunnel, `sshd -t` passed on both VMs, new logins worked, and K3s reported the node `Ready`.

The audit was not run a third time, so the hardening index after these three fixes is not measured.

### Updates on the worker

The worker's clean result on packages in the first run means nothing. The audit runs `apt-get update` first, and on the worker that hung for about six minutes and then failed, as designed: the worker has no path to a package repository. Its package lists are the ones from the image, so it does not know what is outdated. The second run skipped that test.

ADR 0009 gave the worker its packages through a SOCKS forward opened from the orchestrator. That was never run, and [ADR 0011](../decisions/0011-package-proxy-for-the-worker.md) replaced it with the proxy below.

## Package proxy

Squid 7.2 from the Ubuntu `main` repository runs on the orchestrator and listens on `10.40.0.4:3128` only. Its whole configuration is `/etc/squid/squid.conf` from cloud-init. On the running orchestrator it was installed by hand with the same content.

Two rules were added and applied from a saved plan that showed nothing else: `0 to add, 2 to change, 0 to destroy`.

| Security group | Priority | Direction | Access | Port | Rule |
| --- | --- | --- | --- | --- | --- |
| Orchestrator | 1000 | Inbound | Allow | TCP 3128 from the worker subnet | `allow-package-proxy-from-worker` |
| Worker | 1000 | Outbound | Allow | TCP 3128 to the orchestrator subnet | `allow-package-proxy-to-orchestrator` |

Afterwards `terraform plan -detailed-exitcode` exited `0`. The effective rules on both network interfaces equal the configured rules, now 10 and 8, plus the same platform IPv6 deny as before.

Tested from the worker, with `curl -x http://10.40.0.4:3128` and the TCP test from above:

| Request | Result |
| --- | --- |
| `GET` a release file on `archive.ubuntu.com` | 200 |
| `GET` a release file on `security.ubuntu.com` | 200 |
| `GET http://example.com/` | 403 |
| `POST` to `archive.ubuntu.com` | 403 |
| `GET` on `archive.ubuntu.com:8080` | 403 |
| `CONNECT archive.ubuntu.com:443` | 403 |
| `CONNECT example.com:443` | 403 |
| Direct TCP to `1.1.1.1:443` and to a target address | No connection |
| Direct TCP to the orchestrator on 22 and 6443 | No connection |
| Direct TCP to the orchestrator on 3128 | Open |

A request through the proxy from the orchestrator's own address returned 403: only the worker subnet is served. IP flow verify from the worker returns `Allow` by `allow-package-proxy-to-orchestrator` for port 3128 and `Deny` by `deny-all-outbound` for port 6443.

Then the worker's first update:

```bash
sudo apt-get update
sudo unattended-upgrade
```

| Step | Result |
| --- | --- |
| `apt-get update` | Fetched 32.0 MB in 3 seconds |
| Pending before | 5 packages, 3 from the security suite: `libpng16-16t64`, `libxml2-16`, `sudo` |
| `unattended-upgrade` | Exit `0` |
| Pending after | 2 packages, none from the security suite. No restart required |

The proxy log for the session shows 53 forwarded `GET` requests, to the two package hosts only, and the refusals from the tests. It also shows refused requests the worker makes by itself, to `motd.ubuntu.com` and to an HTTPS host. The image's login message and subscription hooks try to phone home. The proxy says no.

With the proxy in place, the worker's SSH daemon refuses TCP forwarding again, like the orchestrator's.

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

## Worker rebuild

Run on 2026-10-11, after the milestone closed. The worker was still empty, so a rebuild cost nothing, and it answers whether the current template builds the machine the checks describe. The procedure is in the [runbook](../runbooks/platform-compute.md#rebuild-the-worker).

```bash
terraform plan -replace='azurerm_linux_virtual_machine.vm["worker"]' -out=platform.tfplan
terraform apply platform.tfplan
```

```text
Apply complete! Resources: 1 added, 0 changed, 1 destroyed.
```

The destroy took 57 seconds and the create 54. The network interface, the address, and the security group were not touched.

| Check | Result |
| --- | --- |
| Serial log | Cloud-init finished at 20:14:08 UTC, 80.2 seconds after boot |
| Host key | New. The fingerprint in the serial log equals the one the worker presents |
| `cloud-init status` | `status: done` |
| Proxy setting, SSH daemon settings, file modes, `binutils` removed | All as the template writes them, read on the VM |
| Feed login from the orchestrator, after its public key was added again | `aisec-worker` |
| Package index refresh through the proxy | 32.0 MB fetched from the two Ubuntu hosts |
| `sudo unattended-upgrade` | Installed `libpng16-16t64`, `libxml2-16`, `sudo`. Nothing left from the security suite. Two packages left from `resolute-updates` |
| `validation/platform-checks.sh` | 94 passed, 0 failed, at 20:18 UTC |
| Idle use | 533 MiB of 7905 used, 2.2 GB of disk |

The rebuild found one gap in the procedure. Step 14 adds the worker's host key on the orchestrator only if no entry exists. After a rebuild an entry exists and is wrong, so the feed login fails on a changed host key. The rebuild steps remove the old entry first.

What this does not show: the orchestrator's template. That rebuild needs a new mesh VPN key, a signed node, and K3s from nothing, and has not been run.

## Bootstrap state copy

Run on 2026-10-11. The bootstrap root keeps local state, because it creates the accounts a backend would need. That file was the only record of what the root owns.

The root now creates a `bootstrap` container in the platform state account, and gives the operator `Storage Blob Data Contributor` on that container alone. The plan was 2 to add. The file is uploaded by hand after each apply:

```bash
az storage blob upload --auth-mode login \
  --account-name "$(terraform output -json state_storage_accounts | jq -r .platform)" \
  -c bootstrap -n terraform.tfstate -f terraform.tfstate --overwrite
openssl md5 -binary terraform.tfstate | base64
```

The upload at 20:13:43 UTC returned a `content_md5` equal to the checksum of the local file, and a `version_id`, so blob versioning keeps earlier uploads.

The platform identity holds a data role on the whole account and can read the copy. The state holds identifiers and no key, so that is accepted. The target identity cannot reach it.

Not done: a restore. Nobody has downloaded the copy and planned against it.

## Limitations

- **The benchmark profile is older than the cluster.** `k3s-cis-1.9` was written for K3s 1.27 to 1.29. The cluster runs 1.36. A newer profile does not ship with the tool.
- **The running orchestrator differs from its template in how it got one fix.** The segment size clamp was installed by hand with the same content as the cloud-init template. A VM built from the template has not been booted with it.
- **The worker can open one connection to the orchestrator, to the package proxy.** Everything else is refused. Dispatch and results in milestone 3 still have to be initiated from the orchestrator, or get their own rule.
- **The worker's updates depend on the proxy and on two hostnames.** If either changes, updates stop quietly. Nothing alerts on that yet.
- **The targets have no update path.** The proxy is for the worker only. Milestone 4 decides how the targets are kept current.
- **No CIS result for the operating system.** No tool ships a CIS profile for Ubuntu 26.04 yet. The audit that ran is not a CIS benchmark. Carried as an accepted risk in the [threat model](../security/accepted-risks.md#accepted-risks) until one does.
- **No audit daemon, remote logging, or file integrity monitoring on either VM.** Open until the audit log decision in milestone 3.
- **The hardening on the running orchestrator was applied by hand.** The operating system part has the same content as its template. The two cluster settings from runbook steps 17 and 18 were not in the template until 2026-10-12. The orchestrator has not been built from it. The worker has. See [Worker rebuild](#worker-rebuild).
- **Mesh VPN connections are relayed.** Fine for administration, slow for bulk transfer.
- **Node signing was turned on after the orchestrator joined.** Enabling it signed the existing nodes. `tailscale lock status` on the orchestrator reports `Tailnet Lock is ENABLED` and a signature by the workstation's key, with two trusted signing keys. A rebuild is different: the new node has to be signed, and that path has not been run.
- **No encryption at host.** The feature is not registered on the subscription.
- **The regional core quota is full.**
- **Built once.** The runbook was written from this build. The worker has been rebuilt once. A rebuild of everything from scratch and a removal have not been run.
