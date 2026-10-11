# Threat model

Status: first pass, written 2026-10-11 against the design. Only the network foundation is built, so most controls here are decided or planned, not verified. Each row says which.

This document lists what can go wrong at each trust boundary, what stops it, where that gets proven, and what is left over. The method and the reason for doing it now are in [ADR 0010](decisions/0010-threat-model-and-security-checks-per-milestone.md). The system it describes is in the [architecture](architecture.md).

## What the first pass found

Five things stand out. None is fixed by this document.

1. **The tool services are the wall.** Every limit on the AI worker ends at one service on the trusted machine that reads hostile input. That service is not designed yet, and neither is the way it tells one job from another. See T16, T18, T22.
2. **The repository is the approval channel and is unprotected.** `main` accepts a force push today. Until that changes, "approval binds to a commit" has nothing to stand on. See T10.
3. **The operator is a single point of total compromise.** One Azure account owns both sides. One GitHub account approves every change. The design constrains automation, not that person. See T15, T30.
4. **A proposal is a data path to a public page.** The worker reads evidence and writes text that ends up in a pull request. Nothing decided so far checks what that text carries. See A5.
5. **A compromised orchestrator is the end.** It holds every credential that matters and can reach any host on port 443. This is accepted, not solved. See T05.

## Scope and method

In scope: the platform, the targets, the repository, and the Azure control plane as the project uses it.

Out of scope: a compromise of Azure, GitHub, or the mesh VPN provider from the inside. The design trusts them and says so. A stolen operator account on any of them is in scope.

Also out of scope: the operator's workstation. This project is the infrastructure, and how the operator's machine is secured is the operator's business. The model covers what a key taken from that machine can reach, not how it is kept.

The method has two passes:

- **STRIDE per boundary.** Spoofing, tampering, repudiation, information disclosure, denial of service, elevation of privilege, asked at each of the six crossings below.
- **AI-specific threats.** Checked against the OWASP Top 10 for LLM Applications, the OWASP Top 10 for Agentic Applications for 2026, and MITRE ATLAS 5.6.0. OWASP LLM entries are cited by name, because their numbers differ between editions.

Ratings are a judgment, not a score:

| Rating | Meaning |
| --- | --- |
| High | Reaches a credential, changes the platform or a target without approval, or breaks containment |
| Medium | Produces a wrong result or an outage that the design detects |
| Low | Limited effect, or needs another failure first |

Control states:

| State | Meaning |
| --- | --- |
| Verified | Built, and tested with evidence in a worklog |
| Decided | Recorded in a decision record, not built |
| Planned | In a roadmap gate, with no design yet |
| Open | Depends on a decision that has not been made |
| Accepted | No control. The risk is carried on purpose |

## Assets

| Asset | Why it matters |
| --- | --- |
| Delivery and repository credentials | Whoever holds them can change a target or publish as the platform |
| Deployment keys and the Owner account | They can rebuild or remove either side |
| Approval | The only thing that authorizes a change. Worth exactly as much as the commit it names |
| Containment | The rules that keep a deliberately weak target away from everything else |
| Evidence | Findings and fixes are only as good as the evidence under them |
| Workflow templates, policies, and tool definitions | They decide what a worker may ask for |
| The audit log | Without it, a refused call and a call that never happened look the same |

All target data is synthetic. Its confidentiality is not an asset in this lab. It would be the main one in production.

## Attackers

| Attacker | Starts with |
| --- | --- |
| Turned AI worker | Code execution on the worker VM, through injected instructions or a poisoned model |
| Compromised target | Control of NetBox or the lab VM, which is the expected state of a weak target |
| Content author | An advisory, a package, an image, or a model that the platform fetches |
| Repository attacker | A pull request from a fork, a hijacked pipeline action, or a stolen GitHub session |

## Trust boundaries

![Trust boundaries: six numbered crossings between the operator, the trusted orchestrator, the untrusted AI worker, the targets, GitHub, the internet, and the Azure APIs](diagrams/trust-boundaries.svg)

The diagram source is [`diagrams/trust-boundaries.html`](diagrams/trust-boundaries.html).

| Boundary | Crossing | What crosses |
| --- | --- | --- |
| B1 | Operator to orchestrator, over the mesh VPN | Shells, the workflow interface |
| B2 | Orchestrator to the internet, through the NAT gateway | Packages, images, the model, security feeds, mesh VPN control traffic |
| B3 | Platform to GitHub | Pull requests out, approvals in |
| B4 | Orchestrator to AI worker and back | Job dispatch out, tool calls and results back |
| B5 | Orchestrator to targets | Collection, probes, rehearsal, approved delivery |
| B6 | Operator to the Azure APIs | Terraform runs, state, role assignments, policy |

## Threats

"Gate" names the roadmap milestone whose exit gate proves the control. A threat with no gate is listed under [open items](#open-items).

### B1. Operator access

| ID | Threat | STRIDE | Rating | Control | State | Gate | Residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T01 | A device that is not the operator's joins the mesh, through a stolen login or the provider adding a node | S, E | High | Access policy limited to the operator's devices. SSH key authentication on every VM regardless. Node signing, so the provider alone cannot add a device | Decided, node signing not yet | 2 | The mesh login is a second factor on top of SSH, not a replacement |
| T02 | The mesh auth key leaks and enrolls a rogue router | S | High | Single-use, short-lived, tagged key. Dead once the orchestrator has enrolled | Planned | 2 | The key is readable in instance metadata until it expires |
| T03 | The orchestrator is down and there is no way in | D | Medium | Serial console and run-command through the Azure APIs | Decided | 2 | Break-glass needs the Owner account |
| T04 | An operator session to a target cannot be told from a collector by address | R | Low | Separate ports and credentials. Sessions recorded in the audit log | Planned | 3 | Attribution rests on the log |

### B2. Egress and downloads

| ID | Threat | STRIDE | Rating | Control | State | Gate | Residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T05 | A compromised orchestrator sends anything to any host on port 443 | I | High | None at the network. Nothing untrusted runs on the orchestrator | Accepted | None | Total. Filtering by hostname costs a firewall |
| T06 | A fetched image, package, binary, or install script is malicious | T, E | High | Pinned by digest and verified on the orchestrator before it runs or is pushed. Signatures checked where upstream signs | Decided | 3, 4 | A digest proves identity, not innocence. The first pin is trusted on sight |
| T07 | A fed machine leaks data through DNS lookups | I | High | Explicit deny for the Azure DNS service tag on the worker and target subnets | Decided | 2 | None known |
| T08 | A fed machine reaches a storage account in its own region without any gateway | I | High | Explicit deny for the internet tag, next to the missing outbound path | Decided | 2 | On the target side the deny is a target setting. See T25 |
| T09 | The package forward is a live internet path while it is open | I, E | Medium | Opened only from the orchestrator, only with no job running and no target seeded. Otherwise rebuild | Decided | 2 | Anything already on that machine can use it for the duration |

### B3. Repository and approval

| ID | Threat | STRIDE | Rating | Control | State | Gate | Residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T10 | A force push or direct push changes `main`, or the commit under an approval | T | High | Ruleset on `main`: pull request required, no force push, checks required | Planned | 2 | A repository administrator can lift the ruleset |
| T11 | An approval for one commit is used to deliver another | T, E | High | Approval binds to commit and target. The delivery runner re-checks both | Planned | 5 | Rests on the delivery runner being correct |
| T12 | The broker's repository credential is stolen | S, E | High | It exists only in the `change` namespace. The worker never holds it. Minimal app permissions | Open | 5 | Depends on the permissions decision |
| T13 | A secret or a real identifier lands in the public repository | I | High | Push protection and a secret scan. State, plans, and local configuration are ignored by Git | Planned | 2 | Scanners know patterns. An account ID is not a pattern |
| T14 | A hijacked pipeline action or a fork pull request runs hostile code in the pipeline | T, E | Medium | No secrets in the pipeline, a read-only token, actions pinned by commit | Decided | 2 | It can still report a false pass |
| T15 | The operator's GitHub account is taken over | S | High | Strong sign-in on the account | Accepted | None | The attacker approves whatever they like. There is no second approver |

### B4. AI worker

| ID | Threat | STRIDE | Rating | Control | State | Gate | Residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T16 | A turned worker calls a tool outside its job: another target, another operation | E | High | Every call authorized on the server by caller, job, target, operation, and arguments | Planned | 3, 6 | The policy check is custom code |
| T17 | The worker reaches a target or the internet directly | E, I | High | Deny rules on the platform side, plus no outbound path | Verified as configured. Traffic test pending | 2 | None known once tested |
| T18 | The worker presents itself as another job or caller | S | High | A credential scoped to one job, issued at dispatch | Open | 3 | Depends on the dispatch decision |
| T19 | Files, cache, or session state from one job reach the next | I | Medium | One session per job. Cleanup tested, not assumed | Planned | 3, 6 | Jobs share a VM and a kernel |
| T20 | The worker never finishes, or floods the tool services | D | Medium | Time and output limits per job. One job at a time | Planned | 3, 6 | A stuck job blocks the only worker |
| T21 | The worker edits or deletes the record of its own calls | R | High | The log is written on the orchestrator, where the worker has no access | Planned | 3 | None known |
| T22 | The worker exploits a bug in a tool service and lands on the orchestrator | E | High | Only tool service ports are open from the worker subnet. SSH runs the other way only. Hardening baseline on the cluster | Open | 3 | A parsing bug in a tool service is a direct path to the trusted side |

### B5. Targets

| ID | Threat | STRIDE | Rating | Control | State | Gate | Residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T23 | A compromised target reports false evidence | S, T | High | Target evidence is compared with the repository, the cloud API, and the network. Disagreement is recorded | Planned | 4, 6 | A lie that every source agrees with |
| T24 | A target attacks the collector through a crafted response | E | High | New connections from targets to the platform are denied. Collector output is schema-checked | Deny verified as configured. Rest planned | 2, 4 | Collectors parse hostile data on the trusted machine |
| T25 | The target side removes its own containment | T | High | Azure Policy outside both roots refuses public addresses. Worker-side denies live in the platform root | Decided | 2 | The target-side denies for DNS and same-region storage stay target settings |
| T26 | Delivery changes more than was approved, or the wrong target | T | High | Allowlisted fields only. Approved commit, approved target | Planned | 5, 7 | Rests on the allowlist being right |
| T27 | A fix clears the finding and breaks the consumer | D | Medium | Rehearsal against the consumer contract before the pull request, and again after delivery | Planned | 4, 5 | The contract covers what it lists and nothing else |
| T28 | A seeded weakness is reachable from outside the lab | I | Medium | No public address anywhere, enforced by policy | Decided | 2 | None known |

### B6. Build and control plane

| ID | Threat | STRIDE | Rating | Control | State | Gate | Residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T29 | A deployment key is used by someone other than the operator | S, E | High | Each key reaches one side only. A certificate is valid for at most 91 days | [Verified](worklogs/0001-network-foundation.md#identity-separation) | 1 | Full control of one side until the certificate is removed or expires. How the key is stored is out of scope |
| T30 | The Owner account is taken over | S, E | High | Strong sign-in on the account | Accepted | None | Total. The separation does not bind that role |
| T31 | The bootstrap state is lost | D | Low | Everything in it can be imported again | Accepted | None | An afternoon of imports |
| T32 | State is read and gives up sensitive values | I | Medium | Entra authentication, shared keys off, one identity per account. Secrets kept out of Terraform | Verified | 1 | The accounts accept connections from any network |
| T33 | One side's identity changes the other side | E | High | Role assignments scoped to one side | [Verified](worklogs/0001-network-foundation.md#identity-separation) | 1 | The peering action, which carries no traffic alone |
| T34 | A change to the shared network module reaches both sides unnoticed | T | Medium | Each root's plan is read before its apply. Static checks on pull requests | Planned | 2 | One reader |
| T35 | A secret in VM custom data is read from instance metadata | I | Medium | No secret in custom data on a fed machine | Decided | 2 | The orchestrator's enrollment key. See T02 |
| T36 | A workload on the cluster reaches the `change` namespace credentials | E | High | Per-workload permissions and a hardening baseline. Namespaces are not treated as a wall | Open | 3 | Depends on the workload identity decision |

## AI-specific threats

The design's answer to most of these is the same: assume the attack works, and make sure a turned worker holds nothing and reaches nothing.

| ID | Threat | Reference | Rating | Control | State | Gate | Residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | Instructions hidden in an advisory, a tool result, or target evidence take over the agent | OWASP LLM: Prompt Injection. ASI01. ATLAS AML.T0051.001 | High | Not prevented. Contained by T16 to T18, by allowlisted change fields, by rehearsal, and by approval | Planned | 6 | The agent's output is untrusted every time, injected or not |
| A2 | The agent uses a legitimate tool for something its job does not need | OWASP LLM: Excessive Agency. ASI02, ASI03. ATLAS AML.T0053, AML.T0101 | High | Narrow tools with no destructive operations. Delivery belongs to a separate trusted runner | Planned | 3, 6 | A tool that reads too much is still a tool that reads |
| A3 | The model is wrong and convincing, and the operator approves it | OWASP LLM: Misinformation. ASI09 | High | Tools establish facts. Rehearsal tests the fix. The pull request states what is uncertain. An unsafe patch is rejected even when its tests pass | Planned | 4, 5 | One tired approver |
| A4 | The model file, the agent runtime, or a tool server is poisoned upstream | OWASP LLM: Supply Chain. ASI04. ATLAS AML.T0010, AML.T0058 | High | Digest pins, a known publisher, and worker containment for whatever gets through | Decided | 3 | A backdoored model behaves until it does not |
| A5 | Evidence leaves the platform inside proposal text published to the repository | OWASP LLM: Sensitive Information Disclosure. ATLAS AML.T0057, AML.T0086 | High | The broker publishes checked fields, not free text from the worker | Open | 5 | Depends on the broker design. Harmless here only because the data is synthetic |
| A6 | Context poisoned in one job steers a later one | ASI06. ATLAS AML.T0080 | Medium | One scoped session per job, with cleanup. Same control as T19 | Planned | 3, 6 | Shared VM |
| A7 | A job is driven into unbounded inference | OWASP LLM: Unbounded Consumption. ATLAS AML.T0034.002 | Medium | Time and output limits. Same control as T20 | Planned | 3 | None beyond a lost job |
| A8 | The agent runtime executes commands the model wrote | ASI05 | Medium | A restricted tool set, which the runtime has to prove it supports. The worker is assumed compromised either way | Planned | 3 | Code execution on the worker is the starting assumption, not the breach |

## Credential inventory

Every secret the project has or has planned. A credential not in this table should not exist.

| Credential | Lives | Read by | Rotation | State |
| --- | --- | --- | --- | --- |
| Owner sign-in to Azure | Workstation token cache | Operator | New sign-in | In use |
| Platform deployment key and certificate | Workstation, outside the repository | Operator | New key pair and a bootstrap apply. [Procedure](runbooks/network-foundation.md#rotate-a-certificate) written, not yet run | In use |
| Target deployment key and certificate | Same | Operator | Same | Same |
| Bootstrap state | Workstation, local file | Operator | Not a secret to rotate | In use |
| Platform and target state | One storage account per root | That root's identity, and a subscription administrator | Not rotated. Access is by role | In use |
| Operator's GitHub account | GitHub | Operator | Account sign-in settings | In use |
| Mesh VPN auth key | Supplied at provisioning | The orchestrator, once | Single use. A new key per rebuild | Milestone 2 |
| Mesh node key | Orchestrator | Root on the orchestrator | Re-enroll | Milestone 2 |
| Operator SSH key | Workstation | Operator | New key, pushed by Terraform | Milestone 2 |
| Feed SSH key, orchestrator to worker and targets | Orchestrator | Root on the orchestrator | New key, pushed from the orchestrator | Milestone 2 |
| Cluster token and administrator kubeconfig | Orchestrator | Root on the orchestrator | Cluster token rotation | Milestone 2 |
| Job credential for dispatch and tool calls | Issued per job | One worker session | Dies with the job | Open, milestone 3 |
| NetBox administrator, database, and consumer token | Target VMs | The target, and the orchestrator for seeding | Reseeded with each rebuild | Milestone 4 |
| Repository app key | `change` namespace | PR broker | App key rotation | Open, milestone 5 |

## Lab against production

The controls are meant to hold up in production. The lab around them is not production, and each gap below is a choice made for capacity or cost.

| Lab choice | Why it is acceptable here | Production would use |
| --- | --- | --- |
| Mesh VPN with a third-party coordination service | No public address, no operator address in a rule, one agent | A self-hosted control plane, or a VPN gateway or private circuit with a bastion. Node signing at the least |
| One person writes, approves, and operates | There is one person | A separate approver, required human review, and time-limited privileged roles |
| One Azure account owns both sides | One subscription | A subscription per side, under separate administrators |
| Deployment keys on a workstation | Terraform runs there | Workload identity federation from a controlled runner, with no long-lived key |
| One K3s node, one VM per role | A quota of 4 vCPUs per region | A highly available control plane across zones |
| Orchestrator egress open on port 443 | Hostname filtering costs as much as the four VMs | A firewall or proxy with a hostname allowlist |
| Worker isolation is one VM shared by consecutive jobs | No capacity for more | A fresh sandbox per job |
| The audit log sits on the orchestrator | No second trusted machine | An append-only store outside the platform |
| Public repository, synthetic data | Nothing in it is real | A private repository, classified data, and strict control over what a pull request may contain. A5 becomes the main risk |
| Locally redundant state, local bootstrap state | The lab can be rebuilt from the runbooks | Geo-redundant remote state, with tested recovery |

## Accepted risks

These have no control and no gate. They are carried on purpose.

- **T05:** a compromised orchestrator can send anything anywhere on port 443.
- **T15, T30:** a takeover of the operator's GitHub or Azure account defeats the design.
- **Provider compromise:** Azure, GitHub, and the mesh VPN provider are trusted.
- **Single approver:** nobody checks the operator.
- **T31:** the bootstrap state has one copy. Losing it costs imports, not resources.
- **The workstation:** out of scope. A deployment key taken from it is covered by T29.

## Open items

Threats that no decision or gate covers yet. Each needs an answer before the milestone named.

| Item | Threats | Needed before |
| --- | --- | --- |
| Node signing on the mesh is not in any gate | T01 | Milestone 2 |
| How a job proves which job it is | T18 | Milestone 3 |
| What stands between a tool service bug and the rest of the orchestrator | T22, T36 | Milestone 3 |
| Where the audit log is stored, and who can delete it | T04, T21 | Milestone 3 |
| What the broker allows into a pull request | A5 | Milestone 5 |
| Repository app permissions | T12 | Milestone 5 |
| Sign-in strength on the operator's accounts cannot be shown by a gate | T15, T30 | Not planned |
