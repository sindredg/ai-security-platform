# Containment

The AI worker runs untrusted model output. It gets no path to the internet, to the targets, or to a name server, and one port on the orchestrator. The design is [ADR 0005](../decisions/0005-ai-workers-on-a-separate-vm.md) and [ADR 0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md). The threat is T17: the worker reaches a target or the internet directly.

![Network flows: the operator reaches the orchestrator on ports 22 and 6443, the orchestrator reaches the worker and the targets on port 22 and the internet through one NAT gateway, the worker reaches only port 3128 on the orchestrator, and everything else is denied](../diagrams/network-flows.svg)

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
| `C.1` | No connection to the internet | A turned worker cannot call out or fetch a payload | TCP to `1.1.1.1:443` times out |
| `C.2`, `C.3` | No connection to the target network | The worker investigates through tool services, never directly | TCP to an address in two target subnets times out. No machine is there yet, so this would time out without the rule too. `Z.6` is the proof until targets exist |
| `C.4` | No connection to the platform resolver | DNS is a way to pass data out, and a deny-all rule does not cover it | TCP to `168.63.129.16:53` times out |
| `C.5` | A public name does not resolve | The same, tested end to end | `getent hosts example.com` has to fail |
| `C.6` | No connection to the orchestrator on 22 | The worker never administers the trusted side | TCP times out. The port listens: `E.2` and `M.1` reach it |
| `C.7`, `C.8` | No connection to the Kubernetes API or the kubelet | The cluster holds the credentials the worker must not have | TCP to 6443 and 10250 times out. Both ports listen on the orchestrator |
| `C.9` | The worker does not forward packets | It is not a router for anything behind it | `net.ipv4.ip_forward` is `0` |

## From Azure's side

A timeout proves a packet was dropped. It does not say which rule dropped it, and the target network has no machines yet. These checks name the rule.

| ID | Claim | How it is checked |
| --- | --- | --- |
| `Z.4`, `Z.5` | The effective rules on each network interface equal the configured rules | `az network nic list-effective-nsg` against `az network nsg show`, compared rule by rule. See below |
| `Z.6` | Worker to the target network is denied by `deny-to-targets` | IP flow verify |
| `Z.7` | Worker to the internet is denied by `deny-to-internet` | IP flow verify |
| `Z.8` | Worker to the proxy is allowed by `allow-package-proxy-to-orchestrator` | IP flow verify |
| `Z.9` | Worker to the Kubernetes API is denied by `deny-all-outbound` | IP flow verify |

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

Limit: service tags such as `Internet` are compared by name. The addresses a tag expands to are not checked.

## The orchestrator's side

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `E.1` | The orchestrator reaches the internet on 443 | It is the one machine that downloads | TCP to `1.1.1.1:443` |
| `E.2` | The orchestrator reaches the worker on 22 | Feeding and administration | TCP to the worker |
| `E.3` | The worker's rules drop the orchestrator on 80 | The allow is one port, not the subnet | TCP times out. Nothing listens on that port, so `refused` would mean the rules let the packet in |
| `E.4` | The feed key logs in to the worker | The feed path works end to end | An SSH login from the orchestrator with the feed key |
| `R.1` | The mesh VPN agent is active | The subnet router is the way in | `systemctl is-active` |
| `R.2` | The segment size clamp is loaded | Without it, connections through the router stall. See [troubleshooting 02](../troubleshooting/02-ssh-through-subnet-router-stalls.md) | Two rules in the `aisec_mss` table |
| `R.3` | The orchestrator forwards packets | It routes for the mesh | `net.ipv4.ip_forward` is `1` |

## Not checked

- The orchestrator can reach any host on 443. That is an accepted risk, not a claim.
- Platform endpoints such as the instance metadata service stay reachable from every VM.
