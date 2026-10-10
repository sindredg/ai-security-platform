# 0007. Mesh VPN for administrative access

Status: Accepted
Date: 2026-10-10

## Context

No VM has a public endpoint. That is deliberate, but it leaves a problem: getting a shell on four Linux VMs in two regions, and the Argo UI in a browser.

Opening SSH to a home IP is the obvious fix and a bad one. Home addresses change, and an operator IP has no business in a firewall rule or a public repository.

The method also has to reach the AI worker, which is cut off from the internet on purpose.

## Options

| Option | Operator address needed | Inbound exposure | Reach | Cost and effort |
| --- | --- | --- | --- | --- |
| Public IP with SSH restricted to the operator's address | Yes, in a network rule | One public port per VM | Direct | Low, until the address changes |
| Azure Bastion, Developer SKU | No | None | Portal sessions only, one VM at a time, same virtual network only | No hourly charge |
| Azure Bastion, Basic SKU | No | A managed public endpoint | All VMs, including peered networks | USD 0.19 per hour while deployed |
| Point-to-site VPN gateway | No | A managed public endpoint | All VMs | Hourly gateway charge, certificates to manage |
| Mesh VPN agent on the orchestrator, acting as subnet router | No | None | All VMs through the orchestrator | One agent, one secret |

## Decision

Use Tailscale. Its agent runs on the orchestrator VM and on the operator's workstation, and nowhere else.

- The orchestrator advertises the platform and target address ranges as a subnet router. The other VMs need no agent.
- The operator uses SSH with key authentication to each VM's private address, and reaches the Argo interface the same way.
- The mesh access policy limits access to the operator's signed-in devices.
- The agent's auth key is a secret. It is supplied at provisioning time and never committed.
- No VM gets a public IP for administration, and no network rule names an operator address.

## Trade-offs

- **A third party joins the trust boundary.** Tailscale's coordination service handles device identity and key exchange. Traffic is encrypted between devices and the service does not see it in the clear.
- **The orchestrator needs outbound internet** for the agent. That is part of the egress design, which is still open.
- **The orchestrator is the only way in.** If it is down, the other VMs are reachable only through the provider's serial console or run-command features.
- **Operator sessions to targets arrive from the orchestrator's address.** The subnet router translates source addresses, so target network rules cannot tell an operator from a collector by address. Port and credential separate them instead.
- **The orchestrator forwards packets.** That widens what a compromise of it can reach. It already holds the platform's most sensitive credentials, so this does not create a new most-trusted machine. It makes the existing one matter slightly more.
