# 0004. NetBox as the first target, three ordered exercises

Status: Accepted
Date: 2026-10-10

## Context

The platform needs a target that is separate from its own infrastructure and realistic enough that a fix can be wrong in interesting ways. A target that only exposes a health endpoint lets a "fix" pass by breaking the service for its real users.

The target must run within 2 vCPUs, hold no real data, and support more than one kind of finding so the workflow is exercised on different change surfaces.

## Options

| Option | Strength | Weakness |
| --- | --- | --- |
| A VM with an outdated package and an open port | Simple to seed | No dependent consumer. Fixes are hard to get wrong |
| A Git hosting service | Realistic, has an API | Overlaps with existing work on that kind of service |
| NetBox with a dependent API consumer | Inventory that automation depends on, object-level permissions, a REST API, a containerized deployment with a database | Heavier than a single package. Upgrades involve database migrations |
| Three different targets (Linux VM, Container Apps, Windows client) | Broad coverage | Three adapters before one workflow is proven |

## Decision

Use NetBox with synthetic inventory and one legitimate API consumer. Run three exercises in this order, each reusing the same service, consumer contract, and workflow:

1. **Excess inventory access.** The consumer's permissions disclose records outside its approved scope.
2. **Excess network access.** NetBox is reachable from a network viewpoint that policy forbids.
3. **Vulnerable image or dependency.** A pinned artifact is affected by a real public advisory.

Complete the first exercise end to end, including delivery and verification, before starting the second.

Rules that apply to all three:

- The consumer contract, not a health check, defines whether the service still works.
- A change that removes the legitimate consumer's access fails validation.
- NetBox is evidence, never authority. The platform's own target registry and policy are independent of anything NetBox returns.
- Each exercise needs a known-affected fixture and a known-unaffected one.

Other target types are deferred until this workflow is proven.

## Trade-offs

- **One target type.** The result shows the workflow on a containerized service on a VM. It does not show coverage of managed platforms or workstations.
- **Exercise 1 can be solved without AI.** A deterministic check finds the violation. The project compares the AI-assisted result with a baseline that uses no AI and reports it honestly.
- **Exercise 3 depends on finding a suitable artifact.** If no affected and fixed pair with clear applicability exists for the pinned stack, the exercise is recorded as not done.
- **Permission state lives in the application.** Terraform does not own NetBox permission objects. A separate source of truth and reconciliation procedure is needed for exercise 1.
- **Rollback is not an image downgrade.** NetBox upgrades can migrate the database. Recovery is a tested backup and restore on the rehearsal copy.
