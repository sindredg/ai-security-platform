# 0046. A signed tag from a separate key approves a commit, and delivery checks the target before the merge

Status: Accepted
Date: 2026-10-26

The delivery token is made for each delivery: [0047](0047-a-delivery-token-for-each-delivery.md).

## Context

Milestone 5's criteria: delivery applies only the approved commit to the approved target, and a changed commit voids the approval. After delivery the consumer still gets its records, forbidden records stay hidden, and writes stay denied. One rollback is shown, with what it cannot repair ([roadmap](../roadmap.md#5-remediation-pull-requests-and-delivery)).

What is fixed already:

- **A commit's signature shows where it was made, not who approved it.** The coding agent on the operator's machine signs with the operator's key ([0024](0024-the-targets-in-their-own-repository-and-signed-commits.md)).
- **GitHub's merge is not an approval the platform can verify.** Whoever holds the GitHub session merges, and the squash commit is signed by GitHub.
- **The platform holds no repository credential,** and the operator's machine publishes each fix ([0045](0045-the-operator-publishes-a-checked-proposal.md)).
- **Root commands on the orchestrator host reach NetBox,** as the collect command does ([0040](0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)).

## Options

**What an approval is**

| Option | What it binds | What it costs |
| --- | --- | --- |
| The pull request's merge | Whatever the merge produced | Anyone with the GitHub session approves, the coding agent included |
| A signed tag on the commit, from a key only the operator uses | One commit and, in its message, one target. Verified offline against a pinned key | A second key, and one command per approval |
| A hardware key touched for each approval | The same, with proof of presence | Hardware the project does not have |

**When the merge happens**

| Option | What `main` holds | What it costs |
| --- | --- | --- |
| Merge, then deliver | A state that may never have worked on the target | A failed delivery leaves `main` wrong |
| Approve the pull request's head, deliver, check, then merge | Only states that passed the checks after delivery | The pull request stays open until delivery |

## Decision

**An approval is a signed Git tag on the approved commit, pushed to the targets repository.** The tag's message names the target, and it is signed with a separate SSH approval key, protected by a passphrase, which only the operator uses and which is never added to the agent the coding agent signs with.

The key's public half is pinned on the orchestrator, and published in the targets repository so that anyone can verify a tag. Delivery reads only the pinned copy.

**An approval is used once, within 24 hours.** Delivery keeps a ledger of the tag objects it has used, and refuses a tag older than 24 hours or dated in the future.

**The order is approve, deliver, check, merge.** `main` only ever holds a state that passed the checks after delivery. A rollback delivers `main`'s head again, with its own approval.

**Delivery is a root command on the orchestrator host.** It fetches the targets repository during a fetch window, verifies the tag, and chooses a mode:

- **Fix:** the commit's only parent is `main`'s head, it changes only the seed, and the change removes at least one user from a permission and adds none.
- **Restore:** the commit is `main`'s head.
- Anything else is refused before NetBox is touched.

**Before a fix, delivery checks for drift.** When NetBox's permission assignments differ from `main`'s seed, it refuses and prints the difference.

Delivery writes the ledger line before it applies, reads the assignments back, and runs both checks against the commit's contract. A fix passes only when every contract account is within by both checks.

**A delivery account does the writing.** It can view users and groups, and view and change permission assignments, with a write token limited to the orchestrator's address and readable by root only.

**A failed check after delivery stops for the operator.** There is no automatic rollback. A fix's pull request is merged only after the checks after its delivery pass.

## Trade-offs

- **The approval key lives on the operator's machine.** Whoever holds it and its passphrase approves, within the 24 hours of each tag. The workstation is out of scope.
- **The delivery account can change any permission.** The command limits what it changes, not NetBox.
- **A rollback cannot take back what was read.** What the consumer read while exposed, and anything it copied, stays read.
- **A restore needs an approval too.** Rolling back waits for the operator, like a fix.
- **Not seen when this was written:** a tag verified on the orchestrator, a delivery, and a restore.
