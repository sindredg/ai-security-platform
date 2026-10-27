# 0041. The workflow compares the model's verdict with the checks, and stops on anything but a match

Status: Accepted
Date: 2026-10-25

How the template keeps a workflow from running either step alone: [0048](0048-the-workflows-steps-are-inline-so-no-workflow-runs-one-alone.md).

How the answer gets its verdict lines: [0049](0049-a-netbox-jobs-answer-is-a-final-output-checked-against-a-schema.md).

## Context

The architecture lets a proposal go ahead only when the model's verdict agrees with the deterministic checks. A disagreement, an inconclusive verdict, or a failed job stops the workflow for the operator ([architecture](../architecture.md#workflow)). Milestone 4 has to show both outcomes, a match and a stop, each with evidence from that job only ([roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation)).

Three things stand in the way:

- **No pod can read the checks' verdicts.** The collect command keeps them on the orchestrator, in root's files beside each job's snapshot, so the job never reads them ([0040](0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)). Workflow pods run at the restricted pod security level, which refuses a host path.
- **The answer has no verdict per account.** The system text asks every answer for one `Status:` line and one `Excess:` line, which fit the synthetic fixture's single question. A NetBox job has two accounts, each with its own verdict. On 2026-10-25 a job's answer called one account inconclusive, then listed that account's reads as excess ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-collection-and-the-jobs)).
- **Nothing reads the verdict.** The dispatch step checks the result's shape, the slot erase, and that a tool was called. A job succeeds whatever it concludes.

## Options

**Where the comparison reads the checks' verdicts**

| Option | What it gives | What it costs |
| --- | --- | --- |
| The collect command also writes the job's verdicts into a config map in `orchestration`, and only the comparison step mounts its job's key | No new network path. The verdicts come from the program that computed them | One more config map. The verdicts sit in the cluster's store |
| The tool service serves them on its registration port, which only dispatch pods reach | No new object | The verdicts move into the component that parses the worker's input. One bug there hands the model the answer |
| A workflow parameter | No new object | Whoever submits the job sets the expected value, not the collector |
| The operator compares on the host after the job | Nothing new in the cluster | The workflow does not compare |

**Where the comparison runs**

| Option | Cost |
| --- | --- |
| A step of its own after dispatch, from the dispatch image | One more pod per job. The answer travels as a workflow parameter |
| Inside the dispatch step | The verdicts sit in the pod that talks to the worker while the job runs, and a failed job and a mismatch fail the same step |

**What a stop is**

| Option | Cost |
| --- | --- |
| The comparison step fails, and the workflow ends Failed with the reason | A stopped job cannot be continued. The next try is a new job |
| A suspend step that the operator resumes or stops | In milestone 4 nothing comes after it to resume into, and the architecture wants no override. A suspended workflow keeps the worker mutex, so every other job waits: Argo releases a workflow's locks when the workflow completes (read in v4.1.6's source) |

## Decision

**The answer ends with one line per account.** The NetBox task, [`collectors/netbox/task.txt`](../../collectors/netbox/task.txt), says what each evidence document holds, defines each verdict the way the collector's checks decide theirs, and asks for the evidence behind each conclusion. It ends with one line per account:

```text
Verdict: ACCOUNT VALUE REFERENCES
```

The values are `excess`, `missing`, `within`, and `inconclusive`. The system text keeps its `Status:` and `Excess:` lines as the default, behind one new sentence: when the task says how the answer ends, end it that way. The synthetic fixture, its check, and the model comparison's cases keep working unchanged.

**The collect command writes the job's verdicts into a config map that the comparison reads.** The config map is `netbox-verdicts` in `orchestration`, with one key per job, `JOB.json`. Each key holds the job's ID, the time of the collection, and each account's configured and observed verdicts, and nothing else from NetBox. It keeps the newest jobs, as the tool service's config map does. Only root on the orchestrator writes it: no workload account may change config maps in `orchestration`, and a check reads that. The comparison step mounts only its own job's key, and the document names its job.

**A comparison step follows dispatch, for NetBox jobs.** The template's entrypoint becomes a list of steps: dispatch, then the comparison when the target is NetBox. Synthetic jobs end after dispatch, as before. The comparison runs from the dispatch image, holds no credential, and carries a label of its own, so no network policy lets it reach the worker or the tool service.

A match is every account the checks name, with the configured and the observed check in agreement, neither of them unknown, and the model's value the same as theirs. Anything else is a stop:

- a mismatch, or an inconclusive verdict
- an account with no line, or with lines that disagree
- a line for an account the checks do not name, or a verdict line that cannot be read
- checks that disagree with each other, or cannot settle an account
- no verdicts for the job

**A stop is a failed step.** The comparison step exits non-zero, and the workflow ends Failed, with the reason as the step's message. The exit handler revokes the job's token, as before. A match ends the workflow Succeeded. Nothing overrides a stop: the operator looks, and the next try is a new job. In milestone 5 the proposal runs after a match only.

**The comparison shows its work.** It prints one row per account, with the model's value and references beside both checks' verdicts, and keeps the same rows as the step's output. Of the answer, it prints and keeps only what matched a pattern: account names, values, references, and counts.

**The dispatch step hands on the answer, and limits it.** The answer reaches the comparison as a workflow parameter, which Argo renders. Argo reads `{{` as its own template syntax, and `{{=` as an expression its controller evaluates. It moves a pod's arguments, or its template, over 128 KiB into a config map, which its controller may not create here, and writes each `<`, `>`, and `&` as six characters. So the dispatch step fails a job whose answer is longer than 8 KiB or holds `{{`. A failed job is a stop.

## Trade-offs

- **A small model has to write the lines exactly.** A line the comparison cannot read is a stop, not a match. Qwen3.5-4B got 3 of 8 cases right in the model comparison ([0031](0031-qwen3-5-4b-stays-the-workers-model.md)). If no task text gets it to a match, the comparison works and the investigation does not.
- **A stop has no override.** A right verdict in the wrong form costs a new job.
- **The comparison trusts the checks.** Two checks wrong the same way pass a wrong verdict. [0037](0037-an-unscoped-copy-of-the-consumers-permission.md) accepts that: the finding needs both.
- **An answer over 8 KiB fails the job.** The system text asks for short answers. The NetBox answer of 2026-10-25 was about 2 KiB.
- **One more pod per job,** from an image the node already holds.
- **The verdicts are in the cluster's store,** readable by root on the orchestrator and by the Argo controller, as the evidence is. They name accounts and give each two words.
- **Not seen when this was written:** a template volume whose key names the workflow, a missing key in a volume marked optional, the reason as Argo's step message, and the condition on the target. The change that builds this records whether they work, in the [milestone 4 worklog](../worklogs/0005-netbox-target-and-exercise-1.md).
