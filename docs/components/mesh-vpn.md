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

## How a node joins

A single-use, tagged auth key that lasts one day. It travels in the VM's custom data, is used once at first boot, and its file is removed. The key ends up in Terraform state, which is why it has to be single use.

Node signing is on. Two of the operator's devices hold signing keys. A node that joins without a signature is on the network and can talk to nothing.

## The segment size clamp

The tunnel carries 1280-byte packets and the virtual network 1500. The fed machines never see the "fragmentation needed" reply, because their security groups drop ICMP. So the orchestrator rewrites the maximum segment size on every routed TCP handshake. Without it, a connection through the router opens and then stalls. See [troubleshooting 02](../troubleshooting/02-ssh-through-subnet-router-stalls.md).

## Access policy

Set in the provider's admin console, not in this repository. The intended policy: the operator's devices reach the orchestrator and the two routed networks on TCP 22 and 6443, and nothing else. Checks `M.3` and `M.4` fail until it is in place.

## Validation

`A.1` to `A.4`, `R`, and `M` in the [validation pages](../validation/access.md).

## Limits

- **A third party is in the trust boundary.** The coordination service handles identity and key exchange. Node signing limits what it can do alone.
- **Connections are relayed.** A NAT gateway prevents direct connections. Fine for a shell, slow for bulk.
- **The access policy and the signing setup are console settings.** Nothing in the repository can rebuild them.
- **The agent version is held.** It gets no security fix until someone moves the pin.
- **A rebuild with node signing on has not been run.**

## Official documentation

- [Subnet routers](https://tailscale.com/kb/1019/subnets)
- [Tailnet Lock](https://tailscale.com/kb/1226/tailnet-lock)
- [Auth keys](https://tailscale.com/kb/1085/auth-keys)
- [Tags](https://tailscale.com/kb/1068/tags)
- [Grants](https://tailscale.com/kb/1324/grants)
- [Reference architecture for Azure](https://tailscale.com/docs/reference/reference-architectures/azure)
- [nftables: mangling packet headers](https://wiki.nftables.org/wiki-nftables/index.php/Mangling_packet_headers)
