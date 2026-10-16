# 0020. An edge VM for the way out and the mesh, and the targets to Poland Central

Status: Proposed
Date: 2026-10-16

Supersedes parts of four records. From [0009](0009-one-egress-point-on-the-orchestrator-subnet.md): where the one way out sits. From [0007](0007-mesh-vpn-for-administrative-access.md): which machine is the subnet router. From [0011](0011-package-proxy-for-the-worker.md): which machine runs the package proxy. From [0003](0003-region-pair.md): the target region. The rest of each record stands.

## Context

The orchestrator holds every credential that matters. It is also the one way out ([0009](0009-one-egress-point-on-the-orchestrator-subnet.md)) and the mesh VPN node beside the operator's devices ([0007](0007-mesh-vpn-for-administrative-access.md)). Root on the orchestrator gets all three at once:

- **Any host on TCP 443 and 80** (T05). Its security group allows the `Internet` tag on both ports, and nothing filters by hostname.
- **Public DNS** (T07). The worker and the targets deny the `AzurePlatformDNS` tag. The orchestrator does not, so it can carry data out in the names it looks up.
- **A node on the operator's tailnet**, in the same kernel as the secrets. The access policy grants the orchestrator's tag nothing, so it cannot open a connection to an operator device today. That rests on one console setting, and no check covers that direction.

Every control that runs on the orchestrator itself fails against root there. An nftables output rule, a local proxy, a tailnet policy the agent enforces: root removes or bypasses each of them. The control has to sit outside the orchestrator's kernel.

A hostname allowlist is not the fix it looks like. What the orchestrator fetches, read from the code and the cluster on 2026-10-16:

| What | Hosts | From |
| --- | --- | --- |
| Operating system packages | `azure.archive.ubuntu.com`, port 80 | `/etc/apt/sources.list.d/` on the orchestrator |
| K3s and its install script | `github.com`, `raw.githubusercontent.com` | `infra/platform/cloud-init/orchestrator.yaml.tftpl` |
| Cluster system images | `docker.io` (`rancher/local-path-provisioner`, `mirrored-coredns-coredns`, `mirrored-metrics-server`, `mirrored-pause`) | `k3s crictl images` |
| The tool service image | `ghcr.io` | `platform/tool-service/tool-service.yaml` |
| Model and agent inputs | `huggingface.co`, `files.pythonhosted.org`, `download.pytorch.org`, `github.com` | `worker/model-server/artifacts.tsv`, `worker/agent-runtime/artifacts.tsv` |
| Mesh agent packages | `pkgs.tailscale.com` | The orchestrator's cloud-init |

GitHub, Docker Hub, Hugging Face, and PyPI accept uploads from anyone with an account. A standing allowlist with those names on it lets a compromised orchestrator push data to the attacker's own repository through an allowed name. [0009](0009-one-egress-point-on-the-orchestrator-subnet.md) said the same about the worker. Nothing on the orchestrator needs any of them while it runs. They are needed when something is built or deployed.

Placement is bounded by quota. The subscription allows 4 vCPUs per region, and its type is not eligible for an increase ([Azure limits](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#how-to-manage-limits)). Sweden Central has 4 of 4 in use. The other candidates, read on 2026-10-16 with `az vm list-skus --all` and `az vm list-usage`:

| Region | vCPUs in use | Usable B-series sizes with 2 vCPUs or fewer | Zones for them |
| --- | --- | --- | --- |
| Norway East | 0 of 4 | None. 793 of 865 sizes are restricted, as in 0003 | Not applicable |
| Denmark East | 0 of 4 | B v1 and B v2, from `B2ats_v2` (1 GB) to `B2as_v2` (8 GB) | 1, 2, 3 |
| Poland Central | 0 of 4 | B v2 only | 3 only |

Denmark East is the target region today. It holds an empty target network: one virtual network, four security groups, and the target root's state account. No target VM exists.

## Options

Where the outbound filter lives.

| Option | Holds against root on the orchestrator | Filters by hostname | Cost |
| --- | --- | --- | --- |
| nftables output rules and a local proxy on the orchestrator | No | Yes | Nothing new |
| Azure Firewall, Basic | Yes | Yes | USD 0.395 per hour ([0009](0009-one-egress-point-on-the-orchestrator-subnet.md)), more than all the VMs together |
| Security group rules opened by an apply for each fetch, no proxy | Yes | No. A window opens every host | No new VM. The mesh agent needs TCP 443 all the time, so it has to move anyway |
| An edge VM with the NAT gateway, the mesh agent, and Squid. The orchestrator's security group allows only the proxy | Yes | Yes | One small VM to run and patch |

What the orchestrator may fetch through the edge.

| Option | Upload path to an attacker's account | Cost |
| --- | --- | --- |
| A standing allowlist | Always open, through every allowed upload host | Nothing to operate |
| The edge downloads, verifies, and pushes each artifact | None | A second copy of every fetch script, on the edge |
| A small standing list with no upload host, plus a fetch window the operator opens on the edge for a build or a deploy | Open only during a window, which closes itself | One command to run before a fetch |

Where the edge runs.

| Option | Problem |
| --- | --- |
| Sweden Central | No quota left, and no way to raise it |
| Norway East | No small size is usable |
| Poland Central | One zone. The edge carries all administration and all outbound traffic, and a zone without capacity leaves no fallback in the region |
| Denmark East, with the targets moved to Poland Central | Three zones. The targets tolerate one zone better: they are rebuilt, not patched, and nothing reaches the platform through them |

Routing the orchestrator's and the worker's traffic through the edge as a gateway, with a route table, was considered and rejected. Their security groups deny the internet at the source, before any route applies, so a packet that breaks the rules never reaches the edge. Flow logs record those denials where they happen. The route table would add forwarding and asymmetric-routing faults for no new signal.

## Decision

An edge VM in Denmark East takes the way out, the mesh VPN node, and the package proxy. The orchestrator keeps the secrets and loses all three. The targets move to Poland Central.

**The edge**

- `Standard_B2als_v2` (2 vCPUs, 4 GB), zone 1, from the same Ubuntu image as the other VMs. 4 GB until the footprint of the mesh agent, Squid, and a log agent is measured. The smaller sizes are an option after that.
- Its own virtual network, `10.45.0.0/24`, with one subnet, `10.45.0.0/27`, and the VM at `10.45.0.4`. It belongs to the platform root and the platform resource group. Resource group location does not bind resource location, and the policy assignments are per resource group, so 0002's separation holds.
- Peerings: platform to edge, and edge to targets. Platform to targets stays, for the orchestrator's collectors. Peering is not transitive, so each pair has its own.
- The NAT gateway and its public address move from the orchestrator subnet to the edge subnet. No other subnet has an outbound method.
- It runs the mesh agent, Squid, and nothing else. No K3s, no workloads, no job credential.

**The mesh**

- The edge joins with a single-use tagged auth key, as the orchestrator did, under a new tag, `tag:aisec-edge`. It is signed with Tailnet Lock and advertises `10.40.0.0/20` and `10.50.0.0/20`. The agent's version is held, and its automatic update is turned off at enrolment to match the hold.
- The orchestrator leaves the tailnet. Its agent is removed, and the node is deleted in the console.
- The access policy grants operator devices TCP 22 to the edge and to the two routed networks. TCP 6443 is no longer granted: the Kubernetes API is reached through an SSH tunnel to the orchestrator.
- The policy gets `tests` that refuse a change that lets either platform tag reach an operator device.

**Squid on the edge**

Listens on `10.45.0.4:3128`. The worker's rules are 0011's, unchanged. The orchestrator gets two lists:

- **Standing:** `GET` and `HEAD` on port 80 to the Ubuntu mirrors the orchestrator uses, so its unattended upgrades keep working. No `CONNECT`, no upload host.
- **During a fetch window:** `CONNECT` on port 443 to the build and deploy hosts in the table above. The exact list, including the hosts those names redirect to, is read from Squid's log on the first window and written into the edge's configuration then.

The window is a root-owned command on the edge, run by the operator over SSH. It opens the second list for at most 60 minutes and closes it with a timer. Every open and close, and every request, is logged on the edge. Root on the orchestrator cannot open it.

Squid resolves names for its clients. Nothing on the orchestrator needs to resolve a public name.

**Security groups**

| Group | Change |
| --- | --- |
| Orchestrator | Outbound: the `Internet` allows go, and `AzurePlatformDNS` is denied, as on the worker. TCP 3128 to the edge is allowed. TCP 22 to the worker and the targets stays. Inbound: TCP 22 from the edge subnet replaces the mesh traffic that arrived through the tunnel. TCP 6443 is not allowed from the edge |
| Worker | TCP 3128 goes to the edge instead of the orchestrator. TCP 22 inbound from the orchestrator subnet stays, and from the edge subnet is added for the operator |
| Edge | Inbound: TCP 3128 from the orchestrator and worker subnets. Nothing for administration: the tunnel is opened outbound. Outbound: TCP 443 and 80 to the internet, through the NAT gateway. TCP 22 to the platform and target networks, for routed operator sessions |
| Targets | The rules move with the network to Poland Central. TCP 22 is allowed from the edge subnet as well as the orchestrator subnet |

**The targets**

The target root gets a `location` variable, set to Poland Central. It rebuilds the empty target network there, at the same `10.50.0.0/20`. The planned NetBox and lab VMs are `Standard_B2as_v2` in zone 3, 4 of the region's 4 vCPUs. The target root's state account stays in Denmark East. Where state is stored has no effect on where resources run.

**Checks**

The existing checks move with what they check: `A`, `M`, `P`, and `U.3` to the edge, `Z` to the new rules. New ones:

- The orchestrator opens no connection to `1.1.1.1:443` and gets no answer from `168.63.129.16:53`. Both time out.
- Squid refuses a `CONNECT` to `github.com` from the orchestrator when no window is open, and allows it during one. The window closes itself. This is a procedure step, because opening a window changes state and `platform-checks.sh` only reads.
- The edge's agent has automatic update off and the held version.
- The mesh policy's tests are in place, read from the console. A check cannot read them from the repository.

## Trade-offs

- **The edge is a single point of failure** for administration and for every outbound fetch. When it is down, the way in is the Azure serial console (T03), and the orchestrator cannot update its packages.
- **Root on the edge gets the tailnet node and open TCP 443.** It holds no credential that reaches the cluster, the jobs, or the audit log. It sees routed operator sessions as SSH ciphertext. The policy grants its tag nothing toward operator devices, and the policy tests guard that.
- **The mesh relays are a way out from the edge.** A relay forwards to any node key connected to it, including a node on another tailnet. Moving the agent off the orchestrator takes this channel away from the machine with the secrets. It does not close it.
- **During a window the upload hosts are open.** A compromised orchestrator can push data to an account of its own on GitHub, Docker Hub, Hugging Face, or PyPI while a window lasts. The window is short, logged, and opened only by the operator.
- **Builds and deploys need an extra step.** A rebuilt orchestrator, a K3s upgrade, a new image digest, and a model build each need a window first. A pod restart does not: its image is already on the node.
- **Squid sees the host name and the bytes, not the content.** TLS is not inspected. A client can still reach other tenants on an allowed CDN address.
- **Traffic crosses regions.** Every fetch crosses the Sweden Central to Denmark East peering, metered at USD 0.035 per GB in each direction ([0003](0003-region-pair.md)). A model build is a few gigabytes. Routed sessions gain the latency between the regions.
- **The targets have one zone.** If zone 3 in Poland Central has no capacity on the day, they cannot be built there. 0003's fallback, Poland Central for Denmark East, is spent.
- **One more VM to patch.** The edge is the most exposed machine in the design and gets the same hardening and checks as the other two.
- **Prices for Denmark East are not in the retail price API**, as 0003 found. In Sweden Central `Standard_B2als_v2` is listed at USD 0.0389 per hour on 2026-10-16. The size gets priced again before it is built.
- **The name cutover is untested.** Anything on the orchestrator that resolves a public name without the proxy fails after the change. Reading the code found nothing that does. The first apply is the test.
