# 0007. Mesh VPN for administrative access

Status: Accepted
Date: 2026-10-10

## Context

No VM has a public inbound endpoint. The operator still needs shell access to four Linux VMs in two regions and browser access to the Argo interface.

The access method must not depend on the operator's network address. That address changes, and it must not appear in the repository or in cloud configuration. The method must also work for the AI worker VM, which has no internet egress.

## Options

| Option | Operator address needed | Inbound exposure | Reach | Cost and effort |
| --- | --- | --- | --- | --- |
| Public IP with SSH restricted to the operator's address | Yes, in a network rule | One public port per VM | Direct | Low, but breaks when the address changes |
| Azure Bastion, Developer SKU | No | None | Portal sessions only, one VM at a time, same virtual network only | No hourly charge |
| Azure Bastion, Basic SKU | No | A managed public endpoint | All VMs, including peered networks | USD 0.19 per hour while deployed |
| Point-to-site VPN gateway | No | A managed public endpoint | All VMs | Hourly gateway charge, certificate management |
| Mesh VPN agent on the orchestrator, acting as subnet router | No | None | All VMs through the orchestrator | One agent, one secret |

## Decision

Use Tailscale. Install its agent on the orchestrator VM and on the operator's workstation.

- The orchestrator advertises the platform and target address ranges as a subnet router. The other VMs run no agent.
- The operator uses SSH with key authentication to reach each VM's private address, and reaches the Argo interface the same way.
- Access is limited to the operator's signed-in devices by the mesh access policy.
- The agent's auth key is a secret. It is supplied at provisioning time and never committed.
- No VM gets a public IP for administration, and no network rule names an operator address.

## Trade-offs

- **A third-party coordination service joins the trust boundary.** It handles device identity and key exchange. Traffic is encrypted end to end between devices and does not pass through it in the clear.
- **The orchestrator needs outbound internet access** for the agent. This is part of the egress design, which is still open.
- **The orchestrator becomes the single administrative path.** If it is down, the other VMs are reachable only through the cloud provider's serial console or run-command features.
- **Administrative traffic to targets arrives from the orchestrator's address.** The subnet router translates source addresses, so target network rules cannot tell operator sessions from collection traffic by address. They are separated by port and credential instead.
- **The orchestrator forwards packets.** IP forwarding is enabled on it, which widens what a compromise of that VM can reach. It already holds the platform's most sensitive credentials, so this does not create a new most-trusted component.
