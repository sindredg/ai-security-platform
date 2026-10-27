# 0043. Proposals are remove-only, come in the same answer, and a policy check on the orchestrator decides

Status: Accepted
Date: 2026-10-26

## Context

Milestone 5 turns a finding into a fix. Its criteria: a proposal becomes a pull request with evidence, an investigation that stopped opens none, and a deliberately unsafe patch is rejected even when its functional tests pass ([roadmap](../roadmap.md#5-remediation-pull-requests-and-delivery)).

What is fixed already:

- **Exercise 1's finding is an extra permission.** The seed gives the consumer an unscoped copy of its own permission, and two checks call the account excess ([0037](0037-an-unscoped-copy-of-the-consumers-permission.md)).
- **The model's answer is untrusted text.** The workflow reads only verdict lines in an exact form, and anything but a match with the checks stops it ([0041](0041-the-workflow-compares-the-models-verdict-with-the-checks.md)).
- **Pods reach neither NetBox nor GitHub.** The collect command runs as root on the orchestrator host and keeps each job's collection there ([0040](0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)).

## Options

**Where a proposal comes from**

| Option | What it gives | What it costs |
| --- | --- | --- |
| The same answer, after the verdict lines | One job. The model proposes from the evidence it has just read | A longer answer, under the same 8 KiB limit |
| A second job, given the verdicts | A clean prompt for the fix | Twice the worker's time per finding, and a second answer to compare |
| No model: the fix the checks imply | Right by construction | The agent adds nothing to the fix |

**What a proposal may change**

| Option | What it gives | What it costs |
| --- | --- | --- |
| Remove one permission from one account | A change that can only narrow access, which a policy can prove from the collection | Cannot fix a permission that must be narrowed instead of removed |
| Any field of a permission | Fixes more kinds of finding | A constraint or an action edit can widen access, and the policy would have to model NetBox's rules |

**What decides whether a proposal goes on**

| Option | What it gives | What it costs |
| --- | --- | --- |
| A Python command on the orchestrator host, standard library only | Reads the job's collection where it is kept, with no new dependency. Tested with hostile cases | Custom code, as the tool service is |
| A policy engine, such as Open Policy Agent | A policy language made for this | A new tool and language to pin, review, and run |
| A step in the workflow | Runs with the job | Needs the collection and its verdicts in the cluster, which pods may not reach |

## Decision

**A proposal comes in the same answer, after the verdict lines, and removes one permission from one account.** For each account the model calls excess, it ends with one proposal line: the account, the action `remove`, the ID of a permission the evidence lists for that account, and the references the change rests on. A proposal counts only after the comparison matched, and never changes its outcome.

**The comparison step reads the proposal lines into its output.** It reads them as strictly as verdict lines, and counts the lines it cannot read.

**A policy check on the orchestrator host decides.** It is Python with the standard library, tested with hostile cases, and it allows a set of proposals only when all of these hold:

- The comparison's outcome is a match, and it read every proposal line.
- Each account both checks call excess has exactly one proposal, and no other account has one.
- The action is remove, and the permission is one the account holds directly, not through a group.
- The checks name that permission in the account's excess, and without it the account is within its contract.

**The proposals are scored on the six held-out cases of [0042](0042-held-out-cases-and-the-baseline-without-the-agent.md), two jobs each,** by rules committed before the runs. A proposal is right when it equals the fix the checks imply, and where removal alone cannot make an account within, right is no proposal or one the policy refuses.

The policy's decision and the rehearsal's verdicts are counted beside each proposal.

**The unsafe patch is shown two ways.** Hand-made unsafe proposals are policy tests. One live run feeds the policy an operator's proposal whose rehearsal passes and which the policy refuses, marked as the operator's.

**Exercise 1 only.** No other kind of change is designed now.

## Trade-offs

- **Remove-only fits exercise 1, not every finding.** A permission that is right in kind but too wide needs a narrower change, which a later exercise decides.
- **The fix is implied by the checks.** The model's proposal can only match it or be refused, so the score shows whether the agent proposes the right fix, not a better one.
- **The policy is custom code that judges a change before a person sees it.** Its tests are the control, and the check after delivery is the proof ([0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md)).
- **A wrong verdict means no proposal.** The workflow stops first, as before.
- **Not seen when this was written:** a proposal line from the model, and the policy reading a live job's collection.
