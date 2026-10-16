# Access

No VM has a public address. The only way in is the mesh VPN, then SSH with a certificate that expires after 12 hours ([ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md)). The certificate settings themselves are `HO.17` to `HO.20` and `HW.17` to `HW.20` on [host hardening](host-hardening.md). The design is [ADR 0007](../decisions/0007-mesh-vpn-for-administrative-access.md). The threat is T01 in the [threat model](../security/threat-model.md): a device that is not the operator's joins the mesh.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `A.1` | The orchestrator is reachable over the mesh VPN with the operator certificate | Without this there is no administration at all | An SSH login from the workstation |
| `A.2` | Node signing is enabled on the mesh | The coordination service cannot add a device by itself | `tailscale lock status` on the orchestrator |
| `A.3` | The orchestrator's node key is signed | An unsigned node is on the network but cannot reach any other node | The same command |
| `A.4` | The spent auth key file is gone | The key is single use, and the file should not outlive first boot | `/run/aisec` is empty |
| `A.5` | No plain key is authorized for the administrator on the orchestrator | sshd ignores the file for this account, so a line there is a change someone made. First boot removes the key Azure writes | No line in `/home/aisec/.ssh/authorized_keys` |
| `A.6` | The worker is reachable through the subnet router | Proves the route, the segment size clamp, and the worker's SSH rule together | An SSH login from the workstation |
| `A.7` | No plain key is authorized for the administrator on the worker | The same. The feed key logs in to its own account ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)), `E.4` and `E.9` to `E.11` | No line in the same file on the worker |
| `A.8` | The administrator on the orchestrator forwards only to the API server on loopback | The one tunnel the design allows, for `kubectl` | `sshd -T -C user=aisec,...` shows `allowtcpforwarding local` and `permitopen 127.0.0.1:6443` |
| `A.9` | Other accounts on the orchestrator forward nothing | The exception is for one account | The same query for another user shows `no`. Before the rollout it passed already. Its fail side was seen with a configuration on standard input that allows forwarding for everyone: the probe printed `yes` |
| `A.10` | The administrator on the worker forwards nothing | The tunnel is for the orchestrator only | The same query on the worker shows `no` and `any`. The `any` is the default `PermitOpen`, which `no` makes moot. Before the rollout it passed already. Its fail side was seen with a configuration given on standard input that allows the forward: the probe printed `local 127.0.0.1:6443` |
| `M.1` | The mesh policy allows SSH to the orchestrator | Administration | A TCP connection from the workstation to port 22 |
| `M.2` | The mesh policy allows the Kubernetes API | Cluster administration | A TCP connection to port 6443 |
| `M.3` | The mesh policy drops the proxy port | A mesh device has no business on the worker's proxy | A TCP connection to port 3128 times out. Squid listens there, so `refused` would mean the packet arrived |
| `M.4` | The mesh policy drops the kubelet port | The kubelet API is not an administration interface | A TCP connection to port 10250 times out |
| `M.5` | The mesh policy drops the tool port | The tool port is for the worker | A TCP connection to the orchestrator's private address on port 30443 times out. Not seen to fail: changing the mesh policy is not a read-only step. Port 22 on the same address is `open`, so the probe can see a connection |

## What these checks found

`M.3` and `M.4` failed on their first run, on 2026-10-11. The mesh access policy was the provider's default, which allows every device to reach every port, so the threat model's statement that mesh access is limited was not true. The policy was replaced the same day and both checks passed. The policy text is on the [mesh VPN page](../components/mesh-vpn.md#access-policy).

The policy is set in the provider's admin console. These two checks are the only thing in the repository that notices if it is loosened.
