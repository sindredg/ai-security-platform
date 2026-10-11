# 0008. Certificate-based deployment identities, created by the bootstrap root

Status: Accepted
Date: 2026-10-10

## Context

Each Terraform root needs its own identity, scoped to its own side ([0002](0002-separate-platform-and-target-infrastructure.md)). Terraform runs on the operator's workstation for now, and the operator is a subscription Owner. Running both roots as that Owner would make the separation a folder convention.

Two things fall out of scoping an identity to a resource group:

- It cannot create that resource group, register resource providers, or assign roles. Something with more rights has to do that first.
- Peering needs a permission on the other side. Azure checks write access on the local network and the `peer/action` permission on the remote one.

## Options

For the identity:

| Option | Secret on disk | Works from a workstation | Notes |
| --- | --- | --- | --- |
| Operator's own sign-in for every root | None | Yes | No separation. One mistake reaches both sides |
| Service principal with a client secret | A password, which Terraform would also write into state | Yes | The easiest thing to leak |
| Service principal with a certificate | A private key, generated locally, never in Terraform or state | Yes | A key file to protect and rotate |
| Managed identity or workload identity federation | None | No. Needs an Azure-hosted runner or a CI issuer | The better answer once deployment moves off the workstation |

For the cross-side peering permission:

| Option | What the other side can do |
| --- | --- |
| Network Contributor on the remote network | Change it. Defeats the separation |
| Operator creates both peerings by hand | Nothing, but the link is no longer in either root |
| Custom role with only `Microsoft.Network/virtualNetworks/peer/action` | Name the remote network as a peering partner. No read, no write |

## Decision

One service principal per side, authenticated with a certificate.

- The operator generates each key pair locally. Only the public certificate goes to Microsoft Entra ID. The private key never enters Terraform, state, or the repository.
- Each identity gets Contributor on its own workload resource group and Storage Blob Data Contributor on its own state account. Nothing at subscription scope.
- Each identity also gets a custom role on the other side's workload resource group. The role has one action, `Microsoft.Network/virtualNetworks/peer/action`.
- The roots take subscription, tenant, client ID, and certificate from `ARM_*` environment variables. No ID is written to a tracked file.

The bootstrap root, run by the operator, owns everything a scoped identity cannot create for itself: resource provider registration is a manual step before it, and it creates the four resource groups, the two state accounts, the two identities, the custom role, and every role assignment. This widens the bootstrap scope set in [0006](0006-terraform-state-in-azure-storage.md), which had it manage only the state accounts.

## Trade-offs

- **Two private keys sit on the workstation.** File permissions protect them, nothing more. Whoever reads a key file is that deployment identity until the certificate is removed or expires.
- **Certificates expire.** The end date is set at bootstrap. Rotation is a new key pair and a bootstrap apply. Miss it and the root stops authenticating.
- **The boundary has one deliberate hole.** Each side can name the other's network as a peering partner. It cannot read or change it, and a one-sided peering carries no traffic.
- **Contributor on a resource group is broad.** An identity can create anything inside its own group, including a public IP address. Nothing outside the root stops that yet.
- **New role assignments need the operator.** A root that later needs a managed identity with a role has to get that assignment from the bootstrap root.
- **Losing the bootstrap state now costs more.** It holds the identities and assignments as well as the accounts. Everything in it can still be imported.
- **The operator still spans both sides.** As in 0002 and 0006, the separation constrains automation and workloads, not the Owner.
