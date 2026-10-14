# 0017. No UDP from the orchestrator to the internet

Status: Accepted
Date: 2026-10-14

## Context

[0009](0009-one-egress-point-on-the-orchestrator-subnet.md) let the orchestrator send UDP to the internet so the mesh VPN agent could try direct connections: UDP 3478 to learn its outside address (`allow-mesh-stun`), and UDP from port 41641 to any port (`allow-mesh-direct`).

Those attempts never succeed here. The NAT gateway gives each destination a different mapping, which `tailscale netcheck` reports as `MappingVariesByDestIP: true`, so the relay carries every connection over TCP 443. 0009 already said so in its trade-offs. The second rule is the widest egress rule on the platform, and it buys nothing ([issue #49](https://github.com/sindredg/ai-security-platform/issues/49)).

## Options

| Option | Egress | What it keeps |
| --- | --- | --- |
| Keep both rules | TCP 443 and 80, UDP 3478, and every UDP port | A direct connection if the NAT ever allows one. It does not, as long as the gateway is the way out |
| Drop `allow-mesh-direct`, keep STUN | TCP 443 and 80, UDP 3478 | The agent can still learn its outside address. That address is no use without the direct path |
| Drop both | TCP 443 and 80 | Nothing the lab uses |

## Decision

The orchestrator sends no UDP to the internet. Both rules go. Its egress is TCP 443 and 80, through the NAT gateway.

Check `E.5` reads `tailscale netcheck` on the orchestrator and expects `UDP: false`.

## Trade-offs

- **Hostname filtering is still missing.** TCP 443 to any host stays open. This removes one path a compromised orchestrator could use, not the risk in T05.
- **A public address would need this undone.** Direct connections need both a mapping that does not vary and UDP. Giving the orchestrator a public address, which 0009 refuses, would need a new record anyway.
- **The relay is the only path.** That was already true in practice. Now it is true by rule, and a relay outage is a mesh outage.
- **Without UDP, the agent cannot measure relay latency by STUN.** How it picks a relay without it was reasoned from the vendor's documentation, not observed. `A.1`, `A.6`, and `R.1` show whether the mesh still works after the apply.
