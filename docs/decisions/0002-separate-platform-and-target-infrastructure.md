# 0002. Separate platform and target infrastructure

Status: Accepted
Date: 2026-10-10

## Context

The platform investigates a target and changes it. The target is weak on purpose and gets torn down and rebuilt all the time. The platform holds the credentials, policies, and workflow definitions that decide what is allowed to change.

Those two things should not be able to hurt each other. In one Terraform configuration, one network, or one permission scope, they can: a bad remediation proposal, a compromised target, or a tired operator in one can reach the other.

There is also a credibility problem. A platform that "investigates" infrastructure it also owns and deploys is marking its own homework.

## Options

| Option | Isolation | Cost and effort |
| --- | --- | --- |
| One Terraform root, one network, separate subnets | Weak. One state file, one identity, one blast radius | Lowest |
| Separate Terraform roots, state, resource groups, networks, and identities in one subscription | Strong against workload and tooling mistakes. Subscription administrators still span both | Moderate. Peering and cross-root inputs to manage |
| Separate subscriptions or tenants | Strongest | Not available to this project |

## Decision

Separate the two at every layer the project controls.

| Layer | Rule |
| --- | --- |
| Terraform | Two roots, `infra/platform/` and `infra/targets/`. Neither reads the other's state |
| State | Separate state with separate access scopes |
| Resource groups | No resource group holds both platform and target resources |
| Network | Separate virtual networks in separate regions, joined by peering with default-deny rules |
| Identity | Separate deployment identities, each scoped to its own resource groups |
| Change scope | Remediation may change allowlisted target fields only |
| Containment | The rules that keep the lab private sit outside the target's change scope |

When one root needs a value from the other, such as an address range or a peering identifier, it gets it as an explicit input. It does not read the other root's state.

## Trade-offs

- **A subscription Owner can still change both sides.** The separation constrains workloads and automation, not that role.
- **Peering straddles the boundary.** Each side of a peering belongs to its own root, so the link takes two applies and an agreed set of inputs.
- **More to bootstrap.** Two state locations and two identities have to exist before the first real resource.
- **Folder names prove nothing.** The separation is only as real as the permissions and network rules behind it. The network foundation milestone tests that each identity cannot modify the other side.
