# Exercise 1's investigation

How the investigation is scored: as dispatched jobs, through the workflow, on held-out cases, beside the same run without the agent ([ADR 0042](../decisions/0042-held-out-cases-and-the-baseline-without-the-agent.md)). The criteria are in the [roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation).

Status: **tested** on 2026-10-26. Twelve evaluation (eval) jobs ran on the live system, two per case, and were scored by these rules ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-scored-runs), [each job](../evidence/2026-10-25-2308-scored-cases.md)). The case file and these rules were committed and pushed before the first of them.

The remediation proposals were scored on 2026-10-27 by [the proposal rules](#the-proposal-rules), again two jobs per case. Under the rules as written, the four matched jobs got 6 of 6 accounts right, and 17 of 20 counting the stopped jobs ([record](../evidence/2026-10-27-0653-scored-proposals.md), [worklog](../worklogs/0006-remediation-pull-requests-and-delivery.md#the-scored-proposals)).

On the seed after the fix, with the agent's output as a structured output, twelve more eval jobs ran on 2026-10-27. None stopped on a line the verification gate could not read, and all 16 verdicts the deterministic checks agree on were theirs. By the proposal rules, the ten matched jobs got 16 of 16 accounts right, and 20 of 20 counting the stopped jobs ([record](../evidence/2026-10-27-2016-structured-output-eval.md), [worklog](../worklogs/0006-remediation-pull-requests-and-delivery.md#the-eval-run-after-the-fix)).

## The cases

[`collectors/netbox/cases.json`](../../collectors/netbox/cases.json) holds the eval set: six variants of the access specification, the least privilege each consumer account needs, each with the verdicts the deterministic checks give on NetBox's seed as it is. Since the fix was delivered on 2026-10-27 ([targets #15](https://github.com/sindredg/ai-security-platform-test/pull/15)), `inventory-reader` holds the tenant-scoped permission alone, as the control does. The two get the same verdicts in every case.

The eval runs before the fix collected against the seed as it was then: `inventory-reader` also held an unscoped copy, and its token returned all seven devices and addresses. The NetBox task was tuned on the seed's access specification, which is not among the cases.

| Case | What the access specification changes | Before the fix | After the fix | What it tests |
| --- | --- | --- | --- | --- |
| `control-only` | Names the control alone | Control `within/within` | The same | A `within` verdict. In the model evaluation of 2026-10-21, all three models called a token whose grants equal its access specification confirmed |
| `consumer-only` | Names `inventory-reader` alone | `excess/excess` | `within/within` | The seeded finding, and no line for an account the access specification does not name |
| `sites` | Grants and reads sites, and no longer expects them denied | `inventory-reader` `excess/excess`, control `missing/missing` | Both `missing/missing` | `missing`: no permission grants a read the access specification needs, and the read is refused |
| `devices-only` | Grants and reads devices only, and expects the address list denied | Both `excess/excess` | The same | `excess` for the control too: a permission the access specification does not grant, and a denied read that answers |
| `change` | Adds `change` on devices, and a device that does not exist | `inventory-reader` `excess/excess`, control `missing/missing` | Both `missing/missing` | `missing` by a grant and by a record |
| `two-of-three` | Lists two of tenant A's three devices | `inventory-reader` `excess/excess`, control `within/excess` | Both `within/excess` | Checks that disagree: the workflow stops whatever the model says, and the output is scored on whether it names the disagreement |

Verdicts are configured/observed. Before the fix, they were worked out with the collector's own functions against a stand-in for the seed. After the fix, both halves of the deterministic checks ran on each case's access specification on the live system on 2026-10-27, outside any job; each job's collection gives the real ones, which the verification gate uses.

## How an eval job runs

1. `collect-netbox-evidence JOB CASE` on the orchestrator. One line of its output gives both deterministic checks' verdicts for each account. Its elapsed time is the baseline's.
2. The workflow, under the same name, with the NetBox task from the same commit, 1200 seconds, and 8 turns. The model server's thinking setting is the one chosen from the development runs for [#36](https://github.com/sindredg/ai-security-platform/issues/36), and the worklog says which.
3. The verification gate's outcome and rows, the result, and the job's audit lines are kept.

Each case runs twice.

## The rules

Written before the first eval run. Applied by a script where a rule names a field, by reading where it says so, and each reading is written down.

| Rule | Read from | Scored |
| --- | --- | --- |
| The verdict for each account the deterministic checks agree on is theirs, the ground truth | The verification gate's rows | Per account: right or not. An account whose checks disagree is not scored here |
| Each verdict line cites at least one reference | The verification gate's rows | Per line |
| Each cited reference was fetched in that job | The tool service (an MCP server)'s audit log: an allowed `get_evidence` call whose `args_sha256` is the SHA-256 of `{"reference":"ev-000N"}` | Per line. A line citing one it never fetched counts as a conclusion without tool evidence |
| The output names the disagreement, in `two-of-three` | The output, by reading: for the control, it says both that the permission is the access specification's and that the token returned a device the specification does not list | Per job |
| Conclusions without tool evidence | The two reference rules | Counted per job |

Recorded per job beside the score: the verification gate's outcome, the elapsed time from the collection to the workflow's end, the tool calls in the audit log, and whether the KV cache was cleared.

The baseline, per case: the deterministic checks' verdicts, the ground truth by construction, the collection's elapsed time, and one command and one line of output as the operator's effort. The agent's path costs the collection, a submission, and the verification gate's rows.

## The proposal rules

Milestone 5 scores each matched job's proposal lines on the same six cases, two jobs each ([ADR 0043](../decisions/0043-proposals-are-remove-only-and-a-policy-check-decides.md)). These rules and the expected fixes were committed before the first eval run of the proposals.

The expected fix is the policy's implied fix: the permissions the deterministic checks call excess whose removal leaves the account within its access specification. Before the fix, it was computed with `policy.implied_fix` from the seed's configured report on the live NetBox, where `inventory-reader` held permission 1, scoped to tenant A, and 2, its unscoped copy. The control holds 3, scoped.

| Case | `inventory-reader` | `inventory-reader-control` | Where a fix can go on |
| --- | --- | --- | --- |
| `control-only` | Not in the access specification | No proposal: `within` | Nowhere. The policy refuses a job with no account to fix |
| `consumer-only` | Remove 2 | Not in the access specification | Remove 2 from `inventory-reader` |
| `sites` | No fix: removing 2 leaves it missing a grant for sites | No proposal: `missing` | Nowhere |
| `devices-only` | No fix: its scoped permission grants addresses too | No fix: the same | Nowhere |
| `change` | No fix: no permission grants change on devices | No proposal: `missing` | Nowhere |
| `two-of-three` | Remove 2 | No proposal | Nowhere: the deterministic checks disagree on the control, so the verification gate stops first |

After the fix, each account holds one permission scoped to tenant A. `policy.implied_fix` on the live configured reports of 2026-10-27 gives no fix for any account in any case: an account is within its spec (`within`), or removing its one permission leaves it under-privileged (`missing`). Right is no proposal everywhere, or a proposal the policy refuses.

| Rule | Read from | Scored |
| --- | --- | --- |
| A proposal is right when it equals the expected fix, and an account without one gets no proposal | The verification gate's `proposals` | Per account both deterministic checks call `excess` |
| Where no fix exists, right is no proposal, or a proposal the policy refuses | The verification gate's `proposals` and the bundle's `policy` | Per account |
| A proposal line that cannot be read counts against the job | The verification gate's `unread_proposals` | Per job |
| The policy's decision and the staging test's verdicts are recorded beside the score | The bundle `propose-netbox-fix` writes | Per job, not scored |
| The verdict rules above stay as they are | As above | As above |

## Limits

- **Twelve jobs.** They show whether the investigation works at all, not a rate.
- **One configuration.** Every case reads the same permissions and records. The cases test reading an access specification against evidence, not finding a different misconfiguration.
- **The seed after the fix is an easier test.** Both accounts hold the same grants, so a model cannot be wrong by mixing them up, and no case has a fix to propose. Scores on it are a new baseline, not comparable with the runs before the fix.
- **One author wrote the cases and tuned the task.** The task was tuned on the seed's access specification only, and no change to its wording targets a case. The separation is by data.
- **The rule for the disagreement is read, not computed.**
- **Found in the runs: no case has documents that disagree in the task's sense.** The task calls `ev-0002` and `ev-0003` disagreeing a reason for `inconclusive`. In `two-of-three` those two agree, and the deterministic checks disagree because the access specification grants a device its record list leaves out ([#205](https://github.com/sindredg/ai-security-platform/issues/205)).
- **Found in the runs: two cases are close to the tuning specification.** `control-only` and `consumer-only` change only the accounts the access specification names, as [ADR 0042](../decisions/0042-held-out-cases-and-the-baseline-without-the-agent.md) says. They hold 4 of the 18 scored verdicts.
