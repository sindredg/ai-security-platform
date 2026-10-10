# 0006. Terraform state in Azure Storage, one account per root

Status: Accepted
Date: 2026-10-10

## Context

Terraform state is the least glamorous sensitive file in the project. It can hold secrets in plain text, it describes everything that exists, and losing it turns every later change into archaeology.

Three things have to be true. The platform and target roots must not share state ([0002](0002-separate-platform-and-target-infrastructure.md)). State must stay out of the repository and away from workloads. And it must survive the loss of the workstation that runs Terraform.

## Options

| Option | Separation | Durability | Cost and effort |
| --- | --- | --- | --- |
| Local state files, ignored by Git | By file only. Whoever has the workstation has both | Gone with the workstation | None |
| One storage account, one container per root | Container-level role assignments. One account-level role or key exposes both | Durable | Low |
| One storage account per root | Account-level boundary. Independent access, network rules, and deletion | Durable | Slightly more to bootstrap |
| Hosted Terraform service | Workspace-level | Durable | Puts another external service in the trust boundary |

## Decision

Store state in Azure Blob Storage with the `azurerm` backend, one storage account per root.

- Each account sits in its own resource group, apart from what its root manages. Destroying a root does not destroy its state.
- Access uses Microsoft Entra authentication and data-plane role assignments. Shared key access is disabled.
- Each root's deployment identity can read and write its own state and no other.
- Blob versioning and soft delete are on, so a bad write can be undone.
- Backend settings that name real resources are passed to `terraform init` from a local file that is not committed. The repository carries an example with placeholders.

A small bootstrap configuration creates the two state accounts. Its own state is local and not committed. It manages only those two accounts, and they can be imported again if that file is lost.

[0008](0008-deployment-identities-and-bootstrap-scope.md) later widened the bootstrap root to the resource groups, deployment identities, and role assignments as well.

## Trade-offs

- **There is a bootstrap step outside the two roots.** A root cannot create the storage its own state lives in.
- **The bootstrap state is local.** Losing it loses no project state, but costs an import.
- **A subscription administrator can read both accounts.** The separation constrains deployment identities and workloads, not that role.
- **State still contains sensitive values.** Access control is what protects it. Secrets stay out of Terraform wherever a managed alternative exists.
- **Storage is metered.** State files are tiny, so the cost is operations and versions, not volume.
