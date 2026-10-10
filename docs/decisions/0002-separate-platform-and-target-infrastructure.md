# 0002. Separate platform and target infrastructure

Status: Accepted
Date: 2026-10-10

## Context

The platform investigates and changes a target service. The target carries intentional weaknesses and is rebuilt often. The platform holds credentials, policies, and workflow definitions that decide what may change.

If both live in the same Terraform configuration, network, or permission scope, then a remediation proposal, a compromised target, or an operator mistake in one can reach the other. The project also needs to show that the service under investigation is not the infrastructure doing the investigating.

## Options

| Option | Isolation | Cost and effort |
| --- | --- | --- |
| One Terraform root, one network, separate subnets | Weak. One state file, one identity, one blast radius | Lowest |
| Separate Terraform roots, state, resource groups, networks, and identities in one subscription | Strong against workload and tooling mistakes. Subscription administrators span both | Moderate. Peering and cross-root references to manage |
| Separate subscriptions or tenants | Strongest | Not available to this project |

## Decision

Separate the two at every layer the project controls.

| Layer | Rule |
| --- | --- |
| Terraform | Two roots, `infra/platform/` and `infra/targets/`. Neither reads the other's state |
| State | Separate state with separate access scopes |
| Resource groups | No resource group contains both platform and target resources |
| Network | Separate virtual networks in separate regions, joined by peering with default-deny rules |
| Identity | Separate deployment identities, each scoped to its own resource groups |
| Change scope | Remediation may change allowlisted target fields only |
| Containment | Rules that keep the lab private are owned outside the target's change scope |

Values one root needs from the other, such as address ranges and peering identifiers, are passed as explicit inputs, not read from the other root's state.

## Trade-offs

- **Shared subscription administration.** A subscription Owner can change both sides. The separation limits workloads and automation, not that role.
- **Peering spans both roots.** Each side of a peering is created by its own root, so the link needs two applies and an agreed input contract.
- **More to bootstrap.** Two state locations and two identities exist before the first resource.
- **Folder names prove nothing.** The separation is real only where permissions and network rules enforce it. The network foundation milestone tests that each identity cannot modify the other side.
