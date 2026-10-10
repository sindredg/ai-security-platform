# Roadmap

Work proceeds one milestone at a time. A milestone is complete when its exit gate is met and the evidence is recorded in a [worklog](worklogs/README.md). The design behind these milestones is in the [architecture](architecture.md).

## Status

| Milestone | State |
| --- | --- |
| 0. Documentation baseline and preflight | In progress |
| 1. Network foundation | Planned |
| 2. Platform compute | Planned |
| 3. Toolchain integration | Planned |
| 4. NetBox target and exercise 1 investigation | Planned |
| 5. Remediation, pull requests, and delivery | Planned |
| 6. Operational and containment drills | Planned |
| 7. Exercise 2: excess network access | Planned |
| 8. Exercise 3: vulnerable image or dependency | Planned |

## 0. Documentation baseline and preflight

Establish the architecture, the first decision records, and account-specific evidence for regions and sizes.

**Exit gate:** architecture, roadmap, and decision records are reviewed. The preflight worklog records quota and SKU evidence for both regions.

## 1. Network foundation

Create both Terraform roots with separate state. Provision resource groups, virtual networks, subnets, network security groups, and peering. No compute.

**Depends on:** the state storage decision.

**Exit gate:**

- `terraform plan` is clean for both roots after apply.
- Peering state is `Connected` in both directions.
- Effective rules show default deny between the networks, with only the documented flows allowed.
- The target root's identity cannot modify platform resources, and the reverse.

## 2. Platform compute

Provision the orchestrator and AI worker VMs. Install K3s. Establish administrative access and the egress path.

**Depends on:** the administrative access and egress decisions.

**Exit gate:**

- Both VMs are reachable only through the chosen administrative path.
- K3s is healthy after a VM restart.
- The worker cannot open a connection to the target network or the internet.
- Idle CPU and memory use on both VMs is measured and recorded.

## 3. Toolchain integration

Deploy Argo Workflows, the agent runtime, and the model server. Prove the path from a workflow to the worker and back, with synthetic evidence only.

**Depends on:** the dispatch and workload identity decisions.

**Exit gate:**

- A workflow starts a worker job, the agent calls one authorized tool, and a schema-checked result returns.
- A tool call for another job or target is denied by the tool service.
- Cancelling a workflow stops the worker job and cleans up its session.
- Model memory use, latency per turn, and tokens per second are measured on the chosen size.
- Component footprint on the orchestrator is measured. Deferred components are added or dropped based on it.

If a candidate needs a substantial custom service to pass this gate, replace or simplify it before continuing.

## 4. NetBox target and exercise 1 investigation

Define the consumer contract. Deploy NetBox, synthetic inventory, and the consumer. Seed the excess-permission finding and investigate it.

**Depends on:** the NetBox version and consumer scope decisions.

**Exit gate:**

- The consumer contract lists endpoints, fields, permitted records, and expected denials.
- Deterministic checks confirm the finding and a known unaffected case.
- The AI investigation cites tool evidence for each conclusion and records uncertainty where evidence disagrees.
- A baseline without AI, using the same tools, is recorded for comparison.

## 5. Remediation, pull requests, and delivery

Rehearse a proposed fix on the rehearsal copy, publish it as a pull request, and deliver it after approval.

**Depends on:** the repository, credential, and approval enforcement decisions.

**Exit gate:**

- A proposal becomes a pull request with evidence, without the worker holding repository credentials.
- A deliberately unsafe patch is rejected even though functional tests pass.
- Delivery applies only the approved commit to the approved target. A changed commit invalidates the approval.
- After delivery, the consumer returns its required records, forbidden records are not disclosed, and writes stay denied.
- One supported rollback is demonstrated, and what it cannot repair is recorded.

## 6. Operational and containment drills

Exercise failure and attack cases against the completed workflow.

**Exit gate:** recorded results, including failures, for:

- Worker and orchestrator interruption without duplicate changes.
- Duplicate findings without duplicate pull requests.
- Forbidden tool calls, storage reads, network connections, and policy edits from a worker.
- Instructions embedded in advisories and tool results.
- Forged and stale target evidence.
- Cleanup verification and measured resource use per investigation.

## 7. Exercise 2: excess network access

Reuse the workflow. Seed a target network rule that admits the unintended viewpoint.

**Exit gate:**

- Probes from both viewpoints before and after the change.
- The change touches only allowlisted target network fields.
- The consumer contract and the exercise 1 denials still hold.
- Outer containment is unchanged.

## 8. Exercise 3: vulnerable image or dependency

Select a real advisory, an affected pinned artifact, and a reviewed fix before seeding.

**Exit gate:**

- An applicability record for the specific artifact, not a version-string match.
- The update is rehearsed with database migration and a tested recovery procedure.
- The specific finding is reassessed after delivery. A clean generic scan is not sufficient.
- Results from exercises 1 and 2 still hold.

If no suitable affected and fixed artifact pair is found, this exercise is recorded as not done.

## Later options

- A Container Apps target and a Windows client target.
- Additional models where measurement justifies them.
- A managed Kubernetes deployment profile with more capacity.
