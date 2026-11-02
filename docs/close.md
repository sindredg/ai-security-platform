# Project close

What the platform showed, where the evidence is, and what it did not show. Milestone states are on the [roadmap](roadmap.md#status), and the weak points that stay on the [security index](security/README.md#standing-weak-points).

## What was built

Six VMs in three Azure regions, with no public address. A trusted orchestrator runs the workflow and holds the platform's credentials, and an AI worker runs an open-weight model and an agent that gets only a short-lived token for its job's evidence ([credential inventory](security/credentials.md)). An edge VM is the only outbound path, and a router is the only mesh VPN node ([architecture](architecture.md)).

None of it runs any more: the [teardown runbook](runbooks/teardown.md) removed it ([worklog](worklogs/0009-exercise-2-excess-network-access.md#the-teardown)).

In exercise 1, a finding goes from collection to delivery in five steps. Deterministic checks give their verdicts first, the agent reads the same evidence through one tool, and a verification gate stops the workflow on any difference. A fix is tested on a staging copy, published as a pull request with checked fields only, and delivered after a signed approval of that commit ([how a fix gets made](../README.md#how-a-fix-gets-made)).

## What it showed

| Claim | Evidence |
| --- | --- |
| The worker cannot reach a credential, the targets, or the internet beyond two package hosts | 42 tested probes during a job, none got through. UDP, the orchestrator's other ports, the model server, and `/proc` were not probed ([worklog](worklogs/0007-operational-and-containment-drills.md#slice-2-forbidden-calls-from-the-worker), [#229](https://github.com/sindredg/ai-security-platform/issues/229)) |
| A verdict unlike the checks' stops the workflow, whatever caused it | Injected instructions, a smaller model, checks that disagree, and a withheld document, each stopped ([evidence](evidence/README.md)) |
| A fix the model proposes reaches the target only through a signed approval of that exact commit | One fix proposed by a job, delivered, and rolled back ([worklog](worklogs/0006-remediation-pull-requests-and-delivery.md#one-fix-end-to-end), [targets #15](https://github.com/sindredg/ai-security-platform-test/pull/15)) |
| The incident response runbook contains and rotates in its three cases | A compromised worker, a compromised target, and a leaked credential. The target's and orchestrator's replacements were not run ([worklog](worklogs/0007-operational-and-containment-drills.md#slice-7-the-incident-response-runbook)) |
| Two independent checks find a seeded port rule that lets the wrong subnet reach the target | The rules at the repository's `main` and a connection from each viewpoint's address agreed in three collections: the staging subnet `excess`, the consumer `within` ([worklog](worklogs/0009-exercise-2-excess-network-access.md#the-jobs)) |
| A vulnerable target image is found and replaced through a staging test | 42 critical and high findings found by a scan, cleared by a new pin after a staging test with a recovery ([worklog](worklogs/0008-exercise-3-vulnerable-image.md)) |
| Every check passed on the live system after the NetBox update, within what the checks cover | 446 of 446. With exercise 2's seed live, 446 of 448: only the two checks that read the seed's path failed ([last run](validation/README.md#last-run), [not covered](validation/README.md#what-the-checks-do-not-cover)) |

The NetBox update changed four lines of the targets repository's pin, from v4.7.3 to v4.7.4 ([targets #20](https://github.com/sindredg/ai-security-platform-test/pull/20)):

![The pull request's diff of netbox/image.env: the tag, the index digest, the linux/amd64 manifest digest, and the image ID move from v4.7.3-5.1.1 to v4.7.4-5.1.1](images/targets-20-image-env.png)

Each test run set has a page of its own, with each job's verdicts, calls, and answer ([test evidence](evidence/README.md)). What the runs taught is on the [lessons](evidence/lessons.md) page.

## The model's place

In exercise 1 the deterministic checks decide, and the model adds nothing they do not already know. The checks took about 4 seconds a job, reasoned from the collection's timings, and a model job 326 to 885 seconds ([worklog](worklogs/0005-netbox-target-and-exercise-1.md#against-the-baseline)). The verification gate exists because the model is not trusted, so a model that agrees with the checks changes no outcome.

| Run | Verdicts right, where the checks agree |
| --- | --- |
| Held-out cases before the seed's fix, two runs | 13 and 10 of 18 ([lab against production](security/lab-vs-production.md)) |
| The same after the fix, with a structured output | 16 of 16, on cases with no fix left to propose ([worklog](worklogs/0006-remediation-pull-requests-and-delivery.md), [#220](https://github.com/sindredg/ai-security-platform/issues/220)) |
| One request, no agent | 3 of 5 cases ([worklog](worklogs/0007-operational-and-containment-drills.md#without-an-agent)) |
| A smaller model, Qwen3.5-2B | None of 16 cases ([ADR 0031](decisions/0031-qwen3-5-4b-stays-the-workers-model.md)), and no usable answer in 2 more ([worklog](worklogs/0007-operational-and-containment-drills.md#a-smaller-model)) |

Injected instructions remain the model's weak point. Every model in the first comparison followed them ([A1](security/ai-threats.md)). On the live seed with a device whose name is an instruction, the model followed it in 1 of 4 finished jobs, and the gate stopped that one ([lessons](evidence/lessons.md)).

A model could earn its place where no check decides: documents that disagree in the task's sense ([#205](https://github.com/sindredg/ai-security-platform/issues/205)), and findings whose facts need reading, not counting. In exercise 2 the checks decided alone, and no model job answered within its limit ([#253](https://github.com/sindredg/ai-security-platform/issues/253)), so the model's quality on a network finding stays unmeasured. Exercise 3 ran without the model: the scan and the pin decided.

## What it did not show

- **A fix for exercise 2.** No job answered within its limit, so no port rule was proposed, delivered, or probed after ([worklog](worklogs/0009-exercise-2-excess-network-access.md), [#253](https://github.com/sindredg/ai-security-platform/issues/253)).
- **A rebuild of the whole platform.** Only the worker booted from its current template ([weak point 7](security/README.md#standing-weak-points)).
- **Alerts that reach someone.** The rules fire in the portal and send nothing ([weak point 6](security/README.md#standing-weak-points)).
- **Production.** One node, one operator, synthetic data ([lab against production](security/lab-vs-production.md)).

## Open issues

Each is a known limitation, with its evidence and the trigger that would bring it back. They stay open after the close: [open issues](https://github.com/sindredg/ai-security-platform/issues).

## Cost

About 1,685 NOK from 2026-10-10 to 2026-11-01, the last day partial, by Azure Cost Management's actual cost per day, read at 17:27 UTC on 2026-11-01. From 2026-10-25, with every VM and the targets running, a day cost 106 to 111 NOK. The VMs cost the same idle or busy, so a 12-minute job's share of a day is about 1 NOK, reasoned, not billed.
