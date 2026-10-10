# 0006. Terraform state in Azure Storage, one account per root

Status: Accepted
Date: 2026-10-10

## Context

The platform and target roots must not share state ([0002](0002-separate-platform-and-target-infrastructure.md)). State can contain sensitive values, so it must stay out of the repository and out of reach of workloads. It also has to survive the loss of the workstation that runs Terraform.

## Options

| Option | Separation | Durability | Cost and effort |
| --- | --- | --- | --- |
| Local state files, ignored by Git | By file only. Whoever has the workstation has both | Lost with the workstation | None |
| One storage account, one container per root | Container-level role assignments. One account-level role or key exposes both | Durable | Low |
| One storage account per root | Account-level boundary. Independent access, network rules, and deletion | Durable | Slightly more to bootstrap |
| Hosted Terraform service | Workspace-level | Durable | Adds an external service to the trust boundary |

## Decision

Store state in Azure Blob Storage with the `azurerm` backend, one storage account per root.

- Each account lives in its own resource group, separate from the resources its root manages. Destroying a root does not destroy its state.
- Access uses Microsoft Entra authentication and data-plane role assignments. Shared key access is disabled.
- Each root's deployment identity can read and write its own state only.
- Blob versioning and soft delete are enabled so that a bad write can be recovered.
- Backend settings that name real resources are supplied at `terraform init` from a local file that is not committed. The repository carries an example with placeholders.

A small bootstrap configuration creates the two state accounts. Its own state is local and not committed. It manages only those accounts, and they can be imported again if that file is lost.

## Trade-offs

- **A bootstrap step exists outside the two roots.** State storage cannot be created by the root that stores its state in it.
- **The bootstrap state is local.** Losing it does not lose project state, but it costs an import to manage the accounts again.
- **A subscription administrator can read both accounts.** The separation limits deployment identities and workloads, not that role.
- **State still contains sensitive values.** Access control protects it. Secrets are kept out of Terraform where a managed alternative exists.
- **Storage is metered.** State files are small, so the cost is dominated by the minimum charges for operations and versions, not by volume.
