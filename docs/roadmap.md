# Roadmap

Each milestone has completion criteria: things that must be shown to work, not things that must be built. A milestone is done when those criteria are met and the evidence is in a [worklog](worklogs/README.md). The design behind all of this is in the [architecture](architecture.md).

Security work has no milestone of its own. Each practice is part of the completion criteria for the milestone that builds what it checks, as decided in [ADR 0010](decisions/0010-threat-model-and-security-checks-per-milestone.md).

## Status

| Milestone | State |
| --- | --- |
| 0. Documentation baseline and preflight | Done. [Worklog](worklogs/0000-azure-preflight.md) |
| 1. Network foundation | Done, with one check carried to milestone 2. [Worklog](worklogs/0001-network-foundation.md) |
| 2. Platform compute | Done, with three stated gaps. No CIS result for the operating system, because no tool supports the release yet. Push protection is configured and not tested. No dependency update has been proposed yet. [Worklog](worklogs/0002-platform-compute.md) |
| 3. Toolchain integration | In progress. The model server runs on the worker, and the agent runtime runs headless against it with a fixture tool. The tool service runs on the orchestrator and has answered tool calls from the worker with a job token. The audit lines and the worker's journal are copied to append-only files on the orchestrator. No workflow or dispatch step exists yet. Paused for milestone 3a. [Worklog](worklogs/0003-toolchain-integration.md) |
| 3a. Edge network and monitoring | Planned. Starts when milestone 3 pauses |
| 4. NetBox target and exercise 1 investigation | Planned |
| 5. Remediation, pull requests, and delivery | Planned |
| 6. Operational and containment drills | Planned |
| 7. Exercise 2: excess network access | Planned |
| 8. Exercise 3: vulnerable image or dependency | Planned |

## 0. Documentation baseline and preflight

Write down the design and the first decisions, and get account-specific evidence for regions and sizes before anything depends on them.

**Completion criteria:** the architecture, roadmap, and first decision records are published. The preflight worklog records quota and VM size evidence for both regions.

## 1. Network foundation

Create the state storage and both Terraform roots. Provision resource groups, virtual networks, subnets, network security groups, and peering. No compute yet.

The point of doing this first is to prove the separation before there is anything to separate.

**Completion criteria:**

- `terraform plan` is clean for both roots after apply.
- Peering state is `Connected` in both directions.
- Effective rules show default deny between the networks, with only the documented flows allowed.
- The target root's identity cannot modify platform resources, and the reverse.

**Result:** met, except that effective rules cannot be read without a network interface. The configured rules are verified. The effective-rule check moves to milestone 2.

## 2. Platform compute

Provision the orchestrator and AI worker VMs. Install K3s. Set up the mesh VPN, the egress path, and the public address policy.

**Depends on:** the egress decision, made in [ADR 0009](decisions/0009-one-egress-point-on-the-orchestrator-subnet.md), and the first pass of the [threat model](security/threat-model.md).

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

Deploy Argo Workflows, the agent runtime, and the model server. Prove the round trip from a workflow to the worker and back, on synthetic evidence only.

This is where the design is most likely to be wrong, so it comes before any target exists.

**Depends on:** the dispatch, job identity, and tool service decisions, made in ADRs [0012](decisions/0012-dispatch-over-ssh-with-a-forced-command.md), [0013](decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md), and [0014](decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md). Cloud identity for cluster workloads is not needed here and moves to milestone 4.

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

Implemented in `tool-service/tests/`, with the service. The tool service is the one piece of custom code that reads what a compromised worker sends ([ADR 0014](decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)). These cases are unit tests that live beside its code and run in the pipeline. They are not drills, and they do not add to the milestone's completion criteria: those criteria demonstrate the round trip on the running system, and the tests keep the edges from moving afterwards.

Every case ends the same way: the call is refused, nothing of the result goes back, and one audit line records the decision and the reason.

| Group | Case |
| --- | --- |
| Malformed arguments | A body that is not JSON, or not valid UTF-8 |
| | A missing field, a wrong type, and a field the schema does not name |
| | An evidence reference with `..`, an absolute path, or a null byte |
| | A tool name that no policy lists |
| Cross-job access | A valid token for one job asks for another job's evidence |
| | A valid token asks for a tool or a target outside its job's scope |
| | The arguments name a different job than the token. The token decides |
| Tokens | No token, a malformed token, and a token nobody issued |
| | An expired token, and a token revoked when its job ended |
| | A refusal never puts the token in the response or the log |
| Oversized requests | A body over the size limit, refused before it is parsed |
| | A result over the size limit, and one call more than the job's call limit |
| Concurrent cancellation | A job is cancelled while its call is in flight. The result is dropped, not delivered late |
| | Two calls race the revocation. None succeeds after it |
| | The same job is cancelled twice, or registered twice. Neither is an error that leaves a live token |

## 3a. Edge network and monitoring

Move the platform's way out and its mesh VPN node off the orchestrator, and send every log to a store outside the machines it describes. Comes between the log copies of milestone 3 and its dispatch work.

The orchestrator holds every credential that matters and reaches any host on TCP 443 and 80 (T05). It is also the mesh VPN node, beside the operator's devices. Running exercises on top of that, with nothing recording what happens, would test a platform that cannot show what an agent did. Milestone 3 resumes with dispatch once this is done.

**Depends on:** decisions about the edge VM and its rules, monitoring in Azure Monitor, SSH certificates for the operator, and a host rule for pod traffic to the host. A regional limit of 6 vCPUs in Sweden Central, for the edge VM.

**Completion criteria:**

- The orchestrator reaches the internet only through the edge proxy, and only the hosts on its list. A request for another host is refused and logged.
- Only the edge resolves public names. The orchestrator's queries to Azure DNS are refused.
- The orchestrator is not on the mesh VPN. The operator reaches the orchestrator, the worker, and the targets through the edge.
- Neither the orchestrator nor the edge can open a connection to an operator device. The mesh policy's own tests refuse a change that would allow it.
- The Kubernetes API is not reachable over the mesh VPN.
- Operator SSH logins use certificates that expire within a day. A key without a certificate is refused.
- A pod reaches the host only on the ports the host rule lists, from its first packet.
- Every namespace rejects a privileged pod, whether or not it has a pod security label.
- Requests to the tool service without a valid token are rate-limited.
- The audit lines, the worker's journal, and the edge's logs reach a log store that no VM can delete from, without passing through the internet.
- A stopped log agent, a gap in the audit sequence, a missed journal pull, a refused outbound request, and a change to a security group or role assignment each raise an alert in the Azure portal. Each was triggered once on purpose.
- Flow logs are recorded for the platform subnets.
- Log volume per day is measured, and a daily cap is set from it.
- The orchestrator's memory and CPU use with the log agent are measured.

## 4. NetBox target and exercise 1 investigation

Define the consumer contract. Deploy NetBox, synthetic inventory, and the consumer. Seed the excess-permission finding and investigate it.

**Depends on:** decisions about the NetBox version, consumer permissions, cloud identity for cluster workloads ([ADR 0013](decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md)), and target package updates ([ADR 0011](decisions/0011-package-proxy-for-the-worker.md)).

**Completion criteria:**

- The consumer contract lists endpoints, fields, permitted records, and expected denials.
- Deterministic checks confirm the finding and a known unaffected case.
- The AI investigation cites tool evidence for each conclusion, and says so when evidence disagrees.
- A baseline without AI, using the same tools, is recorded for comparison.
- Every image on the target side is pinned by digest. Signatures are verified where upstream signs.

## 5. Remediation, pull requests, and delivery

Rehearse a proposed fix on the rehearsal copy, publish it as a pull request, and deliver it after approval.

**Depends on:** the credential and approval enforcement decisions.

**Completion criteria:**

- A proposal becomes a pull request with evidence, and the worker never holds repository credentials.
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

Every threat rated high in the threat model maps to one of these drills or to a stated accepted risk. A high threat with neither is a gap, and the milestone stays open.

## 7. Exercise 2: excess network access

Same workflow, different change surface. Seed a target network rule that lets the unintended viewpoint in.

**Completion criteria:**

- Probes from both viewpoints, before and after.
- The change touches only allowlisted target network fields.
- The consumer contract and the exercise 1 denials still hold.
- Outer containment is unchanged.
- The threat model is rechecked for the new change surface.

## 8. Exercise 3: vulnerable image or dependency

Pick a real advisory, an affected pinned artifact, and a reviewed fix before seeding anything.

**Completion criteria:**

- An applicability record for the specific artifact, backed by its SBOM. A version-string match is not enough.
- The update is rehearsed with database migration and a tested recovery procedure.
- The specific finding is reassessed after delivery. A clean generic scan is not enough.
- Results from exercises 1 and 2 still hold.
- The threat model is rechecked for the new change surface.

If no suitable affected and fixed artifact pair turns up, this exercise is recorded as not done. It does not get faked.

## Later options

- A Container Apps target and a Windows client target.
- More models, where measurement justifies them.
- A managed Kubernetes profile with more capacity.
