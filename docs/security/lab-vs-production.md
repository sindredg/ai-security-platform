# Lab against production

The design is meant to hold up in production. The lab around it is not production. This page keeps the two apart, so that a lab shortcut is not mistaken for a design choice, and a design choice is not excused as a lab shortcut.

Three lists:

- **What carries over.** Controls that would look the same in production.
- **What the lab cuts.** Each gap, why it is tolerable here, what it leaves open, and what production would use.
- **What production does not fix.** Problems that money and a second machine do not solve.

A gap is tolerable here for one of three reasons: the data is synthetic, there is one operator, or the lab can be rebuilt from the runbooks. None of the three is true in production.

## What carries over

These are the design. A production deployment would keep them and build on them.

| Control | State here |
| --- | --- |
| The AI worker is treated as compromised from the start. It holds no credential that reaches a target or a repository | Built. See [containment](../validation/containment.md) |
| Deny by default on every subnet, with explicit denies for the internet, the targets, and DNS | Verified with traffic on the worker |
| No public address on any VM, refused by a policy that neither deployment identity can change | Verified |
| One deployment identity per side, each unable to change the other | Verified |
| Every tool call authorized on the server, from a scope the caller cannot widen | Written, not deployed. See [tool service](tool-service.md) |
| Tools that read and never change. Delivery belongs to a separate trusted runner | Written for one tool. The runner is planned |
| Everything fetched is pinned by digest and checked on the trusted machine before it runs | Built for what exists |
| A change reaches a target only through a pull request that a person approved | The repository rule is built. Delivery is planned |
| Threats written down before the thing they threaten is built, and a gate behind every control | [ADR 0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md) |

## What the lab cuts

"Leaves open" is what an attacker gains, or what fails, because of the lab choice. Threat IDs are from the [threat model](threat-model.md) and the [AI-specific threats](ai-threats.md).

### People and accounts

| Lab choice | Why it is tolerable here | Leaves open | Production would use |
| --- | --- | --- | --- |
| One person writes, approves, and operates | There is one person | Nobody checks the operator. A stolen GitHub session approves its own change (T15) | A separate approver, required review, and privileged roles that are requested and expire |
| One Azure account owns both sides | One subscription | The separation between platform and targets binds the deployment identities, not the owner (T30) | A subscription per side, under separate administrators |
| Deployment keys on a workstation | Terraform runs there | A key taken from that machine controls one side for up to 91 days (T29) | Workload identity federation from a controlled runner, with no long-lived key |

### Access and network

| Lab choice | Why it is tolerable here | Leaves open | Production would use |
| --- | --- | --- | --- |
| Mesh VPN with a third-party coordination service | No public address, no operator address in a rule, one agent. Node signing is on | The provider is trusted for availability, and its agent uploads logs by default (T01) | A self-hosted control plane, or a VPN gateway or private circuit with a bastion |
| Orchestrator egress open on TCP 443 and 80, and on every UDP port | Hostname filtering costs as much as the four VMs | A compromised orchestrator sends anything anywhere (T05) | A firewall or proxy with a hostname allowlist |
| State storage accounts accept connections from any network | Access is by identity, and shared keys are off | A stolen identity works from anywhere (T32) | Private endpoints, and no public network access |
| The worker's packages come through a proxy to two public hosts, over HTTP | The packages are signed, and the proxy passes nothing else | A few bytes leave in each request, and the proxy is a service the worker can attack (T17) | An internal mirror |

### Compute and isolation

| Lab choice | Why it is tolerable here | Leaves open | Production would use |
| --- | --- | --- | --- |
| One K3s node, one VM per role | A quota of 4 vCPUs per region | No availability. A stuck job blocks the only worker (T20) | A highly available control plane across zones, and more than one worker |
| One worker VM shared by consecutive jobs | No capacity for more | Files are cleaned up, the kernel and the model server's memory are shared (T19, A6) | A fresh sandbox or VM per job |
| The tool service is a container on the trusted machine | One trusted machine | A parsing bug is a path to the machine that holds every credential (T22) | A sandboxed runtime or its own machine, and an independent review of the code |
| Credentials are files on the orchestrator and secrets in the cluster | Secrets encryption is on, and one person has root | Root on the orchestrator reads all of them (T36) | A managed secret store, hardware-backed keys, and credentials issued per use |
| A small model, built on the worker from the publisher's weights | It fits in 8 GiB and nothing leaves the lab | Weak answers. Investigation quality is not measured yet (A3) | A model chosen by evaluation, behind a gateway that logs every request |

### Tool service and job identity

| Lab choice | Why it is tolerable here | Leaves open | Production would use |
| --- | --- | --- | --- |
| A job is a bearer token | Simple to issue, check, and revoke | Whoever reads the token on the worker is the job until it ends (T18) | A credential bound to the job's sandbox, such as a certificate per job |
| One self-signed certificate, copied to the worker ([ADR 0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md)) | No authority key to protect, for one server | No revocation. Rotation is a copy made by hand | An internal authority with short-lived certificates, issued automatically |
| The registration caller is checked against a copied public key | The pod keeps no cluster credential | A deleted pod's token works until it expires. A stale copy stops registration | Key discovery with rotation, or mutual TLS between workloads |
| Jobs and call counts live in memory | One replica | A restart ends every job, and a second replica would not know the first one's jobs | A store shared by replicas |

### Detection and response

| Lab choice | Why it is tolerable here | Leaves open | Production would use |
| --- | --- | --- | --- |
| The audit log sits on the orchestrator | No second trusted machine | Root on the orchestrator can edit it (T21) | An append-only store outside the platform |
| No audit daemon, no file integrity monitoring, no alerting | Planned: alerting with milestone 3, the other two with the drills in milestone 6 | A change on a machine, a dead service, or a full disk goes unnoticed | Central logging, integrity monitoring, alerts, and someone on call |
| The worker's journal is pulled on a timer | A push would need another port from the worker | Whatever happened since the last pull can be erased | Logs shipped as they are written, to a store the source cannot change |
| A Lynis audit where a CIS benchmark was planned | No tool has a CIS profile for this release yet | No result against a recognized benchmark for the operating system | An operating system release with a supported benchmark profile |
| Pins move by hand | One person, a short list | A held agent or cluster version gets no security fix until someone moves it | Automated update proposals for every pin, and rebuilt images on a schedule |

### Data, repository, and recovery

| Lab choice | Why it is tolerable here | Leaves open | Production would use |
| --- | --- | --- | --- |
| Public repository, synthetic data | Nothing in it is real | Nothing here. In production the proposal text is a path from evidence to a public page (A5) | A private repository, classified data, and strict control over what a pull request may carry |
| Locally redundant state. The bootstrap state is a local file with a copy made by hand | The lab can be rebuilt from the runbooks | A forgotten upload leaves the copy behind. A restore has not been run (T31) | Geo-redundant remote state, with tested recovery |
| Each VM rebuilt once, never both together | Each machine came back from its template and passed every check | Nobody knows whether everything comes back from an empty subscription | Recovery rehearsed on a schedule, with a time it has to meet |

## What production does not fix

These are not lab shortcuts. A larger budget does not remove them.

- **Injected instructions are not prevented (A1).** The design contains what a turned agent can do. It does not stop the agent from being turned.
- **A convincing wrong answer still reaches a person (A3).** Rehearsal and evidence narrow it. The approver is the last check, in a lab and in a company.
- **A digest proves identity, not innocence (T06, A4).** A backdoored model or package that was pinned on day one is pinned.
- **Custom policy code is custom (T16).** No product ships this project's rule for which job may call which tool. Production reviews that code. It does not get to skip writing it.
- **A compromised orchestrator is the end (T05).** Egress filtering and a secret store make it slower and louder. The machine that dispatches jobs, checks calls, and delivers changes is still the machine to take.

## If this went to production, in this order

1. **A second person and a second account.** Every other control assumes the operator is honest and not compromised.
2. **Logs and the audit trail off the platform, with alerts.** Today a successful attack could leave no record anywhere else.
3. **Egress filtering on the orchestrator.** It turns "anything, anywhere" into a list.
4. **A sandbox per job, and the tool service off the machine that holds the credentials.**
5. **A secret store and an internal certificate authority.** Hand-copied certificates and files on disk do not survive a second operator.

The order is a judgment. It puts first what a single mistake or a single stolen session would cost most.
