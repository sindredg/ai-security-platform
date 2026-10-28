# Mesh VPN

The only way in. No VM has a public address and no firewall rule names an operator address. The operator's devices and a router VM are on a Tailscale network, and the router routes from it to the platform network, the target network, and the edge subnet.

| | |
| --- | --- |
| State | Built. The router since 2026-10-17 ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-router)). Verified by the `A` and `M` checks ([last run](../validation/README.md#last-run)). Before that, the orchestrator was the mesh node |
| Agent version | 1.104.4, from the vendor's signed package repository, held at that version, with its own updater off (`U.2`, `U.6`) |
| Pinned in | `infra/platform/variables.tf` |
| Runs on | The router VM and the operator's devices. Nowhere else (`A.11`) |
| Routes advertised | `10.40.0.0/20`, `10.50.0.0/20`, and `10.45.0.0/27` (`R.4`) |
| Decision | [0007](../decisions/0007-mesh-vpn-for-administrative-access.md), and [0025](../decisions/0025-the-mesh-node-on-its-own-vm.md) for the router |

## The router

`vm-aisec-router`, `Standard_B2ats_v2`, at `10.45.0.36` in its own subnet of the edge network in Denmark East. It runs the mesh agent and nothing else: no K3s, no workloads, no credential that reaches the cluster or the jobs. Its security group has no inbound allow (`Z.17`). It reaches the internet on TCP 443 and 80 through its own NAT gateway, and the platform, the targets, and the edge subnet on TCP 22.

Agent settings, each checked on the router:

| Setting | Value | Check |
| --- | --- | --- |
| Log upload to the vendor | Off: `--no-logs-no-support` on the running agent, from `/etc/default/tailscaled` | `R.5` |
| Automatic update | Off | `U.6` |
| Tailscale SSH, the web client | Off | `R.6` |
| Serve, Funnel | Nothing configured | `R.7` |
| DNS from the mesh | Not accepted (`--accept-dns=false`) | Not checked |

## The path

![Mesh VPN path: the operator device and the router each open outbound connections to the coordination service for control and to a relay server over TLS on port 443 for the tunnel, the router's through its NAT gateway, and the router decrypts, filters to TCP 22, clamps the segment size, translates the source address to 10.45.0.36, and forwards to the orchestrator, the worker, and the two target VMs on TCP 22](../diagrams/mesh-path.svg)

The diagram source is [`diagrams/mesh-path.html`](../diagrams/mesh-path.html).

Nothing dials in. Both ends open their connections outbound, which is why the router's security group has no inbound rule.

| Stage | What happens | Read on the router, 2026-10-17 |
| --- | --- | --- |
| Control | Each agent keeps one connection to the coordination service. It hands out peer keys, the access policy, and node signatures, and carries no traffic. The protocol encrypts itself and runs over TCP 80 here | `ss`: one connection from `tailscaled` on port 80. `tailscale lock status`: enabled, node signed |
| Tunnel | WireGuard between the two agents, encrypted end to end. Each agent sends it inside TLS on port 443 to a relay server, which forwards ciphertext | `tailscale status`: the workstation is `active; relay`. `ss`: two connections from `tailscaled` on port 443. `tailscale netcheck`: `UDP: false` |
| Filter | The router's agent drops anything the access policy does not allow, for itself and for the routed networks | Checks `M.1` to `M.7` test it with traffic |
| Clamp | Routed TCP handshakes get a maximum segment size of 1240 | `tailscale0` has MTU 1280, and the rule is loaded (`R.2`) |
| Translate | The source address becomes `10.45.0.36`. The machines behind the router never see a mesh address, so their security groups name the router subnet | `NoSNAT` is `false`, `ts-postrouting` holds the masquerade rule, and an SSH login shows `10.45.0.36` as the client on the worker and the orchestrator |
| Forward | `allow-ssh-from-router` on the orchestrator, the worker, the edge, and each target subnet. The router's own rules allow TCP 22 out to the three networks | The rules are in [egress and policy](egress-and-policy.md#rules-on-the-platform-side) |

The router's rules have no UDP, so the agent cannot try a direct connection, and the relay is the only path ([ADR 0017](../decisions/0017-no-udp-from-the-orchestrator.md), `E.5`).

The Kubernetes API is not on the mesh. `kubectl` goes through an SSH tunnel to the orchestrator, the one forward its administrator account allows (`A.8`, `M.2`).

## How a node joins

A single-use, tagged auth key that lasts one day, under `tag:aisec-router`. It travels in the VM's custom data, is used once at first boot, and its file is removed (`A.4`). The key ends up in Terraform state, which is why it has to be single use. The steps are in the [router runbook](../runbooks/mesh-router.md).

Node signing is on. Two of the operator's devices hold signing keys. A node that joins without a signature is on the network but cannot reach any other node. The router joined with a signed key (`A.3`).

## The segment size clamp

The tunnel carries 1280-byte packets and the virtual network 1500. The machines behind the router never see the "fragmentation needed" reply, because their security groups drop ICMP. So the router rewrites the maximum segment size on every routed TCP handshake. Without it, a connection through the router opens and then stalls. See [troubleshooting 02](../troubleshooting/02-ssh-through-subnet-router-stalls.md).

## Access policy

Set in the provider's admin console, not from this repository. The operator's devices reach the router and the three routed networks on SSH. Nothing else is allowed, and nothing grants the router a destination. The policy's `tests` refuse a change that lets the router reach the operator's login, or that opens more than SSH on the router.

```json
{
    "tagOwners": {
        "tag:aisec-router": ["autogroup:admin"],
    },
    "grants": [
        {
            "src": ["autogroup:member"],
            "dst": ["tag:aisec-router", "10.40.0.0/20", "10.45.0.0/27", "10.50.0.0/20"],
            "ip":  ["tcp:22"],
        },
    ],
    "tests": [
        {
            "src":    "<operator login>",
            "proto":  "tcp",
            "accept": ["tag:aisec-router:22"],
            "deny":   ["tag:aisec-router:80", "tag:aisec-router:6443"],
        },
        {
            "src":   "tag:aisec-router",
            "proto": "tcp",
            "deny":  ["<operator login>:22", "<operator login>:80", "<operator login>:443",
                      "<operator login>:445", "<operator login>:3389"],
        },
    ],
}
```

The grant to `tag:aisec-router` itself is not in ADR 0025, which names the routes only. Without it the router can be administered only through Azure run command.

The tests name single ports, because the policy language takes no port range in a test. Each operator device also runs with `shields-up`, which refuses every incoming connection whatever the policy says. That is a device setting, and no check reads it.

The provider's default policy allows everything, and that default was in place until 2026-10-11. Checks `M.3`, `M.4`, and `M.7` fail if it comes back. The console's default rule for the provider's own SSH feature is left as it was. It applies to a user's own devices and not to the tagged router.

## Validation

`A`, `R`, and `M` in the [validation pages](../validation/access.md).

## Limits

- **A third party is in the trust boundary.** The coordination service handles identity and key exchange. Node signing limits what it can do alone.
- **Connections are relayed.** No UDP leaves the router. Fine for a shell, slow for bulk.
- **The access policy and the signing setup are console settings.** Nothing in the repository can rebuild them.
- **The agent version is held.** It gets no security fix until someone moves the pin.
- **The agent's own updater was on until 2026-10-16.** The hold stopped `apt`, not the agent, which had `AutoUpdate.Apply` set and would have installed the vendor's next release as root. `U.6` failed on it, and passed after `tailscale set --auto-update=false`. No newer release had been published, so the held version was still the running one.
- **Signing a node after it joins has not been run.** The orchestrator rebuild on 2026-10-13 and the router on 2026-10-17 joined on a signed auth key, which needs no step afterwards.
- **The router is the way in.** When it is down, administration goes through Azure run command, which needs the Owner account. The serial console offers no login, because no account has a password (T03, [worklog](../worklogs/0003-toolchain-integration.md#the-routers-break-glass-path)).
- **Root on the router has a tailnet node, outbound TCP 443, and SSH reach to every network.** SSH still needs the operator's certificate, which never touches the router. Routed sessions pass through it as SSH ciphertext.
- **Log upload was on until 2026-10-17.** On 2026-10-12 the orchestrator's `tailscaled` held a connection to the vendor's log host on port 443. The router runs with `--no-logs-no-support` (`R.5`), which also means no help from the vendor's support.

## Official documentation

- [Subnet routers](https://tailscale.com/kb/1019/subnets)
- [Tailnet Lock](https://tailscale.com/kb/1226/tailnet-lock)
- [Auth keys](https://tailscale.com/kb/1085/auth-keys)
- [Tags](https://tailscale.com/kb/1068/tags)
- [Grants](https://tailscale.com/kb/1324/grants)
- [Reference architecture for Azure](https://tailscale.com/docs/reference/reference-architectures/azure)
- [nftables: mangling packet headers](https://wiki.nftables.org/wiki-nftables/index.php/Mangling_packet_headers)
