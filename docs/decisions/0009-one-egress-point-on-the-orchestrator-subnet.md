# 0009. One egress point, on the orchestrator subnet

Status: Accepted
Date: 2026-10-11

## Context

Every subnet is private. There is no default outbound access, and each security group ends in a deny-all outbound rule. That was the point of the network foundation, and it means nothing can download anything yet.

Compute needs packages, container images, and a model file of several gigabytes. The mesh VPN agent needs its coordination service ([0007](0007-mesh-vpn-for-administrative-access.md)). The machines do not need the same thing:

| Machine | Trust | Needs from the internet |
| --- | --- | --- |
| Orchestrator | Trusted | All the time: mesh VPN, image pulls, security feeds, GitHub |
| AI worker | Untrusted ([0005](0005-ai-workers-on-a-separate-vm.md)) | Packages, runtime binaries, and a model when it is built. Nothing while it runs jobs |
| NetBox and lab VMs | Untrusted, weak on purpose | Packages and container images at build and at each update |

The obvious move is one outbound path for every subnet, closed on the untrusted ones once they are built. That turns containment into a rule someone has to remember to put back. On the target side it is worse. The path would live in the target resource group, where the target identity can change it, and [0002](0002-separate-platform-and-target-infrastructure.md) says containment is not a target setting.

Three documented Azure behaviors decide what counts as closed. All three were read on 2026-10-11 and get tested with traffic in milestone 2.

- **A missing route is not containment.** A VM in a private subnet with no outbound method [still reaches Azure Storage accounts in its own region](https://learn.microsoft.com/azure/virtual-network/ip-services/default-outbound-access#limitations-of-private-subnets). Anyone can own a storage account there. The security group is the control, not the absence of a gateway.
- **Deny-all does not cover DNS.** Azure DNS at `168.63.129.16` [ignores security group rules](https://learn.microsoft.com/azure/virtual-network/what-is-ip-address-168-63-129-16) unless a rule names the `AzurePlatformDNS` service tag. A machine that can resolve public names can pass data to whoever runs the name server.
- **Security groups do not filter by hostname.** They match addresses, ports, and service tags. Limiting egress to named registries takes a firewall or a proxy.

## Options

The outbound path for the orchestrator. Prices are for Sweden Central, from the retail price API on 2026-10-11.

| Option | Public address on a VM | Cost | Notes |
| --- | --- | --- | --- |
| Public IP on the orchestrator's network interface | Yes | USD 0.005 per hour | Cheapest, and the mesh VPN gets direct connections. One security group is all that stands between the VM and the internet. A policy that forbids public addresses on network interfaces becomes impossible |
| NAT gateway on the orchestrator subnet | No | USD 0.045 per hour and USD 0.045 per GB, plus its public address. A Standard address is USD 0.005 per hour | Outbound only by construction. The mesh VPN falls back to relays |
| Standard load balancer with outbound rules | No | Hourly charge | The same result as a NAT gateway from more parts, around a load balancer that balances nothing |
| Azure Firewall, Basic | No | USD 0.395 per hour, USD 0.065 per GB | The only option that filters by hostname. Costs about as much as all four VMs together |

How the untrusted machines get their software.

| Option | Standing path to the internet | Notes |
| --- | --- | --- |
| Share the NAT gateway, close the rule after the build | None while closed | Containment depends on closing it every time. On the target side the gateway belongs to the target root |
| Allowlisting forward proxy on the orchestrator | Yes, to the allowed hosts | One more service on a 2-vCPU machine. The worker gains a second destination, and package and model hosts accept uploads as well as downloads |
| Pull-through registry and package mirror on the orchestrator | Yes, through the mirror | The untrusted side chooses what the trusted side fetches |
| The orchestrator downloads, verifies, and pushes | None | The untrusted machines never download anything. Provisioning has to run from the orchestrator, and package updates need their own mechanism |

## Decision

One way out for the whole system: a NAT gateway on the orchestrator subnet. Every other machine is fed.

**The orchestrator**

- The platform root creates a StandardV2 NAT gateway with one static public address and associates it with the orchestrator subnet. No other subnet gets an outbound method.
- The orchestrator's security group allows outbound to the `Internet` tag on TCP 443 and 80, plus the UDP the mesh agent uses to attempt direct connections. Hostnames are not filtered.

**The worker and the targets**

- No outbound method, and explicit deny rules for the `Internet` and `AzurePlatformDNS` tags. On the worker subnet these are platform-side containment rules, next to the existing denies.
- The orchestrator downloads each artifact, checks it against a pinned digest or checksum, and copies it over SSH. That flow is already allowed. Container images travel as archives.
- Operating system packages go through a SOCKS forward carried by an SSH session from the orchestrator. The path exists only while that session is open, and only the trusted side can open it. For the worker, [0011](0011-package-proxy-for-the-worker.md) replaced this on 2026-10-11 with a package proxy on the orchestrator.
- These machines know each other by address and a hosts file. There is no private DNS zone.

**Policy**

The bootstrap root assigns two Azure Policy definitions. Neither deployment identity can change a policy assignment.

- Both workload resource groups: deny a public address on any network interface.
- The target resource group: deny public IP addresses and public IP prefixes as resource types. Without an address there is no NAT gateway, no outbound load balancer rule, and no firewall. The target side having no egress stops being something the target root could undo.

This closes the gap recorded in [0008](0008-deployment-identities-and-bootstrap-scope.md): an identity could create a public address in its own group and nothing outside the root stopped it.

## Trade-offs

- **The gateway bills by the hour whether or not a VM runs.** Parking the lab means removing the gateway and its address, then applying again before the orchestrator starts. Without it the orchestrator has no mesh VPN, and without the mesh VPN there is no way in.
- **Mesh VPN connections are relayed.** Tailscale [documents Azure NAT Gateway as a hard NAT](https://tailscale.com/docs/reference/reference-architectures/azure) that prevents direct connections. Shells and the Argo interface go through a relay and are slower for it. Downloads do not cross the mesh. The fix is a public address on the VM, which is what this decision refuses.
- **The orchestrator can reach any host on port 443.** A compromise of it is not slowed by egress rules. It already holds every credential that matters, and filtering by hostname costs a firewall.
- **Feeding is slower.** Every artifact is fetched once and copied again. The fed machines cannot install packages from cloud-init, so their setup runs from the orchestrator after boot. The orchestrator's disk holds the model and the image archives. Copies to the targets cross regions at USD 0.035 per GB.
- **The orchestrator is the supply chain.** What it pushes is what runs. The digest check there is the only check.
- **The SOCKS forward is a real internet path while it is open.** Anything already running on that machine can use it. Package maintenance happens when no job is running and before a target is seeded. Otherwise the machine gets rebuilt.
- **No DNS on the fed machines will break something.** Software that expects to resolve a name at startup fails until it is given an address. Milestone 2 finds out what.
- **Platform endpoints stay reachable from every VM.** The instance metadata service and the host agent endpoint are not the internet, but metadata returns a VM's custom data. No secret goes into custom data on a fed machine.
- **The target-side deny rules are still target settings.** They live in the target root, and exercise 2 edits target network rules. The policy and the missing gateway hold whatever those rules say. The denies for same-region storage and for Azure DNS do not.
