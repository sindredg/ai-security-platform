# Egress and policy

One outbound path for the whole system: a NAT gateway on the orchestrator subnet. Every other machine has three controls that block outbound access, because any one control alone leaves a path open.

| | |
| --- | --- |
| State | Built |
| NAT gateway | StandardV2, one static public address, associated with `snet-orchestrator` only |
| Defined in | `infra/platform/egress.tf`, the rules in `infra/platform/main.tf` and `infra/targets/`, the policy in `infra/bootstrap/policy.tf` |
| Decisions | [0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md), [0008](../decisions/0008-deployment-identities-and-bootstrap-scope.md) |

## The three controls on the worker and target machines

| Control | What it stops | What it does not |
| --- | --- | --- |
| No outbound method on the subnet | Ordinary internet access | A private subnet still reaches storage accounts in its own region |
| Explicit deny rules for `Internet` and `AzurePlatformDNS` | The storage path, and name resolution | Nothing, if they stay in place. They are in the root that the side's own identity can change |
| Azure Policy, assigned from the bootstrap root | A public address on any network interface, and any public IP resource on the target side | Neither deployment identity can change it |

## Rules on the platform side

![Network flows: the operator reaches the orchestrator on ports 22 and 6443, the orchestrator reaches the worker and the targets on port 22 and the internet through one NAT gateway, the worker reaches only ports 3128 and 30443 on the orchestrator, and everything else is denied](../diagrams/network-flows.svg)

The diagram source is [`diagrams/network-flows.html`](../diagrams/network-flows.html). The table below names the rule behind each path.

| Security group | Direction | Access | What | Rule |
| --- | --- | --- | --- | --- |
| Orchestrator | Inbound | Deny | Anything from the target network | `deny-from-targets` |
| Orchestrator | Inbound | Allow | TCP 3128 from the worker subnet | `allow-package-proxy-from-worker` |
| Orchestrator | Inbound | Allow | TCP 30443 from the worker subnet, the tool service's node port | `allow-tool-service-from-worker` |
| Orchestrator | Outbound | Allow | TCP 22 to the worker subnet and the target network | `allow-ssh-to-worker`, `allow-ssh-to-targets` |
| Orchestrator | Outbound | Allow | TCP 443 and 80 to the internet. Port 80 also carries the mesh agent's control connection | `allow-https-to-internet`, `allow-http-to-internet` |
| Worker | Inbound | Deny | Anything from the target network | `deny-from-targets` |
| Worker | Inbound | Allow | TCP 22 from the orchestrator subnet | `allow-ssh-from-orchestrator` |
| Worker | Outbound | Deny | The target network, the internet, Azure DNS | `deny-to-targets`, `deny-to-internet`, `deny-to-azure-dns` |
| Worker | Outbound | Allow | TCP 3128 and 30443 to the orchestrator subnet | `allow-package-proxy-to-orchestrator`, `allow-tool-service-to-orchestrator` |
| Both | Both | Deny | Everything else | `deny-all-inbound`, `deny-all-outbound` |

The table is read from `infra/platform/main.tf`. The rules for port 30443, and the removal of the mesh agent's UDP rules in [ADR 0017](../decisions/0017-no-udp-from-the-orchestrator.md), were applied on 2026-10-15. `Z.13` and `E.5` check them.

The orchestrator has no inbound allow for administration. That arrives inside the mesh VPN tunnel, which the orchestrator opens outbound.

## Validation

`C`, `E`, and `Z` in the [validation pages](../validation/containment.md).

## Limits

- **The gateway bills by the hour whether or not a VM runs.**
- **The orchestrator's egress is not filtered by hostname.** That takes a firewall that costs more than the VMs.
- **Port 80 is open as well as 443.** Only the package mirrors need it. Closing it was tried and failed. See [troubleshooting 03](../troubleshooting/03-proxy-cannot-fetch-upstream-over-tls.md).
- **Platform endpoints are not the internet and stay reachable.**

## Official documentation

- [Azure NAT Gateway](https://learn.microsoft.com/azure/nat-gateway/nat-overview)
- [Network security groups](https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview)
- [Default outbound access](https://learn.microsoft.com/azure/virtual-network/ip-services/default-outbound-access)
- [What is IP address 168.63.129.16](https://learn.microsoft.com/azure/virtual-network/what-is-ip-address-168-63-129-16)
- [Azure Policy](https://learn.microsoft.com/azure/governance/policy/overview)
- [IP flow verify](https://learn.microsoft.com/azure/network-watcher/ip-flow-verify-overview)
