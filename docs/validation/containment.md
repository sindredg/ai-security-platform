# Containment

The AI worker runs untrusted model output. It gets no path to the internet, to the targets, or to a name server, and one port on the orchestrator. The design is [ADR 0005](../decisions/0005-ai-workers-on-a-separate-vm.md) and [ADR 0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md). The threat is T17: the worker reaches a target or the internet directly.

## From the worker

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `C.1` | No connection to the internet | A turned worker cannot call out or fetch a payload | TCP to `1.1.1.1:443` has to fail |
| `C.2`, `C.3` | No connection to the target network | The worker investigates through tool services, never directly | TCP to an address in two target subnets has to fail |
| `C.4` | No connection to the platform resolver | DNS is a way to pass data out, and a deny-all rule does not cover it | TCP to `168.63.129.16:53` has to fail |
| `C.5` | A public name does not resolve | The same, tested end to end | `getent hosts example.com` has to fail |
| `C.6` | No connection to the orchestrator on 22 | The worker never administers the trusted side | TCP has to fail |
| `C.7`, `C.8` | No connection to the Kubernetes API or the kubelet | The cluster holds the credentials the worker must not have | TCP to 6443 and 10250 has to fail |
| `C.9` | The worker does not forward packets | It is not a router for anything behind it | `net.ipv4.ip_forward` is `0` |

## From Azure's side

A timeout proves a packet did not arrive. It does not say which rule stopped it, and the target network has no machines yet. These checks name the rule.

| ID | Claim | How it is checked |
| --- | --- | --- |
| `Z.4`, `Z.5` | The effective rules on each network interface equal the configured rules | `az network nic list-effective-nsg` against `az network nsg show`. The platform's own IPv6 deny is the one difference allowed |
| `Z.6` | Worker to the target network is denied by `deny-to-targets` | IP flow verify |
| `Z.7` | Worker to the internet is denied by `deny-to-internet` | IP flow verify |
| `Z.8` | Worker to the proxy is allowed by `allow-package-proxy-to-orchestrator` | IP flow verify |
| `Z.9` | Worker to the Kubernetes API is denied by `deny-all-outbound` | IP flow verify |

## The orchestrator's side

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `E.1` | The orchestrator reaches the internet on 443 | It is the one machine that downloads | TCP to `1.1.1.1:443` |
| `E.2` | The orchestrator reaches the worker on 22 | Feeding and administration | TCP to the worker |
| `E.3` | The orchestrator does not reach the worker on 80 | The allow is one port, not the subnet | TCP has to fail |
| `E.4` | The feed key logs in to the worker | The feed path works end to end | An SSH login from the orchestrator with the feed key |
| `R.1` | The mesh VPN agent is active | The subnet router is the way in | `systemctl is-active` |
| `R.2` | The segment size clamp is loaded | Without it, connections through the router stall. See [troubleshooting 02](../troubleshooting/02-ssh-through-subnet-router-stalls.md) | Two rules in the `aisec_mss` table |
| `R.3` | The orchestrator forwards packets | It routes for the mesh | `net.ipv4.ip_forward` is `1` |

## Not checked

- The orchestrator can reach any host on 443. That is an accepted risk, not a claim.
- Platform endpoints such as the instance metadata service stay reachable from every VM.
