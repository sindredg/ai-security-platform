# Roadmap

Each milestone has an exit gate: things that must be shown to work, not things that must be built. A milestone is done when its gate is met and the evidence is in a [worklog](worklogs/README.md). The design behind all of this is in the [architecture](architecture.md).

## Status

| Milestone | State |
| --- | --- |
| 0. Documentation baseline and preflight | Done. [Worklog](worklogs/0000-azure-preflight.md) |
| 1. Network foundation | Done, with one check carried to milestone 2. [Worklog](worklogs/0001-network-foundation.md) |
| 2. Platform compute | Planned |
| 3. Toolchain integration | Planned |
| 4. NetBox target and exercise 1 investigation | Planned |
| 5. Remediation, pull requests, and delivery | Planned |
| 6. Operational and containment drills | Planned |
| 7. Exercise 2: excess network access | Planned |
| 8. Exercise 3: vulnerable image or dependency | Planned |

## 0. Documentation baseline and preflight

Write down the design and the first decisions, and get account-specific evidence for regions and sizes before anything depends on them.

**Exit gate:** the architecture, roadmap, and first decision records are published. The preflight worklog records quota and VM size evidence for both regions.

## 1. Network foundation

Create the state storage and both Terraform roots. Provision resource groups, virtual networks, subnets, network security groups, and peering. No compute yet.

The point of doing this first is to prove the separation before there is anything to separate.

**Exit gate:**

- `terraform plan` is clean for both roots after apply.
- Peering state is `Connected` in both directions.
- Effective rules show default deny between the networks, with only the documented flows allowed.
- The target root's identity cannot modify platform resources, and the reverse.

**Result:** met, except that effective rules cannot be read without a network interface. The configured rules are verified. The effective-rule check moves to milestone 2.

## 2. Platform compute

Provision the orchestrator and AI worker VMs. Install K3s. Set up the mesh VPN, the egress path, and the public address policy.

**Depends on:** the egress decision, made in [ADR 0009](decisions/0009-one-egress-point-on-the-orchestrator-subnet.md).

**Exit gate:**

- Both VMs are reachable over the mesh VPN and have no public address.
- Effective rules on each network interface match the configured rules, and the denied paths are tested with traffic. Carried over from milestone 1.
- K3s comes back healthy after a VM restart.
- The worker cannot open a connection to the target network or the internet, and cannot resolve a public name.
- A public address on a network interface is refused by policy in both workload resource groups.
- Idle CPU and memory use on both VMs is measured.

## 3. Toolchain integration

Deploy Argo Workflows, the agent runtime, and the model server. Prove the round trip from a workflow to the worker and back, on synthetic evidence only.

This is where the design is most likely to be wrong, so it comes before any target exists.

**Depends on:** the dispatch and workload identity decisions.

**Exit gate:**

- A workflow starts a worker job, the agent calls one authorized tool, and a schema-checked result comes back.
- A tool call for another job or target is refused by the tool service.
- Cancelling a workflow stops the worker job and cleans up its session.
- Model memory use, latency per turn, and tokens per second are measured on the chosen size.
- Component footprint on the orchestrator is measured. Deferred components go in or get dropped based on it.

If a candidate needs a substantial custom service to pass this gate, replace it or simplify the design. Don't build the service.

## 4. NetBox target and exercise 1 investigation

Define the consumer contract. Deploy NetBox, synthetic inventory, and the consumer. Seed the excess-permission finding and investigate it.

**Depends on:** the NetBox version and consumer scope decisions.

**Exit gate:**

- The consumer contract lists endpoints, fields, permitted records, and expected denials.
- Deterministic checks confirm the finding and a known unaffected case.
- The AI investigation cites tool evidence for each conclusion, and says so when evidence disagrees.
- A baseline without AI, using the same tools, is recorded for comparison.

## 5. Remediation, pull requests, and delivery

Rehearse a proposed fix on the rehearsal copy, publish it as a pull request, and deliver it after approval.

**Depends on:** the credential and approval enforcement decisions.

**Exit gate:**

- A proposal becomes a pull request with evidence, and the worker never holds repository credentials.
- A deliberately unsafe patch is rejected even though its functional tests pass.
- Delivery applies only the approved commit to the approved target. A changed commit voids the approval.
- After delivery, the consumer gets its required records, forbidden records stay hidden, and writes stay denied.
- One supported rollback is demonstrated, along with what it cannot repair.

## 6. Operational and containment drills

Break the finished workflow on purpose.

**Exit gate:** recorded results, failures included, for:

- Worker and orchestrator interruption without duplicate changes.
- Duplicate findings without duplicate pull requests.
- Forbidden tool calls, storage reads, network connections, and policy edits from a worker.
- Instructions embedded in advisories and tool results.
- Forged and stale target evidence.
- Cleanup verification and measured resource use per investigation.

## 7. Exercise 2: excess network access

Same workflow, different change surface. Seed a target network rule that lets the unintended viewpoint in.

**Exit gate:**

- Probes from both viewpoints, before and after.
- The change touches only allowlisted target network fields.
- The consumer contract and the exercise 1 denials still hold.
- Outer containment is unchanged.

## 8. Exercise 3: vulnerable image or dependency

Pick a real advisory, an affected pinned artifact, and a reviewed fix before seeding anything.

**Exit gate:**

- An applicability record for the specific artifact. A version-string match is not enough.
- The update is rehearsed with database migration and a tested recovery procedure.
- The specific finding is reassessed after delivery. A clean generic scan is not enough.
- Results from exercises 1 and 2 still hold.

If no suitable affected and fixed artifact pair turns up, this exercise is recorded as not done. It does not get faked.

## Later options

- A Container Apps target and a Windows client target.
- More models, where measurement justifies them.
- A managed Kubernetes profile with more capacity.
