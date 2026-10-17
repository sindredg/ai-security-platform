# Deployment identities and state

Two sides, two identities, two state stores. The platform identity cannot change the target side, and the other way round. A third root, run by the operator, creates both and assigns what neither may change.

| | |
| --- | --- |
| State | Built |
| Roots | `infra/bootstrap` (operator, local state), `infra/platform`, and `infra/targets` in the [targets repository](https://github.com/sindredg/ai-security-platform-test) |
| Identities | One app registration per side, signed in by certificate |
| State | One storage account per side. Shared keys off, access by role |
| Decisions | [0002](../decisions/0002-separate-platform-and-target-infrastructure.md), [0006](../decisions/0006-terraform-state-in-azure-storage.md), [0008](../decisions/0008-deployment-identities-and-bootstrap-scope.md) |

## What each identity holds

![Two sides, two identities: the bootstrap root creates each side, each identity holds roles on its own resource group and state, and the only cross-side permission is the peering action](../diagrams/separation.svg)

The diagram source is [`diagrams/separation.html`](../diagrams/separation.html).

| Identity | Role | Scope |
| --- | --- | --- |
| Platform | Contributor | Its own resource group |
| Platform | Storage Blob Data Contributor | Its own state account |
| Platform | A custom role with one action, peering | The target resource group |
| Targets | The same three, mirrored | |

Neither can create a resource group, assign a role, read the other side's network, or change a policy assignment.

## Validation

Tested by role in [milestone 1](../worklogs/0001-network-foundation.md#identity-separation): eight denied operations per identity. The checks in `validation/` run as the operator and do not repeat this.

## Limits

- **The deployment keys have no passphrase.** The operator's machine is out of scope.
- **The bootstrap state is a local file with a hand-made copy.** The copy sits in a `bootstrap` container in the platform state account and is uploaded after each apply. Nothing checks that it is current.
- **State accounts accept connections from any network.** Access needs a token with a data role.

## Official documentation

- [Terraform `azurerm` backend](https://developer.hashicorp.com/terraform/language/backend/azurerm)
- [Terraform `azurerm` provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Azure Policy](https://learn.microsoft.com/azure/governance/policy/overview)
