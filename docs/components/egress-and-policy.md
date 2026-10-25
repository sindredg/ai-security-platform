# Egress and policy

One outbound path for the whole system: a NAT gateway on the edge network, used by the router and the edge VM. The orchestrator and the worker reach the internet only through Squid on the edge. Every machine without the gateway has three controls that block outbound access, because any one control alone leaves a path open.

| | |
| --- | --- |
| State | Built. Verified by `E`, `C`, and `Z` on 2026-10-17 ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-edge-vm)) |
| NAT gateway | StandardV2 in Denmark East, one static public address, associated with `snet-router` and `snet-edge` only |
| Defined in | `infra/platform/edge.tf`, the rules in `infra/platform/main.tf`, `infra/platform/edge.tf`, and `infra/targets/` of the [targets repository](https://github.com/sindredg/ai-security-platform-test), the policy in `infra/bootstrap/policy.tf` |
| Decisions | [0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md), [0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md), [0025](../decisions/0025-the-mesh-node-on-its-own-vm.md), [0008](../decisions/0008-deployment-identities-and-bootstrap-scope.md) |

## The three controls on the orchestrator, the worker, and the targets

| Control | What it stops | What it does not |
| --- | --- | --- |
| No outbound method on the subnet | Ordinary internet access | A private subnet still reaches storage accounts in its own region |
| Explicit deny rules for `Internet` and `AzurePlatformDNS` | The storage path, and name resolution | Nothing, if they stay in place. They are in the root that the side's own identity can change |
| Azure Policy, assigned from the bootstrap root | A public address on any network interface, and any public IP resource on the target side | Neither deployment identity can change it |

## Rules on the platform side

![Network flows: the operator reaches the router on port 22, the router reaches the orchestrator, the worker, and the targets on port 22, the orchestrator and the worker reach the edge VM's proxy on port 3128 and nothing on the internet, the orchestrator also reaches port 3129 on the edge for the targets' packages, the edge and the router leave through the one NAT gateway, the worker also reaches the tool service on port 30443, the orchestrator reaches the worker and the targets on port 22 and NetBox on port 8443, and everything else drawn is denied. The orchestrator, the worker, and the targets have no DNS. Not drawn: the log agents' port 443 to the monitoring private endpoint, the router's port 22 to the edge VM, and the consumer subnet's port 8443 to NetBox](../diagrams/network-flows.svg)

The diagram source is [`diagrams/network-flows.html`](../diagrams/network-flows.html). The table below names the rule behind each path. NetBox's port, TCP 8443 from the orchestrator and from the consumer subnet, is in the tables and not in the diagram.

| Security group | Direction | Access | What | Rule |
| --- | --- | --- | --- | --- |
| Orchestrator | Inbound | Deny | Anything from the target network | `deny-from-targets` |
| Orchestrator | Inbound | Allow | TCP 22 from the router subnet | `allow-ssh-from-router` |
| Orchestrator | Inbound | Allow | TCP 30443 from the worker subnet, the tool service's node port | `allow-tool-service-from-worker` |
| Orchestrator | Outbound | Deny | The internet, Azure DNS | `deny-to-internet`, `deny-to-azure-dns` |
| Orchestrator | Outbound | Allow | TCP 22 to the worker subnet and the target network | `allow-ssh-to-worker`, `allow-ssh-to-targets` |
| Orchestrator | Outbound | Allow | TCP 3128 to the edge subnet | `allow-proxy-to-edge` |
| Orchestrator | Outbound | Allow | TCP 3129 from the orchestrator's address to the edge subnet, the targets' packages | `allow-target-packages-to-edge` |
| Orchestrator | Outbound | Allow | TCP 8443 from the orchestrator's address to the NetBox VM, NetBox's API ([ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)) | `allow-netbox-to-targets` |
| Orchestrator | Outbound | Allow | TCP 443 to the monitoring subnet, the log agent | `allow-monitoring-private-endpoint` |
| Worker | Inbound | Deny | Anything from the target network | `deny-from-targets` |
| Worker | Inbound | Allow | TCP 22 from the orchestrator subnet and the router subnet | `allow-ssh-from-orchestrator`, `allow-ssh-from-router` |
| Worker | Outbound | Deny | The target network, the internet, Azure DNS | `deny-to-targets`, `deny-to-internet`, `deny-to-azure-dns` |
| Worker | Outbound | Allow | TCP 3128 to the edge subnet | `allow-package-proxy-to-edge` |
| Worker | Outbound | Allow | TCP 30443 to the orchestrator subnet | `allow-tool-service-to-orchestrator` |
| Router | Outbound | Allow | TCP 443 and 80 to the internet, through the edge network's NAT gateway | `allow-https-to-internet`, `allow-http-to-internet` |
| Router | Outbound | Allow | TCP 22 to the platform network, the target network, and the edge subnet | `allow-ssh-to-platform`, `allow-ssh-to-targets`, `allow-ssh-to-edge` |
| Router | Outbound | Allow | TCP 443 to the monitoring subnet, the log agent | `allow-monitoring-private-endpoint` |
| Router | Inbound | Allow | Nothing | |
| Edge | Inbound | Deny | Anything from the target network | `deny-from-targets` |
| Edge | Inbound | Allow | TCP 3128 from the orchestrator subnet and the worker subnet | `allow-proxy-from-orchestrator`, `allow-proxy-from-worker` |
| Edge | Inbound | Allow | TCP 3129 from the orchestrator's address, the targets' packages | `allow-target-packages-from-orchestrator` |
| Edge | Inbound | Allow | TCP 22 from the router subnet | `allow-ssh-from-router` |
| Edge | Outbound | Allow | TCP 443 and 80 to the internet, through the NAT gateway. Azure DNS is not denied: Squid resolves names | `allow-https-to-internet`, `allow-http-to-internet` |
| Edge | Outbound | Allow | TCP 443 to the monitoring subnet, the log agent | `allow-monitoring-private-endpoint` |
| Monitoring | Inbound | Deny | Anything from the target network | `deny-from-targets` |
| Monitoring | Inbound | Allow | TCP 443 from the orchestrator subnet, the edge subnet, and the router subnet, to the private endpoint | `allow-agents-from-orchestrator`, `allow-agents-from-edge`, `allow-agents-from-router` |
| All five | Both | Deny | Everything else | `deny-all-inbound`, `deny-all-outbound` |

The table is read from `infra/platform/main.tf` and `infra/platform/edge.tf` on 2026-10-24. `Z.4`, `Z.5`, `Z.16`, and `Z.20` compare the effective rules on each VM's interface with its group's configured ones. The monitoring group protects a private endpoint, not a VM, and no check compares its rules ([#178](https://github.com/sindredg/ai-security-platform/issues/178)). `Z.21` counts what is allowed into the edge, and `Z.22` and `Z.23` test the orchestrator's paths.

Administration arrives from the router subnet, translated to the router's address. The router has no inbound allow: its mesh tunnel is opened outbound (`Z.17`).

## Rules on the target side

Each of the four target subnets has its own security group. All four have the same base rules, and a service's port is added to the subnets that use it. They are defined in `infra/targets/main.tf` of the [targets repository](https://github.com/sindredg/ai-security-platform-test).

| Direction | Access | What | Rule |
| --- | --- | --- | --- |
| Inbound | Allow | TCP 22 from the orchestrator subnet and the router subnet | `allow-ssh-from-orchestrator`, `allow-ssh-from-router` |
| Inbound, NetBox subnet only | Allow | TCP 8443 to the NetBox VM, from the orchestrator's address and the consumer subnet | `allow-netbox-from-orchestrator`, `allow-netbox-from-consumer` |
| Outbound, consumer subnet only | Allow | TCP 8443 to the NetBox VM | `allow-netbox-to-netbox` |
| Outbound | Deny | The internet, Azure DNS | `deny-to-internet`, `deny-to-azure-dns` |
| Both | Deny | Everything else | `deny-all-inbound`, `deny-all-outbound` |

The table is read from that file on 2026-10-24, with NetBox's port. `Z.25` reads each group's inbound allows. `Z.27` and `Z.28` compare the effective rules on the NetBox VM's and the lab VM's interfaces with their groups, since 2026-10-24. The unintended and rehearsal subnets have no VM, so their effective rules are not read.

## Validation

`C`, `E`, and `Z` in the [validation pages](../validation/containment.md). What the targets cannot reach is `VN.13` to `VN.17` and `VL.13` to `VL.17` on [targets](../validation/targets.md).

## Limits

- **The gateway bills by the hour whether or not a VM runs.**
- **The edge and the router reach any host on TCP 443 and 80.** The edge filters by hostname in Squid, not in its rules. The router's mesh service and relays change addresses without notice. Root on either has open outbound access (T38, T39).
- **Port 80 is open as well as 443 on the edge.** Only the package mirrors need it. Closing it was tried and failed. See [troubleshooting 03](../troubleshooting/03-proxy-cannot-fetch-upstream-over-tls.md).
- **The edge is a single point of failure** for every outbound fetch, and the router for every administrative session.
- **Platform endpoints are not the internet and stay reachable.**

## Official documentation

- [Azure NAT Gateway](https://learn.microsoft.com/azure/nat-gateway/nat-overview)
- [Network security groups](https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview)
- [Default outbound access](https://learn.microsoft.com/azure/virtual-network/ip-services/default-outbound-access)
- [What is IP address 168.63.129.16](https://learn.microsoft.com/azure/virtual-network/what-is-ip-address-168-63-129-16)
- [Azure Policy](https://learn.microsoft.com/azure/governance/policy/overview)
- [IP flow verify](https://learn.microsoft.com/azure/network-watcher/ip-flow-verify-overview)
