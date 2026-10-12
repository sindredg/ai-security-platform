# Access

No VM has a public address. The only way in is the mesh VPN, then SSH with one key. The design is [ADR 0007](../decisions/0007-mesh-vpn-for-administrative-access.md). The threat is T01 in the [threat model](../security/threat-model.md): a device that is not the operator's joins the mesh.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `A.1` | The orchestrator is reachable over the mesh VPN with the operator key | Without this there is no administration at all | An SSH login from the workstation |
| `A.2` | Node signing is enabled on the mesh | The coordination service cannot add a device by itself | `tailscale lock status` on the orchestrator |
| `A.3` | The orchestrator's node key is signed | An unsigned node is on the network and can talk to nothing | The same command |
| `A.4` | The spent auth key file is gone | The key is single use, and the file should not outlive first boot | `/run/aisec` is empty |
| `A.5` | Only the operator key is authorized on the orchestrator | A second key is a second way in | One line in `authorized_keys` |
| `A.6` | The worker is reachable through the subnet router | Proves the route, the segment size clamp, and the worker's SSH rule together | An SSH login from the workstation |
| `A.7` | Only the operator key and the feed key are authorized on the worker | The feed key is the orchestrator's way in | Two lines in `authorized_keys` |
| `M.1` | The mesh policy allows SSH to the orchestrator | Administration | A TCP connection from the workstation to port 22 |
| `M.2` | The mesh policy allows the Kubernetes API | Cluster administration | A TCP connection to port 6443 |
| `M.3` | The mesh policy drops the proxy port | A mesh device has no business on the worker's proxy | A TCP connection to port 3128 times out. Squid listens there, so `refused` would mean the packet arrived |
| `M.4` | The mesh policy drops the kubelet port | The kubelet API is not an administration interface | A TCP connection to port 10250 times out |

## What these checks found

`M.3` and `M.4` failed on their first run, on 2026-10-11. The mesh access policy was the provider's default, which allows every device to reach every port, so the threat model's statement that mesh access is limited was not true. The policy was replaced the same day and both checks passed. The policy text is on the [mesh VPN page](../components/mesh-vpn.md#access-policy).

The policy is set in the provider's admin console. These two checks are the only thing in the repository that notices if it is loosened.
