# Roadmap

Each milestone has completion criteria: things that must be shown to work, not things that must be built. A milestone is done when each criterion is tested or an accepted gap, with the evidence in its [worklog](worklogs/README.md). The design is in the [architecture](architecture.md).

Security work has no milestone of its own. Each practice is part of the criteria for the milestone that builds what it checks ([ADR 0010](decisions/0010-threat-model-and-security-checks-per-milestone.md)).

## Status

| Milestone | State | Open gaps | Evidence |
| --- | --- | --- | --- |
| 0. Documentation baseline and preflight | Done | None | [Worklog](worklogs/0000-azure-preflight.md) |
| 1. Network foundation | Done | None. The effective rules were tested in milestone 2 | [Worklog](worklogs/0001-network-foundation.md) |
| 2. Platform compute | Done | Accepted gap: no tool has a CIS profile for Ubuntu 26.04. Configured, not tested: an update pull request for a provider or an action | [Worklog](worklogs/0002-platform-compute.md) |
| 3. Toolchain integration | Done | Accepted gap: every job on `synthetic` reads one fixed file. Root on the orchestrator, trusted by design, can edit the audit file before the log agent sends it | [Worklog](worklogs/0003-toolchain-integration.md) |
| 3a. Edge network and monitoring | Done | Configured, not tested: a connection from the router to an operator device. The mesh policy's own tests refuse one | [Worklog](worklogs/0004-edge-network-and-monitoring.md) |
| 4. NetBox target and exercise 1 investigation | Done | Accepted gap: no case whose documents disagree ([#205](https://github.com/sindredg/ai-security-platform/issues/205)). An inconclusive verdict stopped a workflow in tests only | [Worklog](worklogs/0005-netbox-target-and-exercise-1.md), [evidence](evidence/README.md) |
| 5. Remediation, pull requests, and delivery | Done | Pipeline tests only: a wider fix refused. Configured, not tested: the copy's routing at first boot. Accepted gap: no held-out case has a fix left to propose ([#220](https://github.com/sindredg/ai-security-platform/issues/220)) | [Worklog](worklogs/0006-remediation-pull-requests-and-delivery.md), [evidence](evidence/README.md) |
| 6. Operational and containment drills | In progress | Accepted gap: no VM rebuilt from its current template, so its first boot is untested ([worklog](worklogs/0007-operational-and-containment-drills.md#summary)) | [Worklog](worklogs/0007-operational-and-containment-drills.md) |
| 7. Exercise 2: excess network access | Planned | | |
| 8. Exercise 3: vulnerable image or dependency | Planned | | |

## 0. Documentation baseline and preflight

Write down the design and the first decisions, and get account-specific evidence for regions and sizes before anything depends on them.

**Completion criteria:** the architecture, roadmap, and first decision records are published. The preflight worklog records quota and VM size evidence for both regions.

## 1. Network foundation

Create the state storage and both Terraform roots. Provision resource groups, virtual networks, subnets, network security groups, and peering. No compute yet, so the separation is proven before there is anything to separate.

**Completion criteria:**

- `terraform plan` is clean for both roots after apply.
- Peering state is `Connected` in both directions.
- Effective rules show default deny between the networks, with only the documented flows allowed.
- The target root's identity cannot modify platform resources, and the reverse.

## 2. Platform compute

Provision the orchestrator and AI worker VMs. Install K3s. Set up the mesh VPN, the egress path, and the public address policy.

**Depends on:** the egress decision ([ADR 0009](decisions/0009-one-egress-point-on-the-orchestrator-subnet.md)) and the first pass of the [threat model](security/threat-model.md).

**Completion criteria:**

- Both VMs are reachable over the mesh VPN and have no public address.
- Effective rules on each network interface match the configured rules, and the denied paths are tested with traffic. Carried over from milestone 1.
- K3s comes back healthy after a VM restart.
- The worker cannot open a connection to the target network or the internet, and cannot resolve a public name.
- A public address on a network interface is refused by policy in both workload resource groups.
- Idle CPU and memory use on both VMs is measured.
- Every credential this milestone creates is in the credential inventory. Each long-lived one has a rotation procedure that has been run once.
- Hardening benchmark results for the operating system and K3s are recorded. Each failed check is fixed or accepted with a reason.
- `main` takes changes only through a pull request with passing checks, and a pushed secret is refused.
- Pull requests run static checks on the Terraform and a secret scan. The pipeline holds no cloud credentials.
- Version pins for providers and pipeline actions get automated update pull requests.

## 3. Toolchain integration

Deploy Argo Workflows, the agent runtime, and the model server. Prove the round trip from a workflow to the worker and back, on synthetic evidence only. This is where the design is most likely to be wrong, so it comes before any target exists.

**Depends on:** the dispatch, job identity, and tool service (an MCP server) decisions, in ADRs [0012](decisions/0012-dispatch-over-ssh-with-a-forced-command.md), [0013](decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md), [0014](decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md), [0029](decisions/0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md), and [0030](decisions/0030-how-a-job-reaches-the-worker.md).

**Completion criteria:**

- A workflow starts a worker job, the agent calls one authorized tool, and a schema-checked result comes back.
- A tool call for another job or target is refused by the tool service.
- Cancelling a workflow stops the worker job and cleans up its session.
- Model memory use, latency per turn, and tokens per second are measured on the chosen size.
- Component footprint on the orchestrator is measured. Deferred components go in or get dropped based on it.
- The threat model covers dispatch, workload identity, and the AI-specific threats. Each threat rated high has a control or a stated acceptance.
- Every image and every input to the model file is pinned by digest and verified on the orchestrator before it runs or is pushed. The model file itself is built on the worker ([ADR 0015](decisions/0015-build-the-model-file-on-the-worker.md)).
- Every tool call, allowed or refused, is logged with caller, job, and decision. The worker cannot write to or delete that log.
- A revoked or expired job token is refused.
- A pod in a workload namespace cannot open a connection to the internet.
- The worker's journal is copied to the orchestrator on a schedule.

If a candidate needs a substantial custom service to meet these criteria, replace it or simplify the design. Don't build the service.

### Hostile-input tests for the tool service

The tool service's rejection cases are unit tests beside its code, run on every pull request, and listed on the [tool service](security/tool-service.md#hostile-input-tests) page. They keep the edges from moving, and do not add to the criteria.

## 3a. Edge network and monitoring

Move the platform's way out and its mesh VPN node off the orchestrator, and send every log to a store outside the machines it describes. Exercises on a platform that cannot show what an agent did would prove little.

**Depends on:** ADRs [0020](decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) to [0028](decisions/0028-alert-rules-flow-logs-and-drills.md). The quota cannot be raised, so the edge and the router take Denmark East's 4 vCPUs, and the targets move to Poland Central.

**Completion criteria:**

- The orchestrator reaches the internet only through the edge proxy, and only the hosts on its list. A request for another host is refused and logged.
- Only the edge resolves public names. The orchestrator's queries to Azure DNS are refused.
- The orchestrator is not on the mesh VPN. The operator reaches the orchestrator, the worker, the edge, and the targets through the router.
- The mesh agent runs only on the router, with its own updates and its log upload off. No subnet can open a connection to the router.
- A check fails when the mesh agent is behind the current stable release.
- The router cannot open a connection to an operator device. The mesh policy's own tests refuse a change that would allow it.
- The Kubernetes API is not reachable over the mesh VPN.
- Operator SSH logins use certificates that expire within a day. A key without a certificate is refused.
- A pod reaches the host only on the ports the host rule lists, from its first packet.
- Every namespace rejects a privileged pod, whether or not it has a pod security label.
- Requests to the tool service without a valid token are rate-limited.
- The audit lines, the worker's journal, and the edge's and the router's logs reach a log store that no VM can delete from, without passing through the internet.
- A stopped log agent, a gap in the audit sequence, a missed journal pull, a refused outbound request, and a change to a security group or role assignment each raise an alert in the Azure portal. Each was triggered once on purpose.
- Flow logs are recorded for the platform subnets.
- The target network is in Poland Central, defined in its own repository. A commit to the platform repository that the operator's key did not sign fails a required check.
- Log volume per day is measured, and a daily cap is set from it.
- The orchestrator's memory and CPU use with the log agent are measured.

## 4. NetBox target and exercise 1 investigation

Define the access specification. Deploy NetBox, synthetic inventory, and the consumer. Seed the over-privilege finding and investigate it.

**Depends on:** ADRs [0035](decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md) to [0042](decisions/0042-held-out-cases-and-the-baseline-without-the-agent.md). Cloud identity for cluster workloads stays open, because no collector in exercise 1 reads from Azure ([ADR 0013](decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md)).

**Completion criteria:**

- The access specification, each consumer's least privilege, lists endpoints, fields, permitted records, and expected denials.
- Deterministic checks confirm the finding and a known unaffected case.
- Evidence is collected per job. The tool service refuses a job's call for another job's evidence on the same target ([#45](https://github.com/sindredg/ai-security-platform/issues/45)), and hands the model only the fields its schema names ([#152](https://github.com/sindredg/ai-security-platform/issues/152)).
- The investigation is scored as a dispatched job, through the workflow, on held-out cases. The hash of the case file is committed before the first evaluation (eval) run.
- The AI investigation cites tool evidence for each conclusion, and says so when evidence disagrees. Conclusions without tool evidence are counted.
- The workflow compares the model's verdict with the deterministic checks. A mismatch, an inconclusive verdict, or a failed job stops the workflow for the operator. A match and a stop are each shown, with evidence from that job only.
- A baseline without AI, using the same tools, is recorded for comparison. A usefulness rubric, written before the runs, scores both, and operator effort and elapsed time are measured for both. The result is recorded whichever way it falls, and is not a pass gate.
- Every image on the target side is pinned by digest. Signatures are verified where upstream signs.

## 5. Remediation, pull requests, and delivery

Test a proposed fix on the staging copy, publish it as a pull request, and deliver it after approval.

**Depends on:** ADRs [0043](decisions/0043-proposals-are-remove-only-and-a-policy-check-decides.md) to [0047](decisions/0047-a-delivery-token-for-each-delivery.md), decided, and the inline steps of [0048](decisions/0048-the-workflows-steps-are-inline-so-no-workflow-runs-one-alone.md), so that no workflow skips the verification gate.

**Completion criteria:**

- A remediation proposal becomes a pull request with evidence, and the worker never holds repository credentials.
- An investigation that stopped for the operator opens no pull request.
- A deliberately unsafe patch is rejected even though its functional tests pass.
- Delivery applies only the approved commit to the approved target. A changed commit voids the approval.
- After delivery, the consumer gets its required records, forbidden records stay hidden, and writes stay denied.
- One supported rollback is demonstrated, along with what it cannot repair.
- The threat model covers the pull request and delivery path, including the repository credentials.

## 6. Operational and containment drills

Break the finished workflow on purpose.

**Completion criteria:** recorded results, failures included, for:

- Worker and orchestrator interruption without duplicate changes.
- Duplicate findings without duplicate pull requests.
- Forbidden tool calls, storage reads, network connections, and policy edits from a worker.
- Instructions embedded in advisories and tool results.
- Forged and stale target evidence.
- Cleanup verification and measured resource use per investigation.
- The incident response runbook, run for a compromised worker, a compromised target, and a leaked credential.
- An audit daemon and file integrity monitoring on both VMs, with a drill that shows each one catching something.
- A rebuild of each VM from the current templates, with every manual step recorded.
- Operator sessions to the targets in the audit log (T04). Carried over from milestone 4.
- The KV-cache clear after a job that timed out ([#199](https://github.com/sindredg/ai-security-platform/issues/199)). Carried over from milestone 4.

Every threat rated high in the threat model maps to one of these drills or to a stated accepted risk. A high threat with neither is a gap, and the milestone stays open.

## 7. Exercise 2: excess network access

Same workflow, different change surface. Seed a target network rule that lets the unintended viewpoint in.

**Completion criteria:**

- Probes from both viewpoints, before and after.
- The change touches only allowlisted target network fields.
- The access specification and the exercise 1 denials still hold.
- Outer containment is unchanged.
- The threat model is rechecked for the new change surface.

## 8. Exercise 3: vulnerable image or dependency

Pick a real advisory, an affected pinned artifact, and a reviewed fix before seeding anything.

**Completion criteria:**

- An applicability record for the specific artifact, backed by its SBOM. A version-string match is not enough.
- The update gets a staging test, with database migration and a tested recovery procedure.
- The specific finding is reassessed after delivery. A clean generic scan is not enough.
- Results from exercises 1 and 2 still hold.
- The threat model is rechecked for the new change surface.

If no suitable affected and fixed artifact pair turns up, this exercise is recorded as not done. It does not get faked.

## Later options

- A Container Apps target and a Windows client target.
- More models, where measurement justifies them.
- A managed Kubernetes profile with more capacity.
