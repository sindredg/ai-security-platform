# 0025. The mesh node on its own VM, out of the worker's reach

Status: Accepted
Date: 2026-10-16

Supersedes one part of [0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md): which VM is the mesh node. The rest of 0020 stands.

## Context

[0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md) puts the mesh agent and Squid on one edge VM. The worker reaches Squid on that VM ([0011](0011-package-proxy-for-the-worker.md)). So a compromised agent has a chain to the operator's tailnet: a flaw in Squid, then root on the edge, then a node beside the operator's devices with open outbound TCP 443. The orchestrator has the same chain, through the same proxy.

The mesh is the part of the design the project controls least. The coordination service decides what each client is told: peers, keys, and the access policy that the clients enforce. Tailnet Lock keeps it from adding a node, and WireGuard keeps the relays from reading traffic. What is left, read on 2026-10-16:

- **The agent updates itself.** `tailscale debug prefs` on the orchestrator shows `AutoUpdate.Apply: true`, and the tailnet's default is on. The apt hold (`U.2`) stops `apt`, not the agent's own updater. A release from the vendor, or from whoever compromises the vendor's release path, would run as root on the router. `U.6`, a check added on the same day, failed on the live orchestrator: `expected: false`, `actual: true`.
- **The policy the clients enforce comes from the service.** A changed policy could let a platform node open connections to the operator's devices. The operator's devices only ever start connections.
- **The agent uploads its logs to the vendor.** An [open item](../security/accepted-risks.md#open-items).
- **The relays forward to any node key**, including one on another tailnet. 0020 states it.

Quota decides the shape. Denmark East allows 4 vCPUs, and 0020's edge uses 2.

## Options

| Option | A path from the worker to a tailnet node | Cost |
| --- | --- | --- |
| 0020 as it is: agent and Squid on the edge | Squid, then the edge | Nothing more |
| Mesh agent on the orchestrator, as before 0020 | The tool service, then the orchestrator, which holds every credential | 0020's reasons against it stand |
| A router VM that runs only the mesh agent, with no inbound rule from any subnet. The edge keeps Squid and the NAT gateway | None. No VM the worker or the orchestrator can reach is a tailnet node | One more small VM. Denmark East's quota is then full |
| An Azure point-to-site VPN gateway instead of the mesh | None, and no third party besides Azure | A gateway billed by the hour, and a new access design |
| WireGuard run by the project on the router VM | None, and no third party | A public address and inbound UDP on the router, an exception to the policy that refuses public addresses, and keys managed by hand |

## Decision

A router VM in Denmark East runs the mesh agent and nothing else. The edge keeps Squid and the NAT gateway, and leaves the tailnet.

**The router**

- `Standard_B2ats_v2` (2 vCPUs, 1 GB), the same image, zone 1. With the edge's `Standard_B2als_v2`, Denmark East is at 4 of 4 vCPUs.
- Its own subnet in the edge's virtual network: `10.45.0.32/27`, the VM at `10.45.0.36`. The NAT gateway serves both subnets.
- It joins under `tag:aisec-router`, signed with Tailnet Lock, and advertises `10.40.0.0/20`, `10.50.0.0/20`, and `10.45.0.0/27`, so the operator reaches the edge through it. `tag:aisec-edge` is not created.
- Agent settings, set at enrolment and checked: automatic update off (`U.6`), log upload off (`--no-logs-no-support`), and Tailscale SSH, the web client, Serve, and Funnel off. Its version moves only by a pin change, as today.

**Security groups**

| Group | Inbound | Outbound |
| --- | --- | --- |
| Router | Nothing. The tunnel is opened outbound | TCP 443 and 80 to the internet, for the coordination service, the relays, and its own packages. TCP 22 to the platform network, the target network, and the edge subnet, for routed sessions. TCP 443 to the private endpoint for monitoring ([0021](0021-monitoring-in-azure-monitor-over-private-link.md)) |
| Edge | TCP 3128 from the orchestrator and worker subnets. TCP 22 from the router subnet | As in 0020. No longer a tailnet node |
| Orchestrator, worker, targets | TCP 22 from the router subnet, where 0020 said the edge subnet | Unchanged |

No subnet has a rule that reaches the router. The worker reaches the edge's port 3128 and the orchestrator's port 30443, and neither is a tailnet node.

**The policy and the operator's devices**

- The access policy grants operator devices TCP 22 to the router's three routes, and nothing else. Its `tests` refuse a change that lets `tag:aisec-router` reach a member device.
- The operator's devices run with `shields-up`, which refuses every incoming connection whatever the policy says. It is a setting on each device, not on the platform. The runbook lists it, and no check can read it.

**Checks**

- `U.6` on the router, as on the orchestrator until it leaves the tailnet.
- A check reads the router's agent settings: log upload off, Tailscale SSH and the web client off.
- `Z` checks read the router's security group: no inbound allow.
- The `A` and `M` checks move to the router.

## Trade-offs

- **Denmark East is full.** A rebuild that needs a second VM there at the same time, or a larger edge, has no room.
- **Root on the router gets a tailnet node, open outbound TCP 443, and SSH reach to every network.** SSH still needs the operator's certificate ([0022](0022-short-lived-ssh-certificates-for-the-operator.md)), which holds no key on the router. Routed sessions pass through it as SSH ciphertext.
- **The router is the way in.** When it is down, administration goes through the Azure serial console (T03). Outbound fetches do not depend on it.
- **The vendor still runs the coordination service.** It can stop the mesh, see which devices talk to which, and change the policy the clients enforce. Turning off updates removes its code path onto the router. `shields-up` removes its path onto the operator's devices. Tailnet Lock removes its path to add a node.
- **Log upload off means no help from the vendor's support** when something breaks.
- **One more VM to patch and monitor.** It gets the same hardening, the log agent, and the heartbeat alert.
