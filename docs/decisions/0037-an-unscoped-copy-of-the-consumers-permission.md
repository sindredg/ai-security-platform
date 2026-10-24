# 0037. The seeded finding is an unscoped copy of the consumer's permission, confirmed by configuration and by what the token returns

Status: Proposed
Date: 2026-10-24

## Context

Exercise 1 is excess inventory access: the consumer's permissions expose records outside its approved scope ([ADR 0004](0004-netbox-as-first-target.md)). Milestone 4 asks for a consumer contract, and for deterministic checks that confirm the finding and a known unaffected case ([roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation)).

How NetBox grants access ([permissions](https://github.com/netbox-community/netbox/blob/v4.7.3/docs/administration/permissions.md), [REST API](https://github.com/netbox-community/netbox/blob/v4.7.3/docs/integrations/rest-api.md)):

- A permission names object types, users or groups, actions, and optional constraints, a Django query filter. A permission without constraints applies to every object of its types. A user's permissions add up: one unscoped permission undoes every scoped one for the same type and action.
- Permissions are per object, not per field. A user who may view a record sees all of its fields.
- API tokens can be read-only, can expire, and can be limited to client addresses.

The mistake to seed should look like one an administrator makes. An extra object type shows in the permission's own list. An unscoped duplicate of a correct permission does not: each permission looks reasonable alone, and the excess is in the sum.

## Options

| Option | What the finding is | What it costs |
| --- | --- | --- |
| An unscoped copy of the consumer's permission | The same types and action, no constraint, so the consumer sees every tenant's records | Detecting it needs the sum of the permissions and a read of what the token returns |
| Extra object types | The consumer can also view types its contract does not list | Easy to see in one permission. Less like a real scoping mistake |
| Both, as separate cases | More held-out cases for scoring | Twice the fixtures and seeds, inside a short milestone |

## Decision

The unscoped copy.

1. **The contract is one tenant's records.** The consumer may read the devices and IP addresses of one synthetic tenant, through a read-only token limited to the consumer viewpoint's address. The contract itself, with its endpoints, fields, record IDs, and expected denials, is a file in the [targets repository](https://github.com/sindredg/ai-security-platform-test) beside the seed. It changes there, with what the running target shows, without a new decision record.
2. **The seeded finding** is a second permission on the consumer with the same types and action and no constraint. Nothing else differs.
3. **The unaffected case** is a control account with the same contract and the scoped permission only. Both accounts exist on every seed, so each check run sees one affected and one unaffected case.
4. **The finding needs two deterministic checks to agree.**
   - **Configured.** The collector reads every permission that applies to each account, directly or through a group, adds them up per type and action, and compares the sum with the contract.
   - **Observed.** From the consumer viewpoint, each account's token reads the contract's endpoints, and the record IDs it gets back are compared with the contract's. An extra record confirms the excess. A missing one means the contract is broken.

   When the two disagree, the disagreement is the result, and neither wins (T23).
5. **The seed is the expected state.** The collector compares what NetBox reports with the seed in the repository, not with NetBox's own earlier answers.
6. **The collector reads permissions, and writes nothing.** Its token is read-only, limited to the orchestrator's address, with `view` on the inventory types and on users, groups, and permissions. Seeding uses a separate write-enabled token, also limited to the orchestrator.

No collector in exercise 1 reads from Azure, so cloud identity for cluster workloads stays open under [0013](0013-a-token-per-job-and-no-cloud-identity-yet.md).

## Trade-offs

- **One finding shape.** The scored cases vary the inventory and the constraint, not the kind of mistake. A model that learns to look for an unscoped permission is not tested on an extra type.
- **Fields are not a boundary.** The finding is about records. A contract that needs to hide a field cannot be met with NetBox's permissions, and this one does not try.
- **The control account is a fixture, not a consumer.** Nothing depends on it. It exists so that every run has an unaffected case.
- **The collector's token maps who can see what.** That makes it worth more than the consumer's. It stays on the orchestrator, with the other credentials that matter ([credentials](../security/credentials.md)).
