# Mesh VPN

The only way in. No VM has a public address and no firewall rule names an operator address. The operator's devices and the orchestrator are on a Tailscale network, and the orchestrator routes from it to both virtual networks.

| | |
| --- | --- |
| State | Built |
| Agent version | 1.104.1, from the vendor's signed package repository, held at that version |
| Pinned in | `infra/platform/variables.tf` |
| Runs on | The orchestrator and the operator's devices. Nowhere else |
| Routes advertised | `10.40.0.0/20` and `10.50.0.0/20` |
| Decision | [0007](../decisions/0007-mesh-vpn-for-administrative-access.md) |

## The path

![Mesh VPN path: the operator device and the orchestrator each open outbound connections to the coordination service for control and to a relay server over TLS on port 443 for the tunnel, the orchestrator's through the NAT gateway, and the orchestrator decrypts, filters, clamps the segment size, translates the source address, and forwards to the worker and the target network on TCP 22](../diagrams/mesh-path.svg)

The diagram source is [`diagrams/mesh-path.html`](../diagrams/mesh-path.html).

Nothing dials in. Both ends open their connections outbound, which is why the orchestrator's security group has no inbound rule for administration.

| Stage | What happens | Read on the orchestrator, 2026-10-12 |
| --- | --- | --- |
| Control | Each agent keeps one connection to the coordination service. It hands out peer keys, the access policy, and node signatures, and carries no traffic. The protocol encrypts itself and runs over TCP 80 here. The agent is built to fall back to 443. That was not tested | `ss`: one connection from `tailscaled` to the vendor's login host on port 80. `tailscale lock status`: enabled, node signed |
| Tunnel | WireGuard between the two agents, encrypted end to end. Each agent sends it inside TLS on port 443 to a relay server, which forwards ciphertext | `tailscale status`: the workstation is `active; relay`, with no direct address. `ss`: two connections from `tailscaled` to relay hosts on port 443 |
| Filter | The orchestrator's agent drops anything the access policy does not allow, for itself and for the routed networks | The agent's packet filter holds TCP 22 and 6443 for its own address and both networks, and nothing else. Checks `M.1` to `M.4` test it with traffic |
| Clamp | Routed TCP handshakes get a maximum segment size of 1240 | `tailscale0` has MTU 1280, `eth0` 1500, and the rule is loaded |
| Translate | The source address becomes `10.40.0.4`. The worker and target machines never see a mesh address, so their security groups name the orchestrator subnet and nothing else | `NoSNAT` is `false`, the masquerade rule counts packets, and an SSH login from the workstation shows `10.40.0.4` as its client on the worker |
| Forward | The security groups allow TCP 22 from the orchestrator subnet to the worker and to the target network. The policy also allows 6443 to the routed networks. The security groups do not | The rules are in [egress and policy](egress-and-policy.md#rules-on-the-platform-side) |

The agent also tries a direct connection over UDP. Those attempts failed here, because the NAT gateway gives each destination a different mapping (`tailscale netcheck` reported `MappingVariesByDestIP: true`), so the relay carried everything. [ADR 0017](../decisions/0017-no-udp-from-the-orchestrator.md) removes the UDP rules, so the relay is the only path.

## How a node joins

A single-use, tagged auth key that lasts one day. It travels in the VM's custom data, is used once at first boot, and its file is removed. The key ends up in Terraform state, which is why it has to be single use.

Node signing is on. Two of the operator's devices hold signing keys. A node that joins without a signature is on the network but cannot reach any other node.

## The segment size clamp

The tunnel carries 1280-byte packets and the virtual network 1500. The worker and target machines never see the "fragmentation needed" reply, because their security groups drop ICMP. So the orchestrator rewrites the maximum segment size on every routed TCP handshake. Without it, a connection through the router opens and then stalls. See [troubleshooting 02](../troubleshooting/02-ssh-through-subnet-router-stalls.md).

## Access policy

Set in the provider's admin console, not from this repository. The operator's devices reach the orchestrator and the two routed networks on SSH and the Kubernetes API. Nothing else is allowed, in either direction.

```json
{
    "tagOwners": {
        "tag:aisec-orchestrator": ["autogroup:admin"],
    },
    "grants": [
        {
            "src": ["autogroup:member"],
            "dst": ["tag:aisec-orchestrator"],
            "ip":  ["tcp:22", "tcp:6443"],
        },
        {
            "src": ["autogroup:member"],
            "dst": ["10.40.0.0/20", "10.50.0.0/20"],
            "ip":  ["tcp:22", "tcp:6443"],
        },
    ],
}
```

The provider's default policy allows everything, and that default was in place until 2026-10-11. Checks `M.3` and `M.4` fail if it comes back. The console's default rule for the provider's own SSH feature is left as it was. It applies to a user's own devices and not to the tagged orchestrator.

## Validation

`A.1` to `A.4`, `R`, and `M` in the [validation pages](../validation/access.md).

## Limits

- **A third party is in the trust boundary.** The coordination service handles identity and key exchange. Node signing limits what it can do alone.
- **Connections are relayed.** A NAT gateway prevents direct connections. Fine for a shell, slow for bulk.
- **The access policy and the signing setup are console settings.** Nothing in the repository can rebuild them.
- **The agent version is held.** It gets no security fix until someone moves the pin.
- **Signing a node after it joins has not been run.** The orchestrator rebuild on 2026-10-13 joined on a signed auth key, which needs no step afterwards.
- **The agent uploads its own logs to the vendor.** On 2026-10-12 `tailscaled` held a connection to the vendor's log host on port 443. The agent runs with no extra flags, so the upload is on. Whether to turn it off is not decided.

## Official documentation

- [Subnet routers](https://tailscale.com/kb/1019/subnets)
- [Tailnet Lock](https://tailscale.com/kb/1226/tailnet-lock)
- [Auth keys](https://tailscale.com/kb/1085/auth-keys)
- [Tags](https://tailscale.com/kb/1068/tags)
- [Grants](https://tailscale.com/kb/1324/grants)
- [Reference architecture for Azure](https://tailscale.com/docs/reference/reference-architectures/azure)
- [nftables: mangling packet headers](https://wiki.nftables.org/wiki-nftables/index.php/Mangling_packet_headers)
