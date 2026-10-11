# Threat model

Status: first pass, written 2026-10-11 against the design and revised the same day after the platform VMs were built. The network, the two platform VMs, and their containment are built and tested. Everything that runs on them is not, so most controls here are still decided or planned. Each row says which.

This document lists what can go wrong at each trust boundary, what stops it, where that gets proven, and what is left over. The method and the reason for doing it now are in [ADR 0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md). The system it describes is in the [architecture](../architecture.md).

This page holds the boundaries and their threats. The rest of the security work is in the [security index](README.md): [AI-specific threats](ai-threats.md), the [credential inventory](credentials.md), [hardening](hardening.md), [accepted risks and open items](accepted-risks.md), and [lab against production](lab-vs-production.md).

## What the first pass found

Five things stand out. None is fixed by this document.

1. **The tool services are the wall.** Every limit on the AI worker ends at one service on the trusted machine that reads hostile input. That service is not designed yet, and neither is the way it tells one job from another. See T16, T18, T22.
2. **The repository is the approval channel and was unprotected.** `main` accepted a force push when this was written. It no longer does: a ruleset requires a pull request with four passing checks, and secret scanning with push protection is on. What a pipeline may do with a credential is still open. See T10.
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

![Trust boundaries: six numbered crossings between the operator, the trusted orchestrator, the untrusted AI worker, the targets, GitHub, the internet, and the Azure APIs](../diagrams/trust-boundaries.svg)

The diagram source is [`diagrams/trust-boundaries.html`](../diagrams/trust-boundaries.html).

| Boundary | Crossing | What crosses |
| --- | --- | --- |
| B1 | Operator to orchestrator, over the mesh VPN | Shells, the workflow interface |
| B2 | Orchestrator to the internet, through the NAT gateway | Packages, images, the model, security feeds, mesh VPN control traffic |
| B3 | Platform to GitHub | Pull requests out, approvals in |
| B4 | Orchestrator to AI worker and back | Job dispatch out, tool calls and results back |
| B5 | Orchestrator to targets | Collection, probes, rehearsal, approved delivery |
| B6 | Operator to the Azure APIs | Terraform runs, state, role assignments, policy |

## Threats

"Gate" names the roadmap milestone whose exit gate proves the control. A threat with no gate is listed under [open items](accepted-risks.md#open-items).

### B1. Operator access

| ID | Threat | STRIDE | Rating | Control | State | Gate | Residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T01 | A device that is not the operator's joins the mesh, through a stolen login or the provider adding a node | S, E | High | Access policy limited to the operator's devices. SSH key authentication on every VM regardless. Node signing, so the provider alone cannot add a device | Node signing on since 2026-10-11, with two signing devices | 2 | The mesh login is a second factor on top of SSH, not a replacement. A stolen signing device can admit a node |
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
| T17 | The worker reaches a target or the internet directly | E, I | High | Deny rules on the platform side, plus no outbound path. The one exception is a proxy on the orchestrator that forwards package downloads to two hosts ([ADR 0011](../decisions/0011-package-proxy-for-the-worker.md)) | Verified with traffic | 2 | The proxy is a service the worker can attack, and requests to the two package hosts carry a few bytes out |
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
| T29 | A deployment key is used by someone other than the operator | S, E | High | Each key reaches one side only. A certificate is valid for at most 91 days | [Verified](../worklogs/0001-network-foundation.md#identity-separation) | 1 | Full control of one side until the certificate is removed or expires. How the key is stored is out of scope |
| T30 | The Owner account is taken over | S, E | High | Strong sign-in on the account | Accepted | None | Total. The separation does not bind that role |
| T31 | The bootstrap state is lost | D | Low | Everything in it can be imported again | Accepted | None | An afternoon of imports |
| T32 | State is read and gives up sensitive values | I | Medium | Entra authentication, shared keys off, one identity per account. Secrets kept out of Terraform | Verified | 1 | The accounts accept connections from any network |
| T33 | One side's identity changes the other side | E | High | Role assignments scoped to one side | [Verified](../worklogs/0001-network-foundation.md#identity-separation) | 1 | The peering action, which carries no traffic alone |
| T34 | A change to the shared network module reaches both sides unnoticed | T | Medium | Each root's plan is read before its apply. Static checks on pull requests | Planned | 2 | One reader |
| T35 | A secret in VM custom data is read from instance metadata | I | Medium | No secret in custom data on a fed machine | Decided | 2 | The orchestrator's enrollment key. See T02 |
| T36 | A workload on the cluster reaches the `change` namespace credentials | E | High | Per-workload permissions and a hardening baseline. Namespaces are not treated as a wall | Open | 3 | Depends on the workload identity decision |
