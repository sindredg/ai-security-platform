# 0004. NetBox as the first target, three ordered exercises

Status: Accepted
Date: 2026-10-10

## Context

The usual lab target is a VM with an old package and an open port. It is easy to seed and nearly impossible to fix wrongly, which makes it a poor test. If nothing depends on the service, then closing the port, removing the package, or turning the machine off all count as success.

A useful target has someone relying on it. Then a fix can be wrong in the way real fixes are wrong: the finding goes away and so does the service.

The target also has to run in 2 vCPUs, hold no real data, and offer more than one kind of finding, so the workflow gets exercised on different change surfaces.

## Options

| Option | Strength | Weakness |
| --- | --- | --- |
| A VM with an outdated package and an open port | Simple to seed | No dependent consumer. Fixes are hard to get wrong |
| A Git hosting service | Realistic, has an API | Too close to a service already used in earlier work |
| NetBox with a dependent API consumer | Inventory that automation relies on, object-level permissions, a REST API, a containerized deployment with a database | Heavier than one package. Upgrades involve database migrations |
| Three different targets (Linux VM, Container Apps, Windows client) | Broad coverage | Three adapters before one workflow is proven |

## Decision

Use NetBox with synthetic inventory and one legitimate API consumer. Run three exercises in this order, each on the same service, consumer contract, and workflow:

1. **Excess inventory access.** The consumer's permissions expose records outside its approved scope.
2. **Excess network access.** NetBox is reachable from a network viewpoint that policy forbids.
3. **Vulnerable image or dependency.** A pinned artifact is affected by a real public advisory.

Finish the first one completely, delivery and verification included, before starting the second.

The rules for all three:

- The consumer contract defines whether the service still works. A health check does not.
- A change that cuts off the legitimate consumer fails.
- NetBox is evidence, never authority. The platform's target registry and policy do not depend on anything NetBox returns.
- Each exercise needs a fixture that is affected and one that is not.

Other target types wait until this workflow is proven.

## Trade-offs

- **One target type.** This shows the workflow on a containerized service on a VM. It says nothing about managed platforms or workstations.
- **Exercise 1 does not need AI.** A deterministic check finds the violation by itself. The project compares the AI-assisted result with a baseline that uses no AI, and reports whichever way it comes out.
- **Exercise 3 depends on finding the right artifact.** If no affected and fixed pair with clear applicability exists for the pinned stack, the exercise is recorded as not done.
- **Permission state lives in the application.** Terraform does not own NetBox permission objects. Exercise 1 needs its own source of truth and reconciliation procedure.
- **Rollback is not an image downgrade.** NetBox upgrades can migrate the database. Recovery means a tested backup and restore on the rehearsal copy.
