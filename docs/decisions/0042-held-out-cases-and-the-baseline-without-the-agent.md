# 0042. Held-out cases are contract variants, and the baseline is the same run without the agent

Status: Accepted
Date: 2026-10-25

## Context

Milestone 4 scores the investigation as a dispatched job, through the workflow, on held-out cases, with the case file's hash committed before the first scored run. The answer has to cite tool evidence for each conclusion and say so when evidence disagrees. A baseline without AI, using the same tools, is recorded beside it, and a rubric written before the runs scores both, with the operator's effort and the elapsed time. The result is recorded whichever way it falls ([roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation)).

What is fixed already:

- **One NetBox, one seed.** The seed holds exercise 1's finding and an unaffected control, and two checks read it ([0037](0037-an-unscoped-copy-of-the-consumers-permission.md)). Every other check of the target expects that seed.
- **The checks are the expected verdicts.** The workflow compares the model's verdict for each account with them, and stops on anything but a match ([0041](0041-the-workflow-compares-the-models-verdict-with-the-checks.md)).
- **The task was tuned on the seed's contract.** Development jobs on 2026-10-25 changed the NetBox task between runs, on that contract alone ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-task-on-development-jobs)). A case scored now has to be one the task was not tuned on.

## Options

**Where the cases come from**

| Option | What it gives | What it costs |
| --- | --- | --- |
| Variants of the contract, collected against the same seed | The checks give each case's verdicts, NetBox does not change, and the seed's checks keep passing | Every case reads the same permissions. The cases vary what the contract allows, not what NetBox holds |
| Variants of the seed, written to NetBox per case | A different configuration per case | NetBox is rewritten and restored around every case, and the target's checks fail in between |
| Evidence documents written by hand | Any shape | The collection is not exercised, and each expected verdict is a person's guess |

**The baseline**

| Option | What it gives | What it costs |
| --- | --- | --- |
| A person reads the same three documents and gives a verdict per account, timed | A human result to compare with | The operator's time on every case, for a result the checks already give |
| The same run without the agent: the collect command, then the two checks' verdicts | No operator session, and the same tools as the job | Right by construction: the checks are what the comparison calls right |
| No baseline | Nothing | The roadmap asks for one |

**How the answers are scored**

| Option | What it gives | What it costs |
| --- | --- | --- |
| By rule, written before the runs | The same score from anyone who applies it | Misses what no rule names. Each judgment call is written down |
| By reading each answer | Catches what rules miss | Not repeatable, and written after the answers are known |

## Decision

**The held-out cases are variants of the consumer contract, collected against the seed as it is.** Each changes what the contract grants, which accounts it names, the records it lists, or the requests it expects NetBox to deny. None is the seed's contract, which the task was tuned on. The cases are one file in the repository, with each case's predicted verdicts, and its SHA-256 is in a pushed commit before the first scored run. The collect command takes a case by name. Without one it collects against the installed contract, as before.

**Each case runs twice,** as a NetBox job through the workflow, with 1200 seconds, the longest a job may have, and eight turns.

**The expected verdicts are the checks', from each job's own collection.** A case whose checks disagree on an account stops whatever the model answers. It is scored on whether the answer says the evidence disagrees. A collection whose verdicts differ from the case's prediction is reported, and the case is not what was designed.

**The baseline is the same run without the agent.** For each case, the collect command runs and its last line gives both checks' verdicts for each account. Its elapsed time is the baseline's time, and reading that line is the operator's effort.

**The answers are scored by rule.** The rule set is written before the first scored run and committed with the case file:

- For each account the checks agree on, whether the model's verdict is theirs.
- Whether each verdict line cites at least one reference, and whether each cited reference was fetched in that job, read from the tool service's audit log.
- For a case with a disagreement, whether the answer names it.
- The count of verdicts without a fetched reference.

The comparison's outcome, the elapsed time, the turns, and the tool calls are recorded per job.

## Trade-offs

- **The baseline is right by construction.** The comparison shows what the agent costs and what its answer adds, not whether it finds more than the checks. That is the expected result for exercise 1, which a deterministic check finds by itself ([0004](0004-netbox-as-first-target.md)).
- **Every case shares one configuration.** The cases test reading a contract against evidence, not finding a different misconfiguration. Two of them name one account each and are close to the contract the task was tuned on.
- **Twelve jobs show whether the investigation works at all.** They do not give a rate with a useful margin.
- **The checks' rule on unconstrained permissions is stricter than the task's definition of excess.** The checks call any permission without a constraint excess, even where the contract grants one without a constraint. No case uses that, so the expected verdicts follow the task's definitions.
- **Not seen when this was written:** the collect command with a case's contract on the live system, and the observed half reading a case's contract on the lab VM.
