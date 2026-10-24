# Architecture

This page describes the current system and its planned design. The network foundation and platform VMs are deployed: state storage, deployment identities, the platform, target, and edge virtual networks, security groups, peerings, one NAT gateway, the orchestrator with K3s, the AI worker, the router with the mesh VPN, the edge VM with Squid, and a Log Analytics workspace reached over a private endpoint, with its alert rules.

A workflow on the orchestrator hands each investigation to the AI worker over SSH. The agent there reads evidence only through the tool service on the orchestrator, with a token for that one job, and its result comes back to the workflow, checked. Only the orchestrator reaches the targets. Each section distinguishes implemented controls, decisions, and open work. What each milestone has built is in the [roadmap](roadmap.md#status).

The reasoning behind each choice is in the [decision records](decisions/README.md). The order of work is in the [roadmap](roadmap.md).

## Purpose

Finding a misconfiguration is only the start. The real work is proposing a fix that removes the problem without breaking the people who depend on the service, and proving that before anyone approves it.

That is what this platform does, for a service it does not host:

- Tools collect evidence and establish facts: configured access, observed reachability, deployed versions.
- AI workers read the evidence, ask for more through narrow tools, and propose a change within defined limits.
- A trusted runner rehearses the change on a disposable copy of the target.
- A pull request carries the change and its evidence to the operator.
- After approval, a trusted delivery step applies it, and fresh collection checks the result.

This is an infrastructure project. The work is Terraform, Kubernetes operations, model hosting, identity, networking, isolation, and drills. Existing software supplies the workflow engine, the agent runtime, and the user interfaces. Custom code stays small: collectors, adapters, and enforcement checks.

### Why the model runs inside the platform

The model is open-weight and runs on CPU on the AI worker. There is no external model API, for three reasons:

- **The evidence stays inside.** Findings, target configuration, and tool output never reach a model vendor. A model with no internet path has nowhere to send what it reads.
- **Every layer under the agent is the project's.** The operating system, the network rules, the model server, and the model are configured here and checked here, not taken on a provider's word.
- **The model can change.** Swapping it, tuning its settings, or fine-tuning it needs no vendor's terms or quota.

The cost is quality and speed. A small model on 2 vCPUs proves the integration, and says little about how good or fast an investigation can be ([limitations](#limitations)).

## System overview

![Architecture: a trusted orchestrator VM holds the secrets and has no direct internet access. It and the AI worker reach the internet only through a proxy on an edge VM. A router VM is the only mesh VPN node, logs go to Azure Monitor over a private endpoint, and the targets in Poland Central are reached only from the orchestrator](diagrams/target-architecture.svg)

The diagram shows the design after milestone 3a ([0020](decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md), [0021](decisions/0021-monitoring-in-azure-monitor-over-private-link.md), [0025](decisions/0025-the-mesh-node-on-its-own-vm.md)). The router, the edge VM, the log store, and the alert rules are built. Status is in the [roadmap](roadmap.md).

Note the dotted line from the AI worker: it ends at a stop bar. The worker cannot reach the target region at all. Everything it knows about the target, it was handed by a tool service on the orchestrator.

The orchestrator box hides four groups of components. They are listed under [Orchestrator](#orchestrator), and the order they act in is under [Workflow](#workflow).

## Platform and target separation

The platform holds the credentials and rules that decide what may change. The target is deliberately weak and gets rebuilt often. Putting them in the same Terraform configuration, network, or permission scope would let a mistake in one reach the other.

They share an Azure subscription, with separate Terraform roots, state, resource groups, networks, and deployment identities. See [ADR 0002](decisions/0002-separate-platform-and-target-infrastructure.md).

| Aspect | Platform | Targets |
| --- | --- | --- |
| Purpose | Orchestration, tools, AI workers, inference | The service under investigation and its lab fixtures |
| Region | Sweden Central | Poland Central. The resource groups and the state account are in Denmark East ([ADR 0020](decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)) |
| Terraform root | `infra/platform/` | `infra/targets/` in the [targets repository](https://github.com/sindredg/ai-security-platform-test) ([ADR 0024](decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)) |
| Terraform state | Own storage account, own access scope | Own storage account, own access scope |
| Resource groups | `rg-aisec-platform`, `rg-aisec-platform-state` | `rg-aisec-targets`, `rg-aisec-targets-state` |
| Virtual network | `10.40.0.0/20` | `10.50.0.0/20` |
| Deployment identity | `aisec-platform-deploy`, platform scope only | `aisec-targets-deploy`, target scope only |
| Lifecycle | Long-lived | Rebuilt and reseeded per exercise |
| Intentional weaknesses | None | Seeded per exercise, inside outer containment |

![Two sides, two identities: the bootstrap root creates each side, each identity holds roles on its own resource group and state, and the only cross-side permission is the peering action](diagrams/separation.svg)

Separate folders prove nothing. The boundary is real only where state permissions, role assignments, network rules, and separate credentials enforce it.

That has been tested. Each deployment identity was denied every read and write it tried on the other side's network, resource group, and state. See the [network foundation worklog](worklogs/0001-network-foundation.md#identity-separation).

A third root, `infra/bootstrap`, sits above both. The operator runs it, and it owns what a scoped identity cannot create for itself: the resource groups, the state accounts, the identities, and their role assignments. Each identity authenticates with a certificate whose private key never enters Terraform. See [ADR 0008](decisions/0008-deployment-identities-and-bootstrap-scope.md).

The boundary has one deliberate hole. Each identity may name the other side's network as a peering partner, through a custom role with that single action. It cannot read or change that network.

Two rules follow:

- **A target change never touches the platform.** A remediation can modify allowlisted target fields. Platform Terraform, policies, workflows, and CI are out of its reach.
- **Containment is not a target setting.** The rules that keep the lab private belong to the platform side. No target change can remove them, approved or not.

## Network

### Address plan

Deployed. Every subnet has its own network security group and no default outbound access.

| Range | Region | Use |
| --- | --- | --- |
| `10.40.0.0/20` | Sweden Central | Platform virtual network |
| `10.40.0.0/27` | Sweden Central | Orchestrator subnet |
| `10.40.0.32/27` | Sweden Central | AI worker subnet |
| `10.50.0.0/20` | Poland Central | Target virtual network |
| `10.50.0.0/27` | Poland Central | NetBox subnet |
| `10.50.0.32/27` | Poland Central | Authorized consumer viewpoint |
| `10.50.0.64/27` | Poland Central | Unintended viewpoint (exercise 2) |
| `10.50.1.0/27` | Poland Central | Rehearsal copy |
| `10.42.0.0/16`, `10.43.0.0/16` | In cluster | K3s default pod and service ranges, never routed between networks |

The edge network, `10.45.0.0/24` in Denmark East, holds the router subnet `10.45.0.32/27` with the router at `10.45.0.36`, built on 2026-10-17 ([ADR 0025](decisions/0025-the-mesh-node-on-its-own-vm.md), [worklog](worklogs/0004-edge-network-and-monitoring.md#the-router)), and the edge subnet `10.45.0.0/27` with the edge VM at `10.45.0.4`, built the same day ([ADR 0020](decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md), [worklog](worklogs/0004-edge-network-and-monitoring.md#the-edge-vm)). The platform network also holds `10.40.0.64/27`, the private endpoint for Azure Monitor, built on 2026-10-17 ([ADR 0021](decisions/0021-monitoring-in-azure-monitor-over-private-link.md), [monitoring](components/monitoring.md)). It takes TCP 443 from the orchestrator, the edge, and the router, and starts nothing.

### Connectivity

Global virtual network peering joins the networks: platform to targets, platform to edge, and edge to targets (`Z.15`, `Z.18`, `Z.24`). Peering is plumbing, not a filter: once it exists, everything can route to everything. Network security groups on both sides deny by default and allow only what is listed here.

Each security group ends in a deny-all rule in both directions at priority 4096. That rule is the point: Azure's built-in rules allow everything inside the `VirtualNetwork` tag, and peering puts the other network inside that tag.

The table is the design. Rules exist for what is built: SSH from the orchestrator subnet to the worker and to the target network, SSH from the router subnet to the orchestrator, the worker, the edge, and the target network, the tool service port from the worker to the orchestrator, the proxy port from the orchestrator and the worker to the edge, TCP 443 from the orchestrator, the edge, and the router to the monitoring private endpoint, and outbound internet access from the router and the edge. The other allowed flows get their rules with the service that listens on them. The denied flows are enforced now.

| Source | Destination | Purpose | State |
| --- | --- | --- | --- |
| Orchestrator subnet | NetBox subnet | Evidence collection, approved delivery | Allowed, fixed ports |
| Orchestrator subnet | Viewpoint and rehearsal subnets | Start named probes and rehearsals | Allowed, fixed ports |
| Orchestrator subnet | AI worker subnet | Artifact transfer and job dispatch, both over SSH | Allowed, TCP 22 |
| AI worker subnet | Orchestrator subnet | The tool service | Allowed, TCP 30443 |
| Orchestrator and AI worker subnets | Edge subnet | Squid: packages, and the orchestrator's fetches during a fetch window | Allowed, TCP 3128 |
| Orchestrator, edge, and router subnets | Monitoring subnet | The log agents, to Azure Monitor's private endpoint | Allowed, TCP 443. The subnet starts nothing |
| AI worker subnet | Target network | None | Denied, by an explicit rule on the platform side |
| AI worker subnet | Internet | None. The orchestrator pushes what the worker needs | Denied, by an explicit rule on the platform side |
| Orchestrator subnet | Internet, and Azure DNS | None. It fetches through Squid on the edge | Denied, by explicit rules on the platform side (`E.12` to `E.14`, `Z.22`) |
| Router subnet | Internet | The mesh VPN's coordination service and relays, packages | Allowed, through the edge network's NAT gateway: TCP 443 and 80 |
| Edge subnet | Internet | Squid's upstream requests | Allowed, through the same NAT gateway: TCP 443 and 80. Squid decides which hosts |
| Router subnet | Platform network, edge subnet, target network | Routed operator sessions | Allowed, TCP 22 |
| Any other source | Edge subnet | None | Denied. Only TCP 3128 from two subnets and TCP 22 from the router are allowed in (`Z.21`) |
| Any subnet | Router subnet | None | Denied. The router has no inbound allow (`Z.17`) |
| Target network | Internet | None. The orchestrator pushes what the targets need | Denied, by explicit rules and by a policy that refuses public IP resources on the target side |
| Target network | Platform network | None | Denied for new connections, by an explicit rule on the platform side |
| Operator device | Router, then other VMs | Administration over the mesh VPN | Allowed for the operator's devices, on SSH only. The Kubernetes API through an SSH tunnel to the orchestrator |
| Internet | Any | None | Denied inbound |

An allowed route is not authorization. Every allowed flow still needs application authentication and TLS.

### Administrative access

No VM has a public address. The operator gets in over a mesh VPN: a router VM runs the agent and nothing else, and routes to the platform network, the target network, and the edge subnet. The orchestrator is not on the mesh. No firewall rule names an operator address, because none is needed. Detail: [mesh VPN](components/mesh-vpn.md).

On every VM, the administrator account takes only an SSH certificate that expires after 12 hours ([ADR 0022](decisions/0022-short-lived-ssh-certificates-for-the-operator.md), [worklog](worklogs/0004-edge-network-and-monitoring.md#rollout-1)). The orchestrator's feed key logs in to an account of its own on the worker, which can only unpack staged files ([ADR 0026](decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)). Since 2026-10-17 the agent runs on a router VM that no subnet can reach ([ADR 0025](decisions/0025-the-mesh-node-on-its-own-vm.md), [worklog](worklogs/0004-edge-network-and-monitoring.md#the-router)).

### Egress

The system has one way out: a NAT gateway in the edge network, used by the router and the edge VM. The orchestrator, the worker, and the targets each have three controls that block outbound access, because any one alone leaves a path open: no outbound method, explicit deny rules, and Azure Policy assigned outside both roots.

The orchestrator and the worker reach the internet only through Squid on the edge VM ([ADR 0020](decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md), [worklog](worklogs/0004-edge-network-and-monitoring.md#the-edge-vm)). The worker gets two Ubuntu package hosts. The orchestrator gets its own package mirror at all times, and a tunnel to the build and deploy hosts only while the operator holds a fetch window open on the edge. The orchestrator is still the only machine that downloads anything for the worker and the targets. The targets get no path.

Detail: [egress and policy](components/egress-and-policy.md), [package proxy](components/package-proxy.md).

## Platform

### Orchestrator

One K3s server on one VM runs everything that is trusted. It has no way out of its own: it fetches through Squid on the edge VM. Detail: [orchestrator](components/orchestrator.md), [K3s](components/k3s.md).

### AI worker

The agent runtime and the model server run on a second VM that is not part of the cluster. The worker reads advisories, target evidence, and tool output. Any of those can carry malicious instructions. The design assumes the worker can be compromised and restricts its access:

- No delivery credentials, no repository credentials, no privileged cloud identity.
- One scoped session per job: one target, one evidence set, bounded time and output.
- One network destination for work: the tool services on the orchestrator.

The cost is dispatch. Argo runs pods, not processes on another machine. A workflow step opens an SSH session to the worker with a key that can only run the job runner, and the runner hands the job to a socket that starts the agent's sandboxed unit. Decided in [ADR 0012](decisions/0012-dispatch-over-ssh-with-a-forced-command.md) and [ADR 0030](decisions/0030-how-a-job-reaches-the-worker.md). Both sides are built and ran together on 2026-10-21: a workflow's step dispatched a job that called a tool, and a stopped workflow ended its job ([worklog](worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows)). Detail: [AI worker](components/ai-worker.md).

What exists today is narrower than the design. A job investigates synthetic evidence through one tool, `get_evidence`, for one target, `synthetic`: the dispatch step registers no other. The fixture tool on the worker is left for the measurement runs the operator starts by hand, outside dispatch. See the [milestone 3 worklog](worklogs/0003-toolchain-integration.md).

### Components

What is built, what is planned, and every version pin are in [components](components/README.md).

## Targets

The first target is NetBox with synthetic inventory. See [ADR 0004](decisions/0004-netbox-as-first-target.md).

| Fixture | Role |
| --- | --- |
| NetBox VM | The protected service: NetBox and its background worker from one image pinned by digest, under Podman, with PostgreSQL and Valkey from Ubuntu on the VM's loopback ([ADR 0035](decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)) |
| Authorized consumer | Reads one synthetic tenant's devices and IP addresses through the REST API, with a read-only token limited to its address. The contract is a file in the targets repository ([ADR 0037](decisions/0037-an-unscoped-copy-of-the-consumers-permission.md)) |
| Unintended viewpoint | A controlled source that policy says must not reach NetBox |
| Rehearsal copy | A disposable NetBox with its own synthetic data and credentials |

The consumer, both viewpoints, and the rehearsal copy share one lab VM, with one network interface per viewpoint subnet. That is a capacity compromise, explained under [Capacity](#capacity).

NetBox is the thing being investigated. It is never a source of truth for the platform. The platform's target registry, permissions, and approval policy do not come from anything NetBox returns.

### Exercises

Three exercises, in this order, on the same service and the same consumer contract.

| Order | Finding | Correct outcome | Change surface |
| --- | --- | --- | --- |
| 1 | The consumer can read inventory outside its approved scope | Required reads still work, other records are gone | NetBox permission configuration |
| 2 | NetBox is reachable from the unintended viewpoint | The consumer keeps access, the unintended source is blocked | Target network rules |
| 3 | A pinned image or dependency is affected by a real public advisory | A vetted update removes the condition and keeps data and the consumer contract intact | Pinned image definition and update procedure |

The easy way to pass a security check is to break the service. So a fix that locks out the legitimate consumer fails, and validation checks the inventory the consumer actually gets back, not a health endpoint.

## Workflow

![Investigation to delivery: trusted orchestrator steps, one untrusted AI worker step, and one operator approval](diagrams/workflow.svg)

1. Collection runs on a schedule or on request and produces validated evidence snapshots.
2. Deterministic checks establish configured access, observed reachability, and candidate findings.
3. A workflow fixes the job scope: target, evidence, tools, time and output limits.
4. An AI worker investigates and asks for more evidence through tool services.
5. The worker proposes a change, limited to allowlisted fields or a vetted procedure.
6. A trusted runner rehearses the change on the rehearsal copy and runs fixed tests.
7. The broker opens a pull request with the change, the evidence, and what remains uncertain.
8. The operator approves the exact commit and target.
9. The delivery runner re-checks policy and applies the change.
10. Fresh collection verifies the outcome. Cleanup retires the session and temporary resources.

Models explain and propose. Tools establish facts. A confident model does not authorize a change, and neither does a green test.

A proposal goes ahead only when the model's verdict agrees with the deterministic checks. A disagreement, an inconclusive verdict, or a failed job stops the workflow for the operator to look at. A wrong verdict then costs the operator a look instead of a wrong pull request, and no verdict closes a finding the checks found.

## Trust boundaries

| Component | Trust | Reason |
| --- | --- | --- |
| Cloud provider, platform administrator | Trusted | Accepted baseline. A privileged provider compromise is a risk this design documents and does not mitigate |
| Orchestrator and its workflow templates | Trusted | Fixed, and not writable by workers |
| AI worker, model output | Untrusted | Assumed compromisable. Limited by network, credentials, and tool-side checks |
| Target, guest reports, API responses | Untrusted | A compromised target can forge its own evidence |
| Advisories, tool results, proposed patches | Untrusted input | Can carry instructions or unsafe changes |

What follows from that:

- Every tool call is authorized on the server: caller, job scope, target, operation, arguments. Hiding a tool from the model is not access control.
- Target evidence is compared with what the repository, the cloud API, and the network say. When they disagree, the disagreement is recorded. The model does not get to pick a winner.
- Approval binds to a commit and a target. Change the proposal and the approval is void.
- Private payloads stay in protected storage. Workflow parameters and logs carry references.
- The repository is public. Pull requests carry synthetic data and sanitized summaries. State, raw plans, and secrets never enter them.

## Security practices

The method is in [ADR 0010](decisions/0010-threat-model-and-security-checks-per-milestone.md). The State column records implementation and validation evidence.

The table above says who is trusted. The [threat model](security/threat-model.md) says what can go wrong at each boundary, what stops it, and where that gets tested. Its first pass was written before any VM existed.

Everything else is attached to the milestone that builds the thing it checks. A practice without a gate has no check that it was done.

| Practice | What it covers | Lands with | State |
| --- | --- | --- | --- |
| Threat model | Threats per trust boundary, AI-specific threats, the control for each, residual risk, and the gap between this lab and production | Before platform compute, then updated with each decision | First pass written on 2026-10-11, and revised with each milestone and decision since. Its status line lists the revisions ([threat model](security/threat-model.md)) |
| Repository protection | Secret scanning with push protection, and a protected `main`. The repository is the approval channel, so this is a system control | Platform compute | Built. Secret scanning, push protection, and a ruleset on `main`. Required checks are documented in the [pipeline page](components/pipeline.md#repository-settings). Verified: a required check that every commit in a pull request is signed by the operator's key blocks a commit GitHub signed ([worklog](worklogs/0004-edge-network-and-monitoring.md#the-fail-side-on-github), [0024](decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)). The targets repository has the same settings and check, verified the same way on 2026-10-17 ([pipeline](components/pipeline.md#the-targets-repository)) |
| Static checks on pull requests | Terraform and manifest misconfigurations, leaked secrets. No cloud credentials in the pipeline | Platform compute | Built. The [pipeline page](components/pipeline.md#checks-on-every-pull-request) lists the checks and which are required. Tested on 2026-10-17: Trivy fails a security group rule that allows SSH from any source, and Checkov passes it ([#99](https://github.com/sindredg/ai-security-platform/issues/99), [worklog](worklogs/0004-edge-network-and-monitoring.md#the-security-group-rules-in-the-scanners)). Built on 2026-10-18: the network module refuses that rule at plan, for both roots once the target pin moved ([targets PR 6](https://github.com/sindredg/ai-security-platform-test/pull/6)), and its test runs on every pull request ([worklog](worklogs/0004-edge-network-and-monitoring.md#open-issues-fixed-before-the-review)) |
| Dependency updates | Automated pull requests that move the version pins | Platform compute | Configured. No update has been proposed yet. From milestone 3a, each proposal is redone by the operator, because the [signature check](components/pipeline.md#the-signature-check) refuses commits GitHub signs |
| Hardening baselines | CIS benchmarks for the operating system and Kubernetes | Platform compute | Run again on 2026-10-19 on the current VMs: kube-bench on the cluster, with one fail accepted and one not explained ([#127](https://github.com/sindredg/ai-security-platform/issues/127)), and Lynis on all four VMs, with its warnings triaged ([hardening](security/hardening.md#benchmarks)). kube-bench ran again on 2026-10-23 with the same result, and its warnings were read one by one ([hardening](security/hardening.md#the-kube-bench-warnings)). No tool has a CIS profile for Ubuntu 26.04 yet, which is an accepted risk |
| Credential inventory | Every secret: where it lives, what can read it, how it is rotated | Platform compute, then every milestone | Current on 2026-10-24, with the target credentials that ADRs 0035 and 0037 decide. Each row says whether its rotation procedure has been run, and most have not ([inventory](security/credentials.md)). The dispatch SSH key and the Argo tokens are in use since 2026-10-21. The executor's token does not expire |
| Audit log | Every tool call with caller, job, and decision, out of the worker's reach | Toolchain integration | Verified for audit output: the live tool service printed one JSON entry per decision, with no token ([worklog](worklogs/0003-toolchain-integration.md#the-round-trip)). Verified for storage on 2026-10-16: a host unit copies the lines into an append-only file on the orchestrator, `L.1` to `L.7` pass, and each was seen to fail, on a broken condition or before the install ([worklog](worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)). Verified on 2026-10-17: the orchestrator's log agent sends each line to Azure Monitor, where no VM holds a role (`O.1`, `O.8` to `O.12`, [worklog](worklogs/0004-edge-network-and-monitoring.md#monitoring)). Root on the orchestrator can still edit the file before the agent reads it ([audit log](security/audit-log.md)) |
| Supply chain | Digest pins, signature checks where upstream signs, an SBOM where an exercise needs one | Toolchain integration, target deployment, exercise 3 | Per artifact on the [supply chain](security/supply-chain.md) page. Built for the files of the model server and the agent runtime, checked against pinned checksums on the orchestrator. Verified for the images the project builds and for Argo's, by `T.2`, `W.2`, and `W.9`, and for the installed Goose binary, by `G.1`. Argo's images are pinned only after their cosign signatures are checked, and llama.cpp's and Goose's provenance was checked once before the pin. K3s's system images come from the release's archive, held by `K.11`. Decided on 2026-10-24 for the target: the NetBox image pinned by digest, unsigned upstream ([ADR 0035](decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)). There is no SBOM |
| Monitoring | Logs and alerts kept outside the machines they describe | Edge network and monitoring | Built on 2026-10-17 and 2026-10-18: agents on the orchestrator, the edge, and the router send to Azure Monitor over Private Link, and alert rules show in the portal, each fired once on purpose, the last `denied-flow-to-internet` on 2026-10-21 (`O.1` to `O.17`, [monitoring](components/monitoring.md)). The daily cap is set from a day measured on 2026-10-19, and holds for a day with the first jobs in it, read on 2026-10-24 with 4.29 MB to spare ([worklog](worklogs/0003-toolchain-integration.md#the-daily-volume-with-jobs-in-it)) |
| Incident response runbook | A compromised worker or target, a leaked credential | Operational drills | Planned |

There is no compliance framework here. ISO 27001 and SOC 2 describe an organisation, and this one has a single operator.

## Identity

- **Operator:** Microsoft Entra ID sign-in through supported OIDC integrations, with no premium identity features assumed. One person investigates and approves. That is not separation of duties, and the project does not claim it is.
- **Workloads:** collector, tool service, broker, delivery runner, and worker each have their own permissions. Delivery and repository credentials exist only in the `change` namespace.
- **Jobs:** each job gets a random token at dispatch, scoped to one target and a list of tools, and revoked when the job ends. Decided in [ADR 0013](decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md). The tool service registers jobs, validates tokens, and revokes jobs, tested on the live system. The dispatch step makes the token for each workflow since 2026-10-21. Detail: [tool service and job identity](security/tool-service.md).
- **Cloud access from K3s:** none, and still open. Workload identity federation on a self-managed cluster needs publicly reachable OIDC issuer metadata and public signing keys, which can be hosted separately from the cluster. A VM managed identity is simpler but is available to every process on that VM. Toolchain integration needs no cloud access, so the choice waits for the first workload that does. See [ADR 0013](decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md).

## Capacity

The subscription allows 4 vCPUs per region and has no GPU quota. Both are treated as fixed. Quota counts VMs that exist, not VMs that run, so deallocating a VM frees nothing. Evidence is in the [preflight worklog](worklogs/0000-azure-preflight.md).

That gives two VMs per region, with nothing to spare. The limit cannot be raised for this subscription type. The targets are in Poland Central. The edge and the router are in Denmark East ([ADR 0020](decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md), [ADR 0025](decisions/0025-the-mesh-node-on-its-own-vm.md)). The table shows today's placement.

| Region | VM | vCPUs | Size | State |
| --- | --- | --- | --- | --- |
| Sweden Central | Orchestrator | 2 | `Standard_B2as_v2` (8 GB) | Built. The regional quota is full |
| Sweden Central | AI worker | 2 | `Standard_D2ps_v6` (Arm, 2 physical cores, 8 GB) | Built |
| Denmark East | Router | 2 | `Standard_B2ats_v2` (1 GB) | Built on 2026-10-17 |
| Denmark East | Edge | 2 | `Standard_B2als_v2` (4 GB) | Built on 2026-10-17. The regional quota is full |
| Poland Central | NetBox | 2 | `Standard_B2as_v2` (8 GB), candidate, zone 3 | Planned |
| Poland Central | Lab | 2 | `Standard_B2as_v2` (8 GB), candidate, zone 3 | Planned |

Idle use of the orchestrator and the worker is on their [component pages](components/README.md). Where it will hurt:

- **Inference.** Two x64 vCPUs are one physical core. Arm sizes give two real cores for the same quota, at the price of arm64 builds for everything on the worker.
- **The orchestrator.** It carries K3s, Argo, collectors, tool services, and the change components. There is no model gateway while there is one model backend ([ADR 0034](decisions/0034-no-model-gateway-while-there-is-one-backend.md)). Monitoring is in Azure Monitor, so the orchestrator carries only a log agent: about 410 MiB with page cache and under half a percent of one core, read on 2026-10-24 ([worklog](worklogs/0003-toolchain-integration.md#orchestrator-footprint)). Across 15.3 hours to 2026-10-24, the whole machine's CPU averaged 3.3 %, and its available memory never fell below 5,389 of 7,881 MB ([worklog](worklogs/0003-toolchain-integration.md#orchestrator-footprint)).
- **Concurrency.** One investigation at a time, one loaded model.

## Repository layout

`.github/`, `infra/`, `platform/`, `edge/`, `worker/`, `tool-service/`, `policies/`, `validation/`, and `docs/` exist. Every other directory appears with the milestone that needs it. The target Terraform root is in the [targets repository](https://github.com/sindredg/ai-security-platform-test), and NetBox, its fixtures, and the consumer contract go there in milestone 4 ([ADR 0024](decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)).

```text
.github/            Static checks on pull requests, the signature check, dependency update configuration
infra/bootstrap/    Operator-run root: resource groups, state accounts, deployment identities
infra/modules/      Shared Terraform modules
infra/platform/     Platform Terraform root
platform/           What the orchestrator runs: K3s manifests, the log copiers, the monitoring hosts script, the dispatch step's image, and Argo with the workflow template
edge/               The fetch window command and its host list, installed on the edge VM
worker/             What the orchestrator copies to the AI worker: pins, build scripts, service units
tool-service/       The MCP server that checks every tool call, its tests, and its pinned packages
policies/           Target, tool, and change rules. Today: the tool service's
collectors/         Planned: collection and adaptation scripts
validation/         Checks against the running system. Contract tests and drills come later
docs/               Architecture, components, decisions, diagrams, runbooks, security, troubleshooting, validation, worklogs
```

## Open decisions

Each gets a decision record before the milestone that depends on it.

| Decision | Needed before |
| --- | --- |
| Cloud identity for K3s workloads | A collector that reads from Azure. None does in exercise 1 ([ADR 0037](decisions/0037-an-unscoped-copy-of-the-consumers-permission.md)) |
| Worker isolation beyond VM separation | Connecting real target evidence |
| GitHub App permissions and approval enforcement | Remediation and pull requests |
| Acceptance thresholds for quality, recovery, and cost | Operational drills |

The target's runtime, how the targets get packages, and the consumer's scope with exercise 1's seeded finding were decided on 2026-10-24 in ADRs [0035](decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md), [0036](decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md), and [0037](decisions/0037-an-unscoped-copy-of-the-consumers-permission.md).

## Limitations

- One K3s node and single VMs. A VM failure stops that part of the system.
- A small model on CPU proves the integration works. It says little about investigation quality or speed.
- One operator. There is no multi-user access model, and nobody else reviews a change. Automated checks are the only second reader.
- A separate VM limits what a compromised worker can reach. It does nothing against a compromised host or provider.
- Both roots use the same network module. A change to it reaches both sides, so the separation is in state, identity, and network rules, not in the code.
- The public address policy leaves one gap on the platform side. It refuses a public address on a network interface in both resource groups, and any public IP resource on the target side. Both are assigned from the bootstrap root and [validated](worklogs/0002-platform-compute.md#public-address-policy). The platform identity can still create a public IP resource in its own group, because the NAT gateway needs one. It cannot attach it to a machine.
- The orchestrator's way out is filtered by hostname, not by content. During a fetch window it can upload to an account of its own on a listed host, and TLS is not inspected (T40).
- The edge VM carries every outbound fetch and the router every operator session. Either one down stops that, and the way in is then Azure run command, which needs the Owner account. The serial console offers no login, because no account has a password (T03).
- The [threat model](security/threat-model.md) is a first pass, written by the designer. The controls on the network, the VMs, and the repository are verified or built. Most of the rest are written, decided, or planned, and its [open items](security/accepted-risks.md#open-items) have no answer yet.
