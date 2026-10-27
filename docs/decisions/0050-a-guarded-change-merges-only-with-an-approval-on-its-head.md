# 0050. A change to the seed or the approvers merges only with an approval on its head commit

Status: Accepted
Date: 2026-10-27

## Context

The order is approve, deliver, check, merge, so that `main` only holds a state that passed the checks after delivery ([0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md)). Delivery applies only the tagged commit.

What is fixed already:

- **Nothing tied the merge to the approval.** A commit pushed to the pull request after its approval could still be merged. Delivery never applied it, and the next fix's drift check finds a difference in users lists only.
- **Whoever holds the GitHub session merges,** the coding agent included ([0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md)). The approval key's public half is in the targets repository's `APPROVERS`, and the orchestrator pins its own copy.
- **The targets repository's signature check runs from the default branch,** with `pull_request_target`, and reads the pull request's commits as data ([0024](0024-the-targets-in-their-own-repository-and-signed-commits.md)).

## Options

| Option | What a merge needs | What it costs |
| --- | --- | --- |
| The operator's attention | Nothing the repository checks | A changed head merges if nobody looks |
| A required check that the head is approved | An approval tag on the head commit, signed with a key in `main`'s `APPROVERS` | Shows an approval, not a delivery. One more run after approving |
| A required check that the head was delivered | A delivery result the repository can read | The platform holds no repository credential ([0045](0045-the-operator-publishes-a-checked-proposal.md)), so the operator would publish the result |

## Decision

**A required check, "Approved commit", guards NetBox's seed, `APPROVERS`, and the check itself.** A pull request that changes one of them passes only when its head commit carries an approval: a tag `approve/netbox/NAME` on that commit, signed with a key in the default branch's `APPROVERS`, whose message starts with `target: netbox`. A pull request that changes none of them passes.

**It runs as the signature check does.** The workflow, the script, and `APPROVERS` come from the default branch, and the pull request's commits and the approval tags are fetched as data. Nothing from the pull request runs.

**Pushing a tag does not start the check.** The operator runs it again after approving.

## Trade-offs

- **It shows an approval, not a delivery.** Delivering and checking before the merge stay the operator's steps.
- **It reads `main`'s `APPROVERS`, not the orchestrator's copy.** A new key in `APPROVERS` needs an approval by the key it replaces, and delivery still reads only the pinned copy.
- **The ruleset is a repository setting.** Whoever administers the repository can take the check out of it.
- **Not seen when this was written:** the check on GitHub, with a pull request and a tag.
