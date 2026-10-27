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
| Read-only tools. A separate trusted runner applies approved changes | Verified: the worker's one tool reads evidence, and delivery, a root command on the orchestrator host, applied an approved fix ([worklog](../worklogs/0006-remediation-pull-requests-and-delivery.md#one-fix-end-to-end)) |
| Downloaded artifacts are pinned by digest and verified before use | Built, per artifact on the [supply chain](supply-chain.md) page |
| A target change requires an approved pull request | Verified: delivery took a tag signed with the approval key, refused it when used again, and the pull request merged after ([worklog](../worklogs/0006-remediation-pull-requests-and-delivery.md#one-fix-end-to-end)) |
| Threats documented before implementation, with validation tied to each control | Decided in [ADR 0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md) |

## Lab limitations

The risk column describes what an attacker could do, or what could fail, because of each lab choice. Threat IDs refer to the [threat model](threat-model.md) and the [AI-specific threats](ai-threats.md).

### People and accounts

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| One person writes, approves, and operates | The lab has one operator | No independent approval. A stolen GitHub session can merge a malicious change, and the approval key on the same machine can approve its delivery (T15, T56) | A separate approver, required review, and temporary privileged access |
| One Azure account owns both sides | Both sides share one subscription | Deployment identities are separated, but the owner controls both sides (T30) | Separate subscriptions and administrators |
| Deployment keys on a workstation | Terraform runs there | A stolen key grants control of one side until it expires, up to 91 days (T29) | Workload identity federation from a controlled runner, without a long-lived key |

### Access and network

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| Mesh VPN with a third-party coordination service | Private administration without public VM addresses or rules tied to the operator's IP address. Node signing is enabled | Availability depends on the provider. Its agent uploads logs by default (T01). Since 2026-10-17 the agent runs on a router VM with log upload off ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md), `R.5`). The vendor can still see which devices talk to which | A self-hosted control plane, or a VPN gateway or private circuit with a bastion |
| The orchestrator's way out is Squid on a small edge VM, with a hostname list and a fetch window | A managed firewall costs more than all the VMs together. Squid filters by hostname, and the window keeps upload hosts closed between builds ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)) | During a window the orchestrator can upload to an account of its own on a listed host (T40). TLS is not inspected. The edge is one more VM to patch, and a single point of failure | A firewall with TLS inspection, or an internal mirror and registry that the build side fills |
| State storage accounts accept connections from any network | Access is by identity, and shared keys are off | A stolen identity works from anywhere (T32) | Private endpoints, and no public network access |
| The worker downloads packages through an HTTP proxy limited to two public hosts | Package verification uses signed repository metadata. The proxy restricts hosts, methods, and ports | Requests can carry some data out, and the worker can attack the proxy (T17) | An internal package mirror |
| The targets get packages only during an update run the operator starts, through a port the orchestrator forwards. Decided on 2026-10-24. The platform side is built since 2026-10-24 (`P.23` to `P.29`), the targets' update account since the same day (`VN.4` to `VN.12`, `VL.4` to `VL.12`), and the update run, which ran once on each target on 2026-10-24 (`U.14`, `U.15`, [worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-update-run), [ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)) | No standing path out of the target network for machines that are weak on purpose | A target is only as current as its last run (T09) | An internal package mirror inside the target network, with automatic updates |

### Compute and isolation

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| One K3s node, one VM per role | A quota of 4 vCPUs per region | No redundancy. A stuck job blocks the only worker (T20) | A highly available control plane across zones and multiple workers |
| One worker VM shared by consecutive jobs | No capacity for more | Agent files are cleaned up, but jobs share the kernel and model server memory (T19, A6) | A fresh sandbox or VM per job |
| The tool service runs in a container on the orchestrator | The lab has one trusted machine | A service vulnerability could expose the machine that holds the credentials (T22) | A sandboxed runtime or separate machine, plus independent code review |
| Credentials stored as files on the orchestrator and as Kubernetes Secrets, such as the dispatch key since 2026-10-21 | K3s secret encryption is enabled. One operator has root access | Root on the orchestrator can read them (T36) | A managed secret store, hardware-backed keys, and short-lived credentials |
| A stop fails the workflow, and the next try is a new job ([ADR 0041](../decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md)) | One worker. A workflow suspended for the operator would hold its lock, and every other job would wait | A right verdict in a form the comparison cannot read costs a whole job | A suspend the operator resumes or ends, with more than one worker, so that a stopped job holds none |
| A small model, built on the worker from the publisher's weights | It fits in 8 GiB and keeps inference local | On six held-out cases, 13 of 18 verdicts were the checks' ([evidence](../evidence/2026-10-25-2308-scored-cases.md)). A wrong one stops the workflow (A3) | A model selected through evaluation, with request logging and appropriate data controls |

### Tool service and job identity

| Lab choice | Reason in this lab | Risk | Production approach |
| --- | --- | --- | --- |
| Job authentication uses a bearer token, issued per job by the dispatch step | Simple to issue, validate, and revoke | Anyone who reads the token can use the job's permissions until revocation or expiry (T18) | A credential restricted to the job's sandbox, such as a private key kept there for mutual TLS |
| One self-signed server certificate copied to the worker ([ADR 0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md)) | One server, with no certificate authority key to protect | Revocation requires replacing the certificate. Rotation requires a manual copy to the worker | An internal certificate authority with automatic issuance and renewal |
| NetBox's TLS key and its self-signed certificate are made on the NetBox VM, and each client pins the certificate ([ADR 0038](../decisions/0038-netboxs-tls-key-made-on-the-netbox-vm.md)) | The key never leaves the VM, and there is no authority to protect | A new certificate breaks every client until each has the new copy. No rotation procedure is written | An internal certificate authority with automatic issuance and renewal |
| NetBox takes a client's address from the connection, with no proxy in front ([ADR 0039](../decisions/0039-netbox-takes-a-clients-address-from-the-connection.md)) | One service and one TLS endpoint, and a token's address limit that no header changes (`N.12`) | It rests on netbox-docker's module path and launch script, which an image move can change | A reverse proxy in front, as the only source NetBox takes the header from |
| The consumer's, the control account's, and the collector's NetBox tokens never expire. Each seed replaces them | One operator, and a seed per exercise | A copied token works until the next seed, from the address it is limited to | Tokens with an expiry, rotated by a job, from a secret store on each host |
| Registration tokens are verified using a copied public key | The service needs no cluster credential or Kubernetes API connection | A deleted pod's token remains valid until expiry. A stale key copy stops registration | Automatic signing-key discovery and rotation, or mutual TLS between workloads |
| Jobs and call counts live in memory | The design uses one replica | A restart invalidates every job token. Replicas would have separate job records | A job store shared by replicas |
| A job's evidence is collected by a command the operator runs on the orchestrator before the workflow, and stored in a config map the tool service mounts ([ADR 0040](../decisions/0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)). The checks' verdicts go into another, which only the comparison step mounts ([ADR 0041](../decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md)) | No pod reaches NetBox or the lab VM, and the collector's token stays on the host | A job starts only from a collection the operator ran, under a job ID the operator chose. A config map holds at most 1 MiB, so the command keeps the newest 20 jobs' keys | A collection step in the workflow, with its own identity and network path, and an evidence store per job outside the cluster's configuration |

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
| NetBox's database and cache passwords, secret key, and token pepper are in Podman's secret store on the NetBox VM, a plain file readable by root ([ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)) | Made on the VM, and never on another machine. A rebuild makes new ones, and the data is synthetic | Root on the VM reads every secret, and a disk snapshot holds them | A secret manager that issues them to the service, with rotation |
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
3. **An egress firewall with TLS inspection for the orchestrator.** The edge VM's host list sees names, not content.
4. **A sandbox per job and a separate host for the tool service.** Limit shared state and access to orchestrator credentials.
5. **A secret store and an internal certificate authority.** Automate credential access and certificate renewal.

This is a proposed order, based on the impact of one mistake or stolen session. It is not a measured result or an agreed implementation plan.
