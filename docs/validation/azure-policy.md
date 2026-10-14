# Azure policy

No machine in this project has a public address, and a policy outside both deployment identities refuses one. The design is [ADR 0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md) and [ADR 0008](../decisions/0008-deployment-identities-and-bootstrap-scope.md).

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `Z.1` | No VM has a public address | Inbound from the internet has nowhere to land | `az vm list -d` |
| `Z.2` | The platform group holds one public address | The NAT gateway's. A second one is something nobody decided | `az network public-ip list` |
| `Z.3` | The target group holds no public address | Without an address the target side has no egress at all | `az network public-ip list` |
| `Z.10` | A public address on a network interface is refused in the platform group | Each identity is Contributor on its own group. The policy is what stops it | A template with such an interface is validated, and Azure answers `RequestDisallowedByPolicy` |
| `Z.11` | The same in the target group | The target identity cannot create its own outbound path | The same |
| `Z.12` | The policy check left nothing behind | Validation deploys nothing, and this proves it | `az resource list` |

## Limits of these checks

- They run as the operator. That the deployment identities cannot change a policy assignment was tested in [milestone 1](../worklogs/0001-network-foundation.md#identity-separation), by role, not here.
- The policy that refuses public IP resources on the target side is implied by `Z.3` and `Z.11`. It is not validated by itself.
