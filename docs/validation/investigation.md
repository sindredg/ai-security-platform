# Exercise 1's investigation

How the investigation is scored: as dispatched jobs, through the workflow, on held-out cases, beside the same run without the agent ([ADR 0042](../decisions/0042-held-out-cases-and-the-baseline-without-the-agent.md)). The criteria are in the [roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation).

Status: **tested** on 2026-10-26. Twelve scored jobs ran on the live system, two per case, and were scored by these rules ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-scored-runs)). The case file and these rules were committed and pushed before the first of them.

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

1. `collect-netbox-evidence JOB CASE` on the orchestrator. Its last line is both checks' verdicts for each account. Its elapsed time is the baseline's.
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

## Limits

- **Twelve jobs.** They show whether the investigation works at all, not a rate.
- **One configuration.** Every case reads the same permissions and records. The cases test reading a contract against evidence, not finding a different misconfiguration.
- **One author wrote the cases and tuned the task.** The task was tuned on the seed's contract only, and no change to its wording targets a case. The separation is by data.
- **The rule for the disagreement is read, not computed.**
