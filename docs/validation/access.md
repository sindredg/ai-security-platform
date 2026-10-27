# Access

No VM has a public address. The only way in is the mesh VPN to the router, then SSH with a certificate that expires after 12 hours ([ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md)). The router is the only platform node on the mesh ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md)). The certificate settings themselves are `.17` to `.20` on [host hardening](host-hardening.md), for every VM. The logins to the targets, and the address they see, are `VN.1` to `VN.3` and `VL.1` to `VL.3` on [targets](targets.md). The design is [ADR 0007](../decisions/0007-mesh-vpn-for-administrative-access.md). The threat is T01 in the [threat model](../security/threat-model.md): a device that is not the operator's joins the mesh.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `A.1` | The orchestrator is reachable through the router with the operator certificate | Without this there is no administration of the cluster | An SSH login from the workstation |
| `A.2` | Node signing is enabled on the mesh | The coordination service cannot add a device by itself | `tailscale lock status` on the router |
| `A.3` | The router's node key is signed | An unsigned node is on the network but cannot reach any other node | The same command |
| `A.4` | The spent auth key file is gone | The key is single use, and the file should not outlive first boot | `/run/aisec` on the router is empty |
| `A.5` | No plain key is authorized for the administrator on the orchestrator | sshd ignores the file for this account, so a line there is a change someone made. First boot removes the key Azure writes. On the router and the edge, cloud-init writes the file back empty after that, so the check counts lines, not the file | No line in `/home/aisec/.ssh/authorized_keys` |
| `A.6` | The worker is reachable through the subnet router | Proves the route, the segment size clamp, and the worker's SSH rule together | An SSH login from the workstation |
| `A.7` | No plain key is authorized for the administrator on the worker | The same. The feed key logs in to its own account ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)), `E.4` and `E.9` to `E.11` | No line in the same file on the worker |
| `A.8` | The administrator on the orchestrator forwards only to the API server on loopback | The one tunnel the design allows, for `kubectl` | `sshd -T -C user=aisec,...` shows `allowtcpforwarding local` and `permitopen 127.0.0.1:6443` |
| `A.9` | Other accounts on the orchestrator forward nothing | The exception is for one account | The same query for another user shows `no`. Before the rollout it passed already. Its fail side was seen with a configuration on standard input that allows forwarding for everyone: the probe printed `yes` |
| `A.11` | The orchestrator is not on the mesh VPN | It holds every credential. A mesh node on it is a way from the vendor's coordination service to those credentials ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)) | The package's status, from `dpkg-query`, does not end in `ok installed`, and no `tailscale0` interface exists. Two counts, both `0` |
| `A.12` | The router is reachable over the mesh VPN with the operator certificate | It is the way in. When it is down, administration goes through Azure run command (T03) | An SSH login from the workstation to the router's mesh name |
| `A.13` | No plain key is authorized for the administrator on the router | As `A.5` | No line in the same file on the router |
| `A.14` | The administrator on the router forwards nothing | Routed sessions pass through the router at the IP layer. An SSH forward would be a second path, around the security groups' view of it | `sshd -T` on the router shows `no` and `any`, as `A.10` |
| `A.15` | The edge is reachable through the router with the operator certificate | Administration of the edge, and the just-in-time (JIT) egress window | An SSH login from the workstation to `10.45.0.4` |
| `A.16` | No plain key is authorized for the administrator on the edge | As `A.5` | No line in the same file on the edge |
| `A.17` | The administrator on the edge forwards nothing | The edge's proxy is the only service it offers | `sshd -T` on the edge shows `no` and `any`, as `A.10` |
| `A.18` | The edge is not on the mesh VPN | [ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md) keeps the mesh node on the router alone | The package's status, from `dpkg-query`, does not end in `ok installed` |
| `A.10` | The administrator on the worker forwards nothing | The tunnel is for the orchestrator only | The same query on the worker shows `no` and `any`. The `any` is the default `PermitOpen`, which `no` makes moot. Before the rollout it passed already. Its fail side was seen with a configuration given on standard input that allows the forward: the probe printed `local 127.0.0.1:6443` |
| `M.1` | The mesh policy allows SSH to the orchestrator | Administration | A TCP connection from the workstation to port 22 |
| `M.2` | The mesh policy drops the Kubernetes API | `kubectl` goes through an SSH tunnel to the orchestrator (`A.8`). Over the mesh, a stolen operator device would reach the API without a certificate that expires | A TCP connection to port 6443 times out. The API server listens there (`K.1`) |
| `M.3` | The mesh policy drops the proxy port on the edge | A mesh device has no business on the proxy | A TCP connection to `10.45.0.4:3128` times out. Squid listens there (`P.2`), so `refused` would mean the packet arrived. Until 2026-10-17 this read the orchestrator |
| `M.9` | The mesh policy drops the target port on the edge | As `M.3`, for the targets' package port | A TCP connection to `10.45.0.4:3129` times out. Squid listens there (`P.2`) |
| `M.4` | The mesh policy drops the kubelet port | The kubelet API is not an administration interface | A TCP connection to port 10250 times out |
| `M.5` | The mesh policy drops the tool port | The tool port is for the worker | A TCP connection to the orchestrator's private address on port 30443 times out. Not seen to fail: changing the mesh policy is not a read-only step. Port 22 on the same address is `open`, so the probe can see a connection |
| `M.6` | The mesh policy allows SSH to the router | Administration of the router | A TCP connection to port 22 on the router's mesh name |
| `M.7` | The mesh policy drops another port on the router | The grant to the router is one port | A TCP connection to port 80 times out. Nothing listens there, so `refused` would mean the policy let the packet in |
| `M.8` | The mesh policy allows SSH to the edge | Administration of the edge, and the JIT egress window | A TCP connection to `10.45.0.4:22` |

## The router

The router runs the mesh agent and nothing else ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md)).

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `R.1` | The mesh VPN agent is active | The router is the way in | `systemctl is-active` |
| `R.2` | The segment size clamp is loaded | Without it, connections through the router stall. See [troubleshooting 02](../troubleshooting/02-ssh-through-subnet-router-stalls.md) | The unit is `active`, and the `aisec_mss` table has two rules |
| `R.3` | The router forwards packets | It routes for the mesh | `net.ipv4.ip_forward` is `1` |
| `R.4` | The router advertises the platform, the targets, and the edge subnet | A route that is missing cuts off a network. A route that is added gives the mesh a network nobody decided | `AdvertiseRoutes` from `tailscale debug prefs`, sorted, equals `10.40.0.0/20 10.45.0.0/27 10.50.0.0/20` |
| `R.5` | The mesh VPN agent uploads no logs to the vendor | The vendor would get a record of the router's activity | `--no-logs-no-support` on the running agent's command line, from `/proc`. The defaults file alone would not show an agent started without it |
| `R.6` | Tailscale SSH and the web client are off | Either is a way in that skips sshd and the certificate | `RunSSH` and `RunWebClient` from `tailscale debug prefs`, both `false` |
| `R.7` | Nothing is served or funnelled through the mesh VPN | Funnel publishes a port to the internet. Serve publishes it to the mesh | `tailscale serve status --json` prints `{}`. No answer is a failure |

`E.5`, `U.2`, and `U.6` to `U.9` also read the router. They are on [containment](containment.md#the-orchestrators-side) and [package proxy](package-proxy.md).

Not checked by the script: that each operator device runs with `shields-up`, and that the policy's `tests` are in place. Both are console or device settings. The [router runbook](../runbooks/mesh-router.md) lists them.

## What these checks found

`M.3` and `M.4` failed on their first run, on 2026-10-11. The mesh access policy was the provider's default, which allows every device to reach every port, so the threat model's statement that mesh access is limited was not true. The policy was replaced the same day and both checks passed. The policy text is on the [mesh VPN page](../components/mesh-vpn.md#access-policy).

The policy is set in the provider's admin console. These two checks are the only thing in the repository that notices if it is loosened.
