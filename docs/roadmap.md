# Roadmap

Each milestone has completion criteria: things that must be shown to work, not things that must be built. A milestone is done when those criteria are met and the evidence is in a [worklog](worklogs/README.md). The design behind all of this is in the [architecture](architecture.md).

Security work has no milestone of its own. Each practice is part of the completion criteria for the milestone that builds what it checks, as decided in [ADR 0010](decisions/0010-threat-model-and-security-checks-per-milestone.md).

## Status

| Milestone | State |
| --- | --- |
| 0. Documentation baseline and preflight | Done. [Worklog](worklogs/0000-azure-preflight.md) |
| 1. Network foundation | Done, with one check carried to milestone 2. [Worklog](worklogs/0001-network-foundation.md) |
| 2. Platform compute | Done, with three stated gaps. No CIS result for the operating system, because no tool supports the release yet. Push protection is configured and not tested. No dependency update has been proposed yet. [Worklog](worklogs/0002-platform-compute.md) |
| 3. Toolchain integration | Done on 2026-10-24, with two stated gaps. Another job's evidence on the same target was not refused, because the tool service stored evidence per target ([#45](https://github.com/sindredg/ai-security-platform/issues/45)). Closed on 2026-10-25 for NetBox's target, on the live service: its evidence is stored per job ([ADR 0040](decisions/0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md), [worklog](worklogs/0005-netbox-target-and-exercise-1.md#evidence-per-job)). Root on the orchestrator can edit the audit file, the trusted machine by design. A workflow from the template hands a job to the worker, the agent calls the tool service with the job's token, and the checked result comes back to the workflow. Stopping a workflow ends its job and erases the model server's slot. Qwen3.5-4B stays the model ([ADR 0031](decisions/0031-qwen3-5-4b-stays-the-workers-model.md)), and the model gateway is dropped ([ADR 0034](decisions/0034-no-model-gateway-while-there-is-one-backend.md)). The claims were reviewed against the code and the running system on 2026-10-24. [Worklog](worklogs/0003-toolchain-integration.md) |
| 3a. Edge network and monitoring | Done on 2026-10-19, with two stated gaps. No login through the router to a target, because no target VM existed: closed on 2026-10-24 by `VN.1` and `VL.1` ([worklog](worklogs/0005-netbox-target-and-exercise-1.md#the-target-vms)). No connection test from the router to an operator device. A third, traffic analytics not processing the platform network's flow log, closed on 2026-10-21 ([worklog](worklogs/0003-toolchain-integration.md#fix-the-denied-flow-alert)). Built and on the live system: Squid on an edge VM as the orchestrator's only way out, a router VM as the only mesh VPN node, SSH certificates, the orchestrator hardening, the targets in Poland Central in their own repository, a required signature check, and logs in Azure Monitor over Private Link with alert rules, each fired once on purpose, the last on 2026-10-21. The daily log volume, the cap set from it, and the orchestrator's footprint with the log agent were measured over one day, to 2026-10-19. [Worklog](worklogs/0004-edge-network-and-monitoring.md) |
| 4. NetBox target and exercise 1 investigation | Started on 2026-10-24. ADRs [0035](decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md) to [0038](decisions/0038-netboxs-tls-key-made-on-the-netbox-vm.md) are accepted, and [0039](decisions/0039-netbox-takes-a-clients-address-from-the-connection.md) is proposed. [0040](decisions/0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md), where a job's evidence is collected and stored, is accepted. It is built and Verified on the live service on 2026-10-25: a command on the orchestrator collects one job's evidence, and the tool service refused a job another job's evidence and a document with an injected field ([worklog](worklogs/0005-netbox-target-and-exercise-1.md#evidence-per-job)). On the platform side, Squid's port for the targets' packages and its two rules are built ([worklog](worklogs/0005-netbox-target-and-exercise-1.md#the-targets-package-port)). The NetBox VM and the lab VM are built, with no way out, and checked by `VN`, `VL`, `HN`, `HL`, `Z.27`, and `Z.28` ([worklog](worklogs/0005-netbox-target-and-exercise-1.md#the-target-vms)). The update run is built, and installed NetBox's database, cache, and Podman on its VM ([worklog](worklogs/0005-netbox-target-and-exercise-1.md#the-update-run)). NetBox runs on its VM from the pinned image, checked on the orchestrator and on the VM, over TLS on port 8443 with a certificate the orchestrator pins, and reachable from the orchestrator and the consumer subnet only. ([worklog](worklogs/0005-netbox-target-and-exercise-1.md#netbox-on-its-vm)). It takes a client's address from the connection only. It holds exercise 1's seed, and the two deterministic checks, `N.14` and `N.17`, agree on the seeded excess and the unaffected control ([worklog](worklogs/0005-netbox-target-and-exercise-1.md#the-seed-and-the-two-checks)). The consumer contract is a file in the targets repository. The consumer's tokens are used only by the collector's observed half, for the checks and for a job's collection. Jobs have run on NetBox's evidence. The investigation is not scored: the workflow does not compare the model's verdict with the checks', and there are no held-out cases yet |
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

**Depends on:** the dispatch, job identity, and tool service decisions, made in ADRs [0012](decisions/0012-dispatch-over-ssh-with-a-forced-command.md), [0030](decisions/0030-how-a-job-reaches-the-worker.md), [0029](decisions/0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md), [0013](decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md), and [0014](decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md). Cloud identity for cluster workloads is not needed here and moves to milestone 4.

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

When the milestone started, the orchestrator held every credential that matters, reached any host on TCP 443 and 80 (T05), and was the mesh VPN node, beside the operator's devices. Running exercises on top of that, with nothing recording what happens, would test a platform that cannot show what an agent did. Milestone 3 resumes with dispatch once this is done.

**Depends on:** the decisions in ADRs [0020](decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) to [0025](decisions/0025-the-mesh-node-on-its-own-vm.md): the edge VM and its rules, monitoring in Azure Monitor, SSH certificates for the operator, a host rule for pod traffic to the host, the targets in their own repository, and the mesh node on a router VM. Three more records were written while it was built: [0026](decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md) for the feed key's account, [0027](decisions/0027-how-the-monitoring-is-built.md) for how the monitoring is built, and [0028](decisions/0028-alert-rules-flow-logs-and-drills.md) for the alert rules, flow logs, and drills. The subscription's quota cannot be raised, so the edge and the router take Denmark East's 4 vCPUs, and the targets move to Poland Central.

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

Define the consumer contract. Deploy NetBox, synthetic inventory, and the consumer. Seed the excess-permission finding and investigate it.

**Depends on:** decisions about the NetBox runtime ([ADR 0035](decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)), target package updates ([ADR 0036](decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)), and consumer permissions with the seeded finding ([ADR 0037](decisions/0037-an-unscoped-copy-of-the-consumers-permission.md)), all accepted on 2026-10-24. Where NetBox's TLS key is made changed the same day ([ADR 0038](decisions/0038-netboxs-tls-key-made-on-the-netbox-vm.md)). Where NetBox takes a client's address from was proposed on 2026-10-25 ([ADR 0039](decisions/0039-netbox-takes-a-clients-address-from-the-connection.md)). Where a job's evidence is collected and stored was decided the same day ([ADR 0040](decisions/0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)). Cloud identity for cluster workloads stays open: no collector in exercise 1 reads from Azure ([ADR 0013](decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md)).

**Completion criteria:**

- The consumer contract lists endpoints, fields, permitted records, and expected denials.
- Deterministic checks confirm the finding and a known unaffected case.
- Evidence is collected per job. The tool service refuses a job's call for another job's evidence on the same target ([#45](https://github.com/sindredg/ai-security-platform/issues/45)), and hands the model only the fields its schema names ([#152](https://github.com/sindredg/ai-security-platform/issues/152)).
- The investigation is scored as a dispatched job, through the workflow, on held-out cases. The hash of the case file is committed before the first scored run.
- The AI investigation cites tool evidence for each conclusion, and says so when evidence disagrees. Conclusions without tool evidence are counted.
- The workflow compares the model's verdict with the deterministic checks. A mismatch, an inconclusive verdict, or a failed job stops the workflow for the operator. A match and a stop are each shown, with evidence from that job only.
- A baseline without AI, using the same tools, is recorded for comparison. A usefulness rubric, written before the runs, scores both, and operator effort and elapsed time are measured for both. The result is recorded whichever way it falls. It is not a pass gate.
- Every image on the target side is pinned by digest. Signatures are verified where upstream signs.

## 5. Remediation, pull requests, and delivery

Rehearse a proposed fix on the rehearsal copy, publish it as a pull request, and deliver it after approval.

**Depends on:** the credential and approval enforcement decisions.

**Completion criteria:**

- A proposal becomes a pull request with evidence, and the worker never holds repository credentials.
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
