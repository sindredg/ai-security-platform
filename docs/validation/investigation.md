# Exercise 1's investigation

How the investigation is scored: as dispatched jobs, through the workflow, on held-out cases, beside the same run without the agent ([ADR 0042](../decisions/0042-held-out-cases-and-the-baseline-without-the-agent.md)). The criteria are in the [roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation).

Status: **tested** on 2026-10-26. Twelve scored jobs ran on the live system, two per case, and were scored by these rules ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-scored-runs), [each job](../evidence/2026-10-25-2308-scored-cases.md)). The case file and these rules were committed and pushed before the first of them.

The proposals were scored on 2026-10-27 by [the proposal rules](#the-proposal-rules), again two jobs per case. Under the rules as written, the four matched jobs got 6 of 6 accounts right, and 17 of 20 counting the stopped jobs ([record](../evidence/2026-10-27-0653-scored-proposals.md), [worklog](../worklogs/0006-remediation-pull-requests-and-delivery.md#the-scored-proposals)).

## The cases

[`collectors/netbox/cases.json`](../../collectors/netbox/cases.json) holds six variants of the consumer contract, each with the verdicts the checks are expected to give. Every case is collected against NetBox's seed as it is: `inventory-reader` holds the tenant-scoped permission and an unscoped copy, and its token returns all seven devices and addresses. The control holds the scoped permission alone. The NetBox task was tuned on the seed's contract, which is not among them.

| Case | What the contract changes | Expected, configured/observed | What it tests |
| --- | --- | --- | --- |
| `control-only` | Names the control alone | Control `within/within` | A `within` verdict. In the model comparison of 2026-10-21, all three models called a token whose grants equal its contract confirmed |
| `consumer-only` | Names `inventory-reader` alone | `excess/excess` | The seeded finding, and no line for an account the contract does not name |
| `sites` | Grants and reads sites, and no longer expects them denied | `inventory-reader` `excess/excess`, control `missing/missing` | `missing`: no permission grants a read the contract needs, and the read is refused |
| `devices-only` | Grants and reads devices only, and expects the address list denied | Both `excess/excess` | `excess` for the control too: a permission the contract does not grant, and a denied read that answers |
| `change` | Adds `change` on devices, and a device that does not exist | `inventory-reader` `excess/excess`, control `missing/missing` | `missing` by a grant and by a record |
| `two-of-three` | Lists two of tenant A's three devices | `inventory-reader` `excess/excess`, control `within/excess` | Checks that disagree: the workflow stops whatever the model says, and the answer is scored on whether it names the disagreement |

The expected verdicts were worked out with the collector's own functions against a stand-in for the seed. Each job's collection gives the real ones, which the comparison uses.

## How a scored job runs

1. `collect-netbox-evidence JOB CASE` on the orchestrator. One line of its output gives both checks' verdicts for each account. Its elapsed time is the baseline's.
2. The workflow, under the same name, with the NetBox task from the same commit, 1200 seconds, and 8 turns. The model server's thinking setting is the one chosen from the development runs for [#36](https://github.com/sindredg/ai-security-platform/issues/36), and the worklog says which.
3. The comparison's outcome and rows, the result, and the job's audit lines are kept.

Each case runs twice.

## The rules

Written before the first scored run. Applied by a script where a rule names a field, by reading where it says so, and each reading is written down.

| Rule | Read from | Scored |
| --- | --- | --- |
| The verdict for each account the checks agree on is theirs | The comparison's rows | Per account: right or not. An account whose checks disagree is not scored here |
| Each verdict line cites at least one reference | The comparison's rows | Per line |
| Each cited reference was fetched in that job | The tool service's audit log: an allowed `get_evidence` call whose `args_sha256` is the SHA-256 of `{"reference":"ev-000N"}` | Per line. A line citing one it never fetched counts as a conclusion without tool evidence |
| The answer names the disagreement, in `two-of-three` | The answer, by reading: for the control, it says both that the permission is the contract's and that the token returned a device the contract does not list | Per job |
| Conclusions without tool evidence | The two reference rules | Counted per job |

Recorded per job beside the score: the comparison's outcome, the elapsed time from the collection to the workflow's end, the tool calls in the audit log, and whether the slot was erased.

The baseline, per case: the checks' verdicts, right by construction, the collection's elapsed time, and one command and one line of output as the operator's effort. The agent's path costs the collection, a submission, and the comparison's rows.

## The proposal rules

Milestone 5 scores each matched job's proposal lines on the same six cases, two jobs each ([ADR 0043](../decisions/0043-proposals-are-remove-only-and-a-policy-check-decides.md)). These rules and the expected fixes were committed before the first scored proposal run.

The expected fix is the policy's implied fix: the permissions the checks call excess whose removal leaves the account within its contract. It was computed with `policy.implied_fix` from the seed's configured report on the live NetBox, where `inventory-reader` holds permission 1, scoped to tenant A, and 2, its unscoped copy. The control holds 3, scoped.

| Case | `inventory-reader` | `inventory-reader-control` | Where a fix can go on |
| --- | --- | --- | --- |
| `control-only` | Not in the contract | No proposal: within | Nowhere. The policy refuses a job with no account to fix |
| `consumer-only` | Remove 2 | Not in the contract | Remove 2 from `inventory-reader` |
| `sites` | No fix: removing 2 leaves it missing a grant for sites | No proposal: missing | Nowhere |
| `devices-only` | No fix: its scoped permission grants addresses too | No fix: the same | Nowhere |
| `change` | No fix: no permission grants change on devices | No proposal: missing | Nowhere |
| `two-of-three` | Remove 2 | No proposal | Nowhere: the checks disagree on the control, so the comparison stops first |

| Rule | Read from | Scored |
| --- | --- | --- |
| A proposal is right when it equals the expected fix, and an account without one gets no proposal | The comparison's `proposals` | Per account the checks call excess by both |
| Where no fix exists, right is no proposal, or a proposal the policy refuses | The comparison's `proposals` and the bundle's `policy` | Per account |
| A proposal line that cannot be read counts against the job | The comparison's `unread_proposals` | Per job |
| The policy's decision and the rehearsal's verdicts are recorded beside the score | The bundle `propose-netbox-fix` writes | Per job, not scored |
| The verdict rules above stay as they are | As above | As above |

## Limits

- **Twelve jobs.** They show whether the investigation works at all, not a rate.
- **One configuration.** Every case reads the same permissions and records. The cases test reading a contract against evidence, not finding a different misconfiguration.
- **One author wrote the cases and tuned the task.** The task was tuned on the seed's contract only, and no change to its wording targets a case. The separation is by data.
- **The rule for the disagreement is read, not computed.**
- **Found in the runs: no case has documents that disagree in the task's sense.** The task calls `ev-0002` and `ev-0003` disagreeing a reason for `inconclusive`. In `two-of-three` those two agree, and the checks disagree because the contract grants a device its record list leaves out ([#205](https://github.com/sindredg/ai-security-platform/issues/205)).
- **Found in the runs: two cases are close to the tuning contract.** `control-only` and `consumer-only` change only the accounts the contract names, as [ADR 0042](../decisions/0042-held-out-cases-and-the-baseline-without-the-agent.md) says. They hold 4 of the 18 scored verdicts.
