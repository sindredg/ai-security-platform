# Containment

The AI worker runs untrusted model output. It gets no path to the internet, to the targets, or to a name server, and two ports on the orchestrator: the package proxy and the tool service. The design is [ADR 0005](../decisions/0005-ai-workers-on-a-separate-vm.md) and [ADR 0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md). The threat is T17: the worker reaches a target or the internet directly.

![Network flows: the operator reaches the router on port 22, the router reaches the orchestrator, the worker, and the targets on port 22, the orchestrator and the worker reach the edge VM's proxy on port 3128 and nothing on the internet, the edge and the router leave through the one NAT gateway, the worker also reaches the tool service on port 30443, the orchestrator reaches the worker and the targets on port 22, and everything else is denied](../diagrams/network-flows.svg)

The diagram source is [`diagrams/network-flows.html`](../diagrams/network-flows.html). It shows what is enforced today. The [target architecture](../architecture.md#system-overview) shows what is planned on top of it.

## What a failed connection proves

The script reports how each connection attempt ended, not just that it failed.

| Result | What happened | What it proves |
| --- | --- | --- |
| `open` | The handshake completed | The path is open |
| `refused` | A reset came back | The packet reached a host with no listener. Nothing on the path blocked it |
| `timeout` | Nothing came back | Something on the path dropped the packet |
| `unreachable` | No route, or a router said so | A routing fault, not a rule |

Network security groups and the mesh policy drop without answering. So a check that says a rule blocks a path expects `timeout`. `refused` on that path is a failure: the packet got through.

A timeout proves a drop only when something listens at the far end. That holds for every check below except `C.2` and `C.3`.

## From the worker

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `C.1` | No connection to the internet | A compromised worker cannot connect out or download a payload | TCP to `1.1.1.1:443` times out |
| `C.2`, `C.3` | No connection to the target network | The worker investigates through tool services, never directly | TCP to an address in two target subnets times out. No machine is there yet, so this would time out without the rule too. `Z.6` is the proof until targets exist |
| `C.4` | No connection to the platform resolver | DNS is a way to pass data out, and a deny-all rule does not cover it | TCP to `168.63.129.16:53` times out |
| `C.5` | A public name does not resolve | The same, tested end to end | `getent hosts example.com` has to fail |
| `C.6` | No connection to the orchestrator on 22 | The worker never administers the trusted side | TCP times out. The port listens: `E.2` and `M.1` reach it |
| `C.7`, `C.8` | No connection to the Kubernetes API or the kubelet | The cluster holds the credentials the worker must not have | TCP to 6443 and 10250 times out. Both ports listen on the orchestrator |
| `C.9` | The worker does not forward packets | It is not a router for anything behind it | `net.ipv4.ip_forward` is `0` |
| `C.10` | No answer from the platform resolver over UDP | `C.4` is TCP, and resolvers answer mostly over UDP | `dig @168.63.129.16` gets no reply (exit 9). The same query from the edge gets an answer, so the silence is the rule |

## From Azure's side

A timeout proves a packet was dropped. It does not say which rule dropped it, and the target network has no machines yet. These checks name the rule.

| ID | Claim | How it is checked |
| --- | --- | --- |
| `Z.4`, `Z.5`, `Z.16`, `Z.20` | The effective rules on each network interface, the orchestrator's, the worker's, the router's, and the edge's, equal the configured rules | `az network nic list-effective-nsg` against `az network nsg show`, compared rule by rule. See below |
| `Z.6` | Worker to the target network is denied by `deny-to-targets` | IP flow verify |
| `Z.7` | Worker to the internet is denied by `deny-to-internet` | IP flow verify |
| `Z.8` | Worker to the proxy on the edge is allowed by `allow-package-proxy-to-edge` | IP flow verify |
| `Z.9` | Worker to the Kubernetes API is denied by `deny-all-outbound` | IP flow verify |
| `Z.13` | Worker to the tool port is allowed by `allow-tool-service-to-orchestrator` | IP flow verify. See [tool service](tool-service.md) |
| `Z.14` | The target network is in Poland Central | The network's location, not the group's: the group stays in Denmark East ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)) |
| `Z.15` | Both halves of the peering are connected | `peeringState` of each half. A rebuilt network leaves the other half `Disconnected` ([troubleshooting 06](../troubleshooting/06-rebuilt-network-leaves-peering-disconnected.md)) |
| `Z.17` | Nothing is allowed into the router | Inbound allow rules among the router's effective rules, counted once `Z.16` got an answer. `0`. Its tunnel is opened outbound, so no subnet needs a way in ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md)) |
| `Z.18` | Both halves of the platform and edge peering are connected | As `Z.15` |
| `Z.24` | Both halves of the edge and target peering are connected | As `Z.15`. The router's sessions to the targets cross it |
| `Z.25` | Only SSH from the orchestrator and the router is allowed into each target subnet | The configured inbound allows of each target group, by name, source, and port. Not the effective rules: those need a network interface, and no target VM exists |
| `Z.19` | The edge network is in Denmark East | The network's location. The group is in Sweden Central |
| `Z.21` | Only the proxy port and SSH from the router are allowed into the edge | The inbound allow rules among the edge's effective rules, by name and port, counted once `Z.20` got an answer: `allow-proxy-from-orchestrator` and `allow-proxy-from-worker` on 3128, `allow-ssh-from-router` on 22 |
| `Z.22` | Orchestrator to the internet is denied by `deny-to-internet` | IP flow verify from the orchestrator. Before 2026-10-17 it named `allow-https-to-internet` |
| `Z.23` | Orchestrator to the proxy on the edge is allowed by `allow-proxy-to-edge` | IP flow verify from the orchestrator |

### What `Z.4` and `Z.5` compare

Each rule is compared on direction, priority, access, name, protocol, source and destination addresses, and source and destination ports. A rule that keeps its name and changes its port fails the check, and the output shows the two versions.

The two commands write the same rule differently, so both are put in one form first:

| Field | Configured | Effective | Compared as |
| --- | --- | --- | --- |
| Any protocol | `*` | `All` | `*` |
| Any address | `*` | `0.0.0.0/0`, sometimes with `::/0` | `*` |
| One port | `22` | `22-22` | `22-22` |
| Any port | `*` | `0-65535` | `0-65535` |
| Lists | One value or a list | Both filled | One sorted list |

Two differences are allowed. Azure's default rules appear in every effective list and are skipped. The platform adds one IPv6 deny through its network manager, and that one rule from that one source is skipped. A second security group on the interface is not skipped and fails the check.

A failed or empty answer from Azure is a `FAIL` with the error. Two empty answers used to compare as equal and pass.

Limit: service tags such as `Internet` are compared by name. The addresses a tag expands to are not checked, and that stays a limit. Azure owns the expansion and changes it without a change here, so a check on it would fail on Azure's schedule and say nothing about this configuration. What a tag rule claims is the tag, and that is what `Z.4` and `Z.5` compare. The traffic checks (`C.*`, `E.*`) show what the tags block in practice.

## The orchestrator's side

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `E.2` | The orchestrator reaches the worker on 22 | Copying files to the worker, and administration | TCP to the worker |
| `E.3` | The worker's rules drop the orchestrator on 80 | The allow is one port, not the subnet | TCP times out. Nothing listens on that port, so `refused` would mean the rules let the packet in |
| `E.4` | The feed key runs nothing but the feed command | The key lives on the trusted machine. On the worker it gets an account with no sudo and one command ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)) | `id` with the key, from the orchestrator, ends with exit status `2`, the command refusing. `255` is SSH failing, and `0` a key that ran the command |
| `E.5` | The router sends no UDP to the internet | [ADR 0017](../decisions/0017-no-udp-from-the-orchestrator.md) keeps the mesh agent off UDP. The router's rules have none | `tailscale netcheck` on the router reports `UDP: false`. Until the router, this read the orchestrator |
| `E.6` | Forwarded traffic from pods goes only to pods | A new pod has no network policy for its first seconds, and CoreDNS forwards names to Azure DNS. [ADR 0018](../decisions/0018-a-host-rule-keeps-pods-off-the-internet.md) | The `forward` chain of the `aisec_pod_egress` table, as `nft` lists it with the counter values removed, equals the three rules in the cloud-init file |
| `E.7` | The pod egress rule loads at boot | Without it, a reboot brings the gap back | `systemctl is-enabled aisec-pod-egress` is `enabled` |
| `E.8` | Pods reach the host only on the API server and kubelet ports | Traffic from a pod to the host's own addresses skips the `forward` chain. Without this, any pod reaches SSH and every port opened later. [ADR 0023](../decisions/0023-the-host-rule-limits-what-pods-reach-on-the-host.md) | The `input` chain of the same table, as `nft` lists it with the counter values removed, equals the three rules in the cloud-init file |
| `E.9` | The feed key is restricted to the orchestrator and the feed command | `from=`, `restrict`, and the forced command are the whole limit on the key | One line in `/home/aisec-feed/.ssh/authorized_keys`, owned by root with mode `644`, with exactly those options |
| `E.10` | The feed account has no other group, no sudo, and not its own home | A group or sudo would undo the rest. A home it owns lets it write the files its shell reads at login | `id -nG`, `sudo -l -U`, and the owner of `/home/aisec-feed` |
| `E.11` | The worker runs the feed command in this checkout | The command is the boundary on the worker. It has to be the reviewed one | The SHA-256 of `/usr/local/sbin/aisec-feed-receive` equals that of `worker/feed/aisec-feed-receive` |
| `E.12` | The orchestrator opens no connection to the internet | It holds every credential. Its way out is Squid on the edge, and nothing else (T05) | TCP to `1.1.1.1:443` times out. Before 2026-10-17 it was `open` |
| `E.13`, `E.14` | The orchestrator gets no answer from Azure DNS | Squid resolves names for it. A resolver is a way to pass data out (T07) | TCP to `168.63.129.16:53` times out, and a `dig` query over UDP gets no reply |

`E.1` read the opposite of `E.12`, that the orchestrator reaches the internet on 443. It was retired on 2026-10-17, when that stopped being true.

## Not checked

- The orchestrator can reach any host on TCP 443 and 80. This access is an [accepted risk](../security/accepted-risks.md#accepted-risks); these checks do not test it.
- Platform endpoints such as the instance metadata service stay reachable from every VM.
