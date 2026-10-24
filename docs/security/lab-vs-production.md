# Lab against production

This page separates the controls intended for production from the lab's limitations. It explains why each limitation is accepted here, what risk it leaves, and what a production deployment would need.

It covers three areas:

- **Controls to keep.** Security controls to retain in production.
- **Lab limitations.** Accepted gaps and the changes needed for production.
- **Remaining risks.** Risks that production infrastructure alone cannot remove.

Synthetic data, a single operator, and rebuild procedures make some gaps acceptable in this lab. These reasons are not enough to accept the same gaps in production. Some choices below are planned rather than deployed; the [roadmap](../roadmap.md) records milestone status.

## What carries over

These controls are part of the design. Their current implementation and evidence are listed below.

| Control | State here |
| --- | --- |
| The AI worker is treated as compromised from the start. It holds no credential that grants access to a target or repository | Built. See [containment](../validation/containment.md) and the [credential inventory](credentials.md) |
| Deny by default on every subnet, with explicit denies for the internet, the targets, and DNS | Verified with traffic on the worker, and on the orchestrator since 2026-10-17 (`E.12` to `E.14`): [containment checks](../validation/containment.md). Verified with traffic from both targets since 2026-10-24 (`VN.13` to `VN.17`, `VL.13` to `VL.17`): [targets](../validation/targets.md) |
| No public address on any VM, enforced by a policy that neither deployment identity can change | Verified: [`Z.1` to `Z.3` and `Z.10` to `Z.12`](../validation/azure-policy.md), and the [identity separation test](../worklogs/0001-network-foundation.md#identity-separation) |
| One deployment identity per side, each unable to change the other | Verified by the [identity separation test](../worklogs/0001-network-foundation.md#identity-separation) |
| Every tool call authorized on the server, from a scope the caller cannot widen | Verified on the live system for a tool outside the job's scope and a revoked or expired token: [worklog](../worklogs/0003-toolchain-integration.md#the-round-trip). See [tool service](tool-service.md) |
| Read-only tools. A separate trusted runner applies approved changes | Built for one [evidence tool](tool-service.md), deployed. The runner is planned |
| Downloaded artifacts are pinned by digest and verified before use | Built, per artifact on the [supply chain](supply-chain.md) page |
| A target change requires an approved pull request | Built for the repository rules: [pipeline settings](../components/pipeline.md#repository-settings). Delivery is planned |
| Threats documented before implementation, with validation tied to each control | Decided in [ADR 0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md) |

## Lab limitations

The risk column describes what an attacker could do, or what could fail, because of each lab choice. Threat IDs refer to the [threat model](threat-model.md) and the [AI-specific threats](ai-threats.md).

### People and accounts

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| One person writes, approves, and operates | The lab has one operator | No independent approval. A stolen GitHub session can approve a malicious change (T15) | A separate approver, required review, and temporary privileged access |
| One Azure account owns both sides | Both sides share one subscription | Deployment identities are separated, but the owner controls both sides (T30) | Separate subscriptions and administrators |
| Deployment keys on a workstation | Terraform runs there | A stolen key grants control of one side until it expires, up to 91 days (T29) | Workload identity federation from a controlled runner, without a long-lived key |

### Access and network

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| Mesh VPN with a third-party coordination service | Private administration without public VM addresses or rules tied to the operator's IP address. Node signing is enabled | Availability depends on the provider. Its agent uploads logs by default (T01). Since 2026-10-17 the agent runs on a router VM with log upload off ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md), `R.5`). The vendor can still see which devices talk to which | A self-hosted control plane, or a VPN gateway or private circuit with a bastion |
| The orchestrator's way out is Squid on a small edge VM, with a hostname list and a fetch window | A managed firewall costs more than all the VMs together. Squid filters by hostname, and the window keeps upload hosts closed between builds ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)) | During a window the orchestrator can upload to an account of its own on a listed host (T40). TLS is not inspected. The edge is one more VM to patch, and a single point of failure | A firewall with TLS inspection, or an internal mirror and registry that the build side fills |
| State storage accounts accept connections from any network | Access is by identity, and shared keys are off | A stolen identity works from anywhere (T32) | Private endpoints, and no public network access |
| The worker downloads packages through an HTTP proxy limited to two public hosts | Package verification uses signed repository metadata. The proxy restricts hosts, methods, and ports | Requests can carry some data out, and the worker can attack the proxy (T17) | An internal package mirror |
| The targets get packages only during an update run the operator starts, through a port the orchestrator forwards. Decided on 2026-10-24. The platform side is built since 2026-10-24 (`P.23` to `P.29`), and the targets' update account since the same day (`VN.4` to `VN.12`, `VL.4` to `VL.12`). The update run is not ([ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)) | No standing path out of the target network for machines that are weak on purpose | A target is only as current as its last run (T09) | An internal package mirror inside the target network, with automatic updates |

### Compute and isolation

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| One K3s node, one VM per role | A quota of 4 vCPUs per region | No redundancy. A stuck job blocks the only worker (T20) | A highly available control plane across zones and multiple workers |
| One worker VM shared by consecutive jobs | No capacity for more | Agent files are cleaned up, but jobs share the kernel and model server memory (T19, A6) | A fresh sandbox or VM per job |
| The tool service runs in a container on the orchestrator | The lab has one trusted machine | A service vulnerability could expose the machine that holds the credentials (T22) | A sandboxed runtime or separate machine, plus independent code review |
| Credentials stored as files on the orchestrator and as Kubernetes Secrets, such as the dispatch key since 2026-10-21 | K3s secret encryption is enabled. One operator has root access | Root on the orchestrator can read them (T36) | A managed secret store, hardware-backed keys, and short-lived credentials |
| A small model, built on the worker from the publisher's weights | It fits in 8 GiB and keeps inference local | Investigation quality has not been evaluated (A3) | A model selected through evaluation, with request logging and appropriate data controls |

### Tool service and job identity

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| Job authentication uses a bearer token, issued per job by the dispatch step | Simple to issue, validate, and revoke | Anyone who reads the token can use the job's permissions until revocation or expiry (T18) | A credential restricted to the job's sandbox, such as a private key kept there for mutual TLS |
| One self-signed server certificate copied to the worker ([ADR 0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md)) | One server, with no certificate authority key to protect | Revocation requires replacing the certificate. Rotation requires a manual copy to the worker | An internal certificate authority with automatic issuance and renewal |
| Registration tokens are verified using a copied public key | The service needs no cluster credential or Kubernetes API connection | A deleted pod's token remains valid until expiry. A stale key copy stops registration | Automatic signing-key discovery and rotation, or mutual TLS between workloads |
| Jobs and call counts live in memory | The design uses one replica | A restart invalidates every job token. Replicas would have separate job records | A job store shared by replicas |

### Detection and response

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| Verified: tool audit logs stored on the orchestrator (`L` checks, [audit log](audit-log.md), [ADR 0019](../decisions/0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)) | No second trusted machine | Root on the orchestrator can edit them (T21). A rebuild of the orchestrator deletes them unless they are archived first. Since 2026-10-17 each line also reaches Azure Monitor, where no VM can change it ([monitoring](../components/monitoring.md)) | An append-only log store outside the platform |
| No audit daemon, no file integrity monitoring, and alerts nobody is sent | The audit daemon and integrity monitoring are planned for milestone 6. Logs reach Azure Monitor since 2026-10-17, and alert rules show in the portal since 2026-10-18, without notifications ([monitoring](../components/monitoring.md#alert-rules), [ADR 0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md)) | An alert at night is seen in the morning. Unauthorized changes the rules do not cover may go unnoticed | Central logging, integrity monitoring, alerts, and an on-call operator |
| Verified: the orchestrator pulls the worker's journal on a timer (`J` checks, [audit log](audit-log.md#the-workers-journal)) | Pushing logs would need another allowed connection from the worker | The worker can erase records created since the last pull. A rebuild of the orchestrator deletes the file unless it is archived first. Since 2026-10-17 the orchestrator's agent also sends each pulled line to Azure Monitor, where no VM can change it (`O.11`, [monitoring](../components/monitoring.md)) | Continuous log forwarding to storage the source cannot modify |
| The targets ship no logs: no log agent, and no path to the workspace (`VN.19`, `VL.19`) | No standing path out of the target network, and a weak target is expected to be compromised | What happens on a target is seen only on the target, and is lost with a rebuild. Operator sessions to the targets are not in the audit log yet (T04) | A log collector inside the target network, or a pull from the trusted side as for the worker |
| Lynis audit instead of the planned CIS benchmark | No tool has a CIS profile for the pinned OS release | No CIS benchmark result for the operating system | An OS release with a supported benchmark profile |
| Some version pins are updated manually | One operator and a short list | Software receives no security fix until its pin is updated | Automated update proposals and scheduled image rebuilds |

### Data, repository, and recovery

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| Public repository with synthetic evidence | No real target data is published | Real evidence could leak through proposal text in production (A5) | A private repository, data classification, and controls on pull request content |
| Locally redundant remote state; bootstrap state kept locally with a manual remote copy | The lab has rebuild runbooks | A missed upload leaves a stale backup. Restoration has not been tested (T31) | Geo-redundant remote state with tested recovery |
| Each VM rebuilt separately; no full-system rebuild | Each VM passed the validation checks after its rebuild | Recovery from an empty subscription has not been tested | Scheduled recovery exercises with a recovery time objective |

## What production does not fix

Production infrastructure alone does not remove these risks.

- **Prompt injection remains possible (A1).** The design limits what a compromised agent can do. It does not prevent malicious instructions from influencing the agent.
- **A convincing wrong answer can be approved (A3).** Evidence and rehearsal reduce the risk. Human review remains the final check.
- **A digest verifies an artifact, not its safety (T06, A4).** Pinning preserves malicious code as well as legitimate code. The initial choice still needs review.
- **Job authorization still needs project-specific policy (T16).** Production needs reviewed rules and tests for which jobs can call which tools.
- **The orchestrator remains a critical trust point (T05).** Outbound filtering and a secret store can limit a compromise and aid detection. They do not remove the orchestrator's authority to dispatch jobs and apply changes.

## If this went to production, in this order

1. **Independent approval and separate administrative accounts.** Reduce the authority of one operator or stolen session.
2. **Logs stored outside the platform, with alerts.** Preserve evidence if a platform machine is compromised.
3. **Outbound filtering on the orchestrator.** Restrict destinations to an explicit allowlist.
4. **A sandbox per job and a separate host for the tool service.** Limit shared state and access to orchestrator credentials.
5. **A secret store and an internal certificate authority.** Automate credential access and certificate renewal.

This is a proposed order, based on the impact of one mistake or stolen session. It is not a measured result or an agreed implementation plan.
