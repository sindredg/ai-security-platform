# A private AI-driven security platform

Self-hosted AI workers investigate security findings on a target service they cannot reach directly, and propose fixes that are tested before review. No proposed change is delivered to the target service without human approval of that exact change.

The split of work is strict. Ordinary tools collect evidence and establish facts. AI interprets the evidence and proposes a change within defined limits. Neither gets to approve anything.

Each finding takes the same path: collect evidence, investigate, propose, rehearse on a disposable copy, open a pull request, wait for approval, deliver, verify.

## At a glance

| Layer | Built with | Runs on |
| --- | --- | --- |
| Infrastructure | Terraform, Azure, two regions, separate roots and identities per side | Azure |
| Access | Tailscale mesh VPN with node signing. No public address anywhere | Orchestrator, operator devices |
| Orchestration | K3s, one node | Orchestrator |
| Package proxy | Squid, two package hosts, no tunnels | Orchestrator |
| Tool service | A small MCP server written for this project, per-job tokens, a pinned certificate | Orchestrator, in K3s |
| Inference | llama.cpp with Qwen3.5-4B on CPU. No external model API | AI worker |
| Agent runtime | Goose, headless, with a restricted tool set | AI worker |
| Pipeline | GitHub Actions: Checkov, Trivy, gitleaks, ShellCheck, Ruff, hadolint, kubeconform | GitHub |
| Workflow engine | Argo Workflows, planned | Orchestrator |
| Target | NetBox with synthetic inventory and a real API consumer, planned | Target network |

Versions and where each is pinned are in the [component index](docs/components/README.md#versions).

## Start here

| Time | Read |
| --- | --- |
| 2 min | This page, down to [what the AI cannot do](#what-the-ai-cannot-do) |
| 15 min | The [architecture](docs/architecture.md), then [ADR 0014](docs/decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) (the tool service) and [ADR 0018](docs/decisions/0018-a-host-rule-keeps-pods-off-the-internet.md) (pods off the internet) |
| Check it | The [validation pages](docs/validation/README.md): each claim, its check, and the last run |
| Rebuild it | The [runbooks](docs/runbooks/README.md), one per milestone |
| Failures | [Troubleshooting](docs/troubleshooting/README.md): symptom, cause, fix |

## Target architecture

This is what gets built. The [roadmap](docs/roadmap.md#status) says which parts exist today. Component detail and the reasoning are in the [architecture](docs/architecture.md). The diagram source is [`docs/diagrams/target-architecture.html`](docs/diagrams/target-architecture.html).

![Target architecture: a trusted orchestrator VM is the only link between the AI worker, the targets, and the outside world. The operator reaches it through a mesh VPN service outside Azure](docs/diagrams/target-architecture.svg)

The mesh VPN service is a third party. The operator's device and the orchestrator both connect out to it, and it relays the encrypted tunnel between them. Nothing in Azure accepts a connection from the internet. The [mesh VPN page](docs/components/mesh-vpn.md) has the detail.

The blocked paths matter as much as the open ones:

- **The AI worker reaches two services on the orchestrator and nothing else:** the tool services and the package proxy. No target, no internet, no name server. Rules in [`infra/platform/main.tf`](infra/platform/main.tf). Checks on [containment](docs/validation/containment.md#from-the-worker).
- **The targets reach nothing outside their own network.** They cannot open a connection into the platform, and they have no internet path. Rules in [`infra/targets/main.tf`](infra/targets/main.tf). No target VM exists yet, so no traffic check covers this side. The [Azure policy checks](docs/validation/azure-policy.md) show it has no public address and cannot get one.
- **No VM has a public address.** The operator comes in over the mesh VPN. Outbound traffic leaves through one NAT gateway on the orchestrator subnet. The policy that refuses an address is in [`infra/bootstrap/policy.tf`](infra/bootstrap/policy.tf), and the [Azure policy checks](docs/validation/azure-policy.md) test it.
- **Pods on the orchestrator do not share its outbound access.** A host rule drops forwarded traffic from pods to anything but pods. See [ADR 0018](docs/decisions/0018-a-host-rule-keeps-pods-off-the-internet.md) and the [orchestrator's checks](docs/validation/containment.md#the-orchestrators-side).
- **The two sides cross only over network peering**, between separate Terraform roots, state, and deployment identities. Every crossing starts on the orchestrator. See [identities and state](docs/components/identities-and-state.md) and [ADR 0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md).

## What can go wrong

A suggested fix and a fix that can be trusted are different things. Three failures separate them:

- **The model is wrong.** It proposes a fix that clears the finding and breaks the service.
- **The evidence lies.** A compromised target reports whatever it likes, and an advisory can carry instructions.
- **A worker dies halfway.** The change ends up half applied, or applied twice.

The design is built around those failures. Models run inside the platform, so inference does not send evidence to an external model provider. Workers get narrowly scoped tools and no cloud, repository, or delivery credentials. Every proposal is rehearsed against the service's real consumer before a person sees it, and nothing is delivered without approval of the exact change.

The AI also has to earn its place. Each result is compared with the same workflow run without it.

## What the AI cannot do

Assume the AI worker is compromised. This is what still holds, what enforces it, and the check that would fail if it stopped holding. Each validation page records whether its checks have run.

| The AI worker cannot | Enforced by | Checked by |
| --- | --- | --- |
| Connect to the internet | The `deny-to-internet` rule on the worker subnet | [`C.1`, `Z.7`](docs/validation/containment.md#from-the-worker) |
| Reach a target | The `deny-to-targets` rule. Evidence comes through tool services only | [`Z.6`](docs/validation/containment.md#from-azures-side). `C.2` and `C.3` prove nothing until a target VM exists |
| Pass data out through DNS | No route to the platform resolver | [`C.4`, `C.5`](docs/validation/containment.md#from-the-worker) |
| Administer the orchestrator or the cluster | No path to SSH, the Kubernetes API, or the kubelet | [`C.6` to `C.8`, `Z.9`](docs/validation/containment.md#from-the-worker) |
| Use the package proxy as a way out | Squid serves two package hosts, plain downloads only. No upload, other port, or tunnel | [`P.8` to `P.11`](docs/validation/package-proxy.md) |
| Call a tool without a valid job token, or trust a forged service | Per-job tokens checked by the tool service. A pinned certificate, TLS 1.3 only | [`T.10` to `T.13`](docs/validation/tool-service.md#from-the-worker), and the [tests in CI](docs/security/tool-service.md) |
| Give a target an address on the internet | An Azure policy refuses public addresses in both resource groups | [`Z.10`, `Z.11`](docs/validation/azure-policy.md) |
| Approve or deliver a change | The worker holds no repository, cloud, or delivery credential. Approval is a pull request on a protected `main` | [Credential inventory](docs/security/credentials.md), [repository settings](docs/components/pipeline.md#repository-settings) |

The reasoning behind each row is in the [threat model](docs/security/threat-model.md) and the [AI-specific threats](docs/security/ai-threats.md).

## Status

The [roadmap](docs/roadmap.md#status) holds the state of every milestone, what each has to prove, and a link to the worklog with the evidence. Known defects and follow-up are in the [open issues](https://github.com/sindredg/ai-security-platform/issues).

## Repository layout

| Path | What it holds | Described in |
| --- | --- | --- |
| [`infra/bootstrap/`](infra/bootstrap/) | Terraform for what the other roots depend on: resource groups, state storage, the two deployment identities, and the public address policy. Applied by the operator | [Identities and state](docs/components/identities-and-state.md) |
| [`infra/platform/`](infra/platform/) | Terraform for the platform side: network, security group rules, NAT gateway, both VMs, and their first-boot templates | [Egress and policy](docs/components/egress-and-policy.md), [orchestrator](docs/components/orchestrator.md), [AI worker](docs/components/ai-worker.md) |
| [`infra/targets/`](infra/targets/) | Terraform for the target network. No VMs yet | [ADR 0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md) |
| [`infra/modules/network/`](infra/modules/network/) | The network module both sides use | [Architecture](docs/architecture.md) |
| [`platform/tool-service/`](platform/tool-service/) | Kubernetes manifests and scripts that deploy the tool service to K3s: namespaces, network policies, the pod, the certificate, and job registration | [Tool service](docs/security/tool-service.md#deployment-controls), [checks](docs/validation/tool-service.md) |
| [`worker/model-server/`](worker/model-server/) | Pins, download, build, and install scripts for the model server on the worker | [Runbook](docs/runbooks/model-server.md) |
| [`worker/agent-runtime/`](worker/agent-runtime/) | Pins, install, and run scripts for the agent runtime, and the fixture tool | [Runbook](docs/runbooks/agent-runtime.md) |
| [`tool-service/`](tool-service/) | The tool service: its code, tests, and Dockerfile | [Tool service](docs/security/tool-service.md) |
| [`policies/`](policies/) | The tool service policy: the tools and arguments each job may use | [Tool service](docs/security/tool-service.md) |
| [`validation/`](validation/) | The script that runs every check against the live system | [Validation](docs/validation/README.md) |
| [`.github/workflows/`](.github/workflows/) | The checks on every pull request, and the image build | [Pipeline](docs/components/pipeline.md) |
| [`docs/`](docs/) | [Decision records](docs/decisions/README.md), [architecture](docs/architecture.md), [components](docs/components/README.md), [security](docs/security/README.md), [validation](docs/validation/README.md), [worklogs](docs/worklogs/README.md), [runbooks](docs/runbooks/README.md), [troubleshooting](docs/troubleshooting/README.md) | |

## What this is not

| Not | Why it matters |
| --- | --- |
| Production | One node, one operator, no high availability, no compliance claim |
| Separation of duties | One person investigates and approves. The pull request records the approval and does not make it independent |
| Real data | All inventory in the target is synthetic |
| Protection from the cloud provider | The design trusts Azure and the platform administrator. See [trust boundaries](docs/architecture.md#trust-boundaries) |
| Fast | Inference runs on two Arm CPU cores with no GPU. The [AI worker](docs/components/ai-worker.md#measured) has the measurements |
| A full list of what is missing | The [accepted risks](docs/security/accepted-risks.md) and the [lab against production](docs/security/lab-vs-production.md) pages hold that |

## License

[MIT](LICENSE).
