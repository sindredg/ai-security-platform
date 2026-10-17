# Host hardening

The same settings on every VM, from cloud-init. They came out of the Lynis audit in [milestone 2](../worklogs/0002-platform-compute.md#operating-system-audit). The checks are the same list on each: `HO` on the orchestrator, `HW` on the worker, `HR` on the router.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `.1` | No failed systemd unit | A unit that failed at boot is the first sign of a broken rebuild | `systemctl --failed` |
| `.2` | No root login over SSH | One named account, and `sudo` from there | `sshd -T` |
| `.3` | No password login | Keys only. No account has a password | `sshd -T` |
| `.4` | No TCP forwarding | An SSH session is not a tunnel into either network. The one exception, for the administrator on the orchestrator, is `A.8` | `sshd -T` |
| `.5` | No agent forwarding | The operator's agent stays on the workstation | `sshd -T` |
| `.6` | Three authentication tries | Default is six | `sshd -T` |
| `.7` | SysRq is off | No kernel commands from a console | `sysctl` |
| `.8` | Kernel pointers are hidden | Less help for a local exploit | `sysctl` |
| `.9` | ICMP redirects are ignored | Nobody on the subnet reroutes this machine | `sysctl` |
| `.10` | The BPF JIT is hardened | Less help for a local exploit | `sysctl` |
| `.11`, `.12`, `.13` | `/etc/crontab`, `sshd_config`, and `/etc/cron.d` are closed to group and world | Only root reads what root schedules | `stat` |
| `.14` | No assembler, linker, or compiler | Nothing on the machine builds a tool it was not given | `command -v` |
| `.15` | Unused network protocols and USB storage are not loaded | Less kernel surface | `lsmod` |
| `.16` | The clock is synchronized | Tokens and certificates depend on it. The worker has no internet and still syncs, from the hypervisor | `timedatectl` |
| `.17` | The administrator account takes only a certificate | A plain key, a copied one included, works until someone removes it everywhere. [ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md) | `sshd -T -C user=aisec,...` shows `authorizedkeysfile none` and the authority, principals, and revocation files |
| `.18` | The certificate authority is the operator's | Whoever holds the key in that file can sign a login | The fingerprint of `/etc/ssh/aisec-user-ca.pub`, which holds one key, equals that of the file `AISEC_USER_CA` names on the workstation. Without that variable the check fails |
| `.19` | One principal, in a file root owns | A principal in a file the account can write is a name anyone signs for | `stat` and the file's content: `root root 644 aisec-operator` |
| `.20` | The revocation list is root's and loads | sshd refuses every certificate if the list is missing or cannot be read, and a list the account can write revokes nothing | `stat`, and `ssh-keygen -Q -l` reads it |

## Accepted, and not checked

These are settings the audit asked for that stay as they are. The reasons are in the worklog.

- IP forwarding on the orchestrator, loose reverse path filtering, and module loading after boot.
- No `auditd`, no remote logging, and no file integrity monitoring yet. Remote logging is planned for [milestone 3a](../roadmap.md#3a-edge-network-and-monitoring), the other two for milestone 6.
- `k3s`, `tailscaled`, and `ssh` run without a systemd sandbox.
