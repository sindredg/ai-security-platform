# 0047. A delivery token for each delivery, not kept on the orchestrator

Status: Accepted
Date: 2026-10-27

Replaces the delivery token of [0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md). The rest of 0046 stands.

## Context

[0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md) gave the delivery account `aisec-deliver` a write token, kept on the orchestrator, readable by root only and limited to the orchestrator's address. It also said the account can change any permission.

A review of the targets change found what that means. View and change on permissions, with no constraint, covers every field of every permission, the account's own included. NetBox has no field-level permissions, and a constraint cannot stop an account adding itself to a permission it may change. So whoever holds the token can give the account any object type and action, or make a token for a superuser. This was read from NetBox's source, not tried.

What else holds:

- **Root on the orchestrator holds the platform's credentials** ([security index](../security/README.md#standing-weak-points)). Apart from the delivery token, the only one that writes to the live NetBox is the seed token, during a seed run. `make-netbox-token.sh` makes it on the NetBox VM, it expires after an hour, and the operator's session pipes it to the orchestrator ([NetBox runbook](../runbooks/netbox.md)).
- **A rehearsal needs a write token on the copy** at every proposal, with no operator present. A reset restores the copy from its dump ([0044](0044-the-rehearsal-copy-is-a-second-netbox-on-the-lab-vm.md)).

## Options

| Option | What a compromised orchestrator gets | What it costs |
| --- | --- | --- |
| A standing token, as 0046 has it | NetBox superuser reach, at any time | Nothing more |
| A constraint on the account's permissions | The same: the account can rewrite a permission it may change | A constraint to keep in step with the seed |
| A token made for each delivery on the NetBox VM, piped into the delivery | Write access while a delivery runs, for an hour at most | One more command in each delivery, from the operator's session |

## Decision

**Each delivery gets its own token.** `make-netbox-token.sh deliver` on the NetBox VM deletes the account's tokens and makes one: write-enabled, limited to the orchestrator's address, and expiring after an hour. The operator's session pipes it into the delivery command's standard input, as it pipes the seed token.

**The delivery command reads the token from standard input,** keeps it in memory, and never writes it to a file.

**No delivery token is kept on the orchestrator for the live NetBox.** The seed makes none on the live NetBox, and a seed run there deletes any the account has.

**The copy keeps a standing delivery token,** made by the copy's seed, because rehearsals run without the operator.

## Trade-offs

- **Within a delivery, the token reaches as far as before.** A compromised orchestrator holding it can rewrite any permission until it expires.
- **A delivery needs the operator's session on the NetBox VM.** The approval already needs the operator.
- **The copy's token can make itself a superuser of the copy.** The copy holds only the synthetic seed and is restored from its dump at each rehearsal.
- **Not seen when this was written:** a delivery with a token made this way.
