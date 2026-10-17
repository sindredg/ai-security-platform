# A private AI-driven security platform

Self-hosted AI workers investigate security findings on a target service they cannot reach directly, and propose fixes that are tested before review. No proposed change is delivered to the target service without human approval of that exact change.

The split of work is strict. Ordinary tools collect evidence and establish facts. AI interprets the evidence and proposes a change within defined limits. Neither gets to approve anything.

## Target architecture

This is what gets built. The networks, their rules, the peering, both platform VMs, the mesh VPN, a K3s cluster, and a model server and an agent runtime on the AI worker exist today. The target network is in Poland Central, in its own repository. The edge VM, the router VM, and monitoring are decided for milestone 3a and not built: until then, the NAT gateway is on the orchestrator subnet and the orchestrator is the mesh VPN node. The cluster is there to run the trusted side: the workflow engine, the collectors, the tool services, and the pull request broker. The tool service runs there. The others and the whole target side are planned. Component detail and the reasoning are in the [architecture](docs/architecture.md). The diagram source is [`docs/diagrams/target-architecture.html`](docs/diagrams/target-architecture.html).

![Target architecture: a trusted orchestrator VM holds the secrets and has no direct way out. It and the AI worker reach the internet only through a proxy on an edge VM. A router VM is the only mesh VPN node, logs go to Azure Monitor over a private endpoint, and the targets in Poland Central are reached only from the orchestrator](docs/diagrams/target-architecture.svg)

The mesh VPN service is a third party. The operator's device and the router VM both connect out to it, and it relays the encrypted tunnel between them. From the router, the operator's sessions continue as SSH to each VM, with a certificate that expires within 12 hours. Until the router is built, the orchestrator is the mesh node. Nothing in Azure accepts a connection from the internet. The [mesh VPN page](docs/components/mesh-vpn.md) has the detail.

The blocked paths matter as much as the open ones:

- **The AI worker reaches two services and nothing else:** the tool services on the orchestrator, and a package proxy limited to two hosts. The proxy is on the orchestrator today and moves to the edge VM in milestone 3a. No target, no internet, no name server. Rules in [`infra/platform/main.tf`](infra/platform/main.tf). Checks on [containment](docs/validation/containment.md#from-the-worker).
- **The targets reach nothing outside their own network.** They cannot open a connection into the platform, and they have no internet path. Rules in [`infra/targets/main.tf`](https://github.com/sindredg/ai-security-platform-test/blob/main/infra/targets/main.tf), in the targets repository. No target VM exists yet, so no traffic check covers this side. The [Azure policy checks](docs/validation/azure-policy.md) show it has no public address and cannot get one.
- **No VM has a public address.** The operator comes in over the mesh VPN. Outbound traffic leaves through one NAT gateway, on the orchestrator subnet today. Milestone 3a moves it to the edge network, and the orchestrator then reaches the internet only through the edge's proxy. The policy that refuses an address is in [`infra/bootstrap/policy.tf`](infra/bootstrap/policy.tf), and the [Azure policy checks](docs/validation/azure-policy.md) test it.
- **The two sides cross only over network peering**, between separate Terraform roots, state, and deployment identities. Every crossing starts on the orchestrator, except the operator's SSH sessions through the router once it exists. See [identities and state](docs/components/identities-and-state.md) and [ADR 0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md).

## Find your way around

| To see | Go to |
| --- | --- |
| What exists today, and what each milestone has to prove | [Roadmap](docs/roadmap.md#status) |
| How the system is built | [Architecture](docs/architecture.md), then the [components](docs/components/README.md), one page per part with every version pin |
| Why each choice was made, and what it costs | [Decision records](docs/decisions/README.md) |
| The check behind a claim about the running system | [Validation](docs/validation/README.md): one page per area, each claim with its check and the last run |
| The commands and output behind a result | [Worklogs](docs/worklogs/README.md), one per milestone |
| The security reasoning | [Security](docs/security/README.md): the threat model, AI-specific threats, credentials, hardening, and [accepted risks](docs/security/accepted-risks.md) |
| How to rebuild it | [Runbooks](docs/runbooks/README.md), one per milestone |
| Failures and what they showed | [Troubleshooting](docs/troubleshooting/README.md) |
| Known defects and follow-up | [Open issues](https://github.com/sindredg/ai-security-platform/issues) |
| The code | [Repository layout](#repository-layout), below |

## What can go wrong

A suggested fix and a fix that can be trusted are different things. Three failures separate them:

- **The model is wrong.** It proposes a fix that clears the finding and breaks the service.
- **The evidence lies.** A compromised target reports whatever it likes, and an advisory can carry instructions.
- **A worker dies halfway.** The change ends up half applied, or applied twice.

The design is built around those failures. Models run inside the platform, so inference does not send evidence to an external model provider. Workers get narrowly scoped tools and no cloud, repository, or delivery credentials. Every proposal is rehearsed against the service's real consumer before a person sees it, and nothing is delivered without approval of the exact change.

The AI also has to earn its place. Each result is compared with the same workflow run without it.

## Status

- **Done:** the network foundation and both platform VMs, deployed and checked. Evidence in worklogs [0001](docs/worklogs/0001-network-foundation.md) and [0002](docs/worklogs/0002-platform-compute.md).
- **In progress:** [milestone 3a](docs/roadmap.md#3a-edge-network-and-monitoring), the edge network and monitoring, in worklog [0004](docs/worklogs/0004-edge-network-and-monitoring.md). The orchestrator hardening and the SSH certificates are on the system, and every commit in a pull request has to pass a required check that it is signed by the operator's key. The target network is in Poland Central, in its own repository. The edge, the router, and monitoring are not built.
- **Paused for 3a:** toolchain integration, in worklog [0003](docs/worklogs/0003-toolchain-integration.md). A model server runs on the AI worker, and the agent runtime has completed fixture-based runs against it. The tool service runs on the orchestrator and has answered tool calls from the worker. No workflow or dispatch exists yet.
- **Planned:** the targets, the investigation and remediation workflow, and the drills.

The [roadmap](docs/roadmap.md#status) holds the state of every milestone and what each has to prove.

## Design in brief

- **Platform:** a small K3s cluster for trusted orchestration, plus a separate VM for AI workers and model inference. Sweden Central. From milestone 3a, an edge VM for the way out and a router VM for the mesh VPN, in Denmark East.
- **Target:** a NetBox inventory service with a real API consumer that must keep working. Poland Central, on its own network, in [its own repository](https://github.com/sindredg/ai-security-platform-test).
- **Separation:** platform and targets share an Azure subscription, with separate Terraform roots, state, resource groups, networks, and deployment identities.
- **Workflow:** collect evidence, investigate, propose, rehearse on a disposable copy, open a pull request, wait for approval, deliver, verify.
- **Inference:** open-weight models on CPU, inside the platform. No external model API.

## Repository layout

| Path | What it holds | Described in |
| --- | --- | --- |
| [`infra/bootstrap/`](infra/bootstrap/) | Terraform for what the other roots depend on: resource groups, state storage, the two deployment identities, and the public address policy. Applied by the operator | [Identities and state](docs/components/identities-and-state.md) |
| [`infra/platform/`](infra/platform/) | Terraform for the platform side: network, security group rules, NAT gateway, both VMs, and their first-boot templates | [Egress and policy](docs/components/egress-and-policy.md), [orchestrator](docs/components/orchestrator.md), [AI worker](docs/components/ai-worker.md) |
| [`ai-security-platform-test`](https://github.com/sindredg/ai-security-platform-test) | A separate repository. Terraform for the target network, no VMs yet. NetBox and its consumer go there in milestone 4 | [ADR 0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md), [ADR 0024](docs/decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md) |
| [`infra/modules/network/`](infra/modules/network/) | The network module both sides use | [Architecture](docs/architecture.md) |
| [`platform/logs/`](platform/logs/) | Host units and scripts on the orchestrator that copy the tool service's audit lines and pull the worker's journal into append-only files, and their tests | [Audit log](docs/security/audit-log.md) |
| [`platform/tool-service/`](platform/tool-service/) | Kubernetes manifests and scripts that deploy the tool service to K3s: namespaces, network policies, the pod, the certificate, and job registration | [Tool service](docs/security/tool-service.md#deployment-controls), [checks](docs/validation/tool-service.md) |
| [`worker/model-server/`](worker/model-server/) | Pins, download, build, and install scripts for the model server on the worker | [Runbook](docs/runbooks/model-server.md) |
| [`worker/log-export/`](worker/log-export/) | The forced command on the worker that hands its journal to the orchestrator's pull, and its install script | [Audit log](docs/security/audit-log.md#the-workers-journal) |
| [`worker/agent-runtime/`](worker/agent-runtime/) | Pins, install, and run scripts for the agent runtime, and the fixture tool | [Runbook](docs/runbooks/agent-runtime.md) |
| [`tool-service/`](tool-service/) | The tool service: its code, tests, and Dockerfile | [Tool service](docs/security/tool-service.md) |
| [`policies/`](policies/) | The tool service policy: the tools and arguments each job may use | [Tool service](docs/security/tool-service.md) |
| [`validation/`](validation/) | The script that runs every check against the live system | [Validation](docs/validation/README.md) |
| [`.github/`](.github/) | The checks on every pull request, the image build, and the signature check with its allowed signers | [Pipeline](docs/components/pipeline.md) |
| [`docs/`](docs/) | Everything in [Find your way around](#find-your-way-around) | |

## What this is not

- Not production. One node, one operator, no high availability, no compliance claim.
- Not real data. All inventory in the target is synthetic.
- Not protection from the cloud provider. The design trusts Azure and the platform administrator, and says so. See [trust boundaries](docs/architecture.md#trust-boundaries).

## License

[MIT](LICENSE).
