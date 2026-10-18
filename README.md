# A private AI-driven security platform

An AI agent on a self-hosted model investigates security findings on a target service it cannot reach directly, and proposes fixes that are tested before review. No change reaches the target service without human approval of that exact change.

The split of work is strict. Ordinary tools collect evidence and establish facts. The agent interprets the evidence and proposes a change within defined limits. Neither gets to approve anything.

What is built today, and what each milestone has to prove, is in the [roadmap](docs/roadmap.md#status).

## Architecture

This is what gets built. K3s on the orchestrator runs the trusted side: the workflow engine, the collectors, the tool service, and the pull request broker. Component detail is in the [architecture](docs/architecture.md). The diagram source is [`docs/diagrams/target-architecture.html`](docs/diagrams/target-architecture.html).

![Architecture: a trusted orchestrator VM holds the secrets and has no direct internet access. It and the AI worker reach the internet only through a proxy on an edge VM. A router VM is the only mesh VPN node, logs go to Azure Monitor over a private endpoint, and the targets in Poland Central are reached only from the orchestrator](docs/diagrams/target-architecture.svg)

<details>
<summary><strong>The names in the diagram</strong></summary>

| Term | What it is |
| --- | --- |
| Orchestrator | The trusted VM. It runs K3s and the workflow, and holds the secrets |
| AI worker | The VM that runs the model and the agent. The design assumes it can be compromised |
| Edge VM | The egress proxy: a NAT gateway and a Squid forward proxy, the platform's only outbound path to the internet |
| Router | The mesh VPN's subnet router, and the only mesh node in Azure. The operator reaches every other VM through it |
| Fetch window | A time-limited allowlist: an operator command on the edge VM that opens code and package hosts for at most 60 minutes |

</details>

## Why it looks like this

Each part of the setup answers one concern. The decision record has the options that were weighed and what the choice costs.

| Concern | Design answer | Decided in |
| --- | --- | --- |
| Findings and target evidence reaching a model vendor | An open-weight model on CPU, on the AI worker. No external model API. The project controls the operating system, the model server, and the model, and can swap or tune it. Versions and measured speed are on the [AI worker page](docs/components/ai-worker.md) | [Architecture](docs/architecture.md#why-the-model-runs-inside-the-platform) |
| The agent compromised by what it reads | The AI worker is its own VM, not a cluster node, with no cluster credentials. It reaches the tool service on the orchestrator and two Ubuntu package hosts through the edge proxy. No target, no internet, no name server ([checks](docs/validation/containment.md#from-the-worker)) | [0005](docs/decisions/0005-ai-workers-on-a-separate-vm.md), [0011](docs/decisions/0011-package-proxy-for-the-worker.md) |
| Root on the host that holds the secrets | The orchestrator has no direct internet access. Its only outbound path is Squid on the edge VM, and code hosts open only in a fetch window | [0020](docs/decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) |
| The mesh VPN, a third-party service and the part the project controls least | Its only node in Azure is the router, a VM apart from the proxy and the secrets. The operator's sessions continue from there as SSH, with certificates that expire within 12 hours ([mesh VPN page](docs/components/mesh-vpn.md)) | [0025](docs/decisions/0025-the-mesh-node-on-its-own-vm.md), [0022](docs/decisions/0022-short-lived-ssh-certificates-for-the-operator.md) |
| A compromised target | The targets reach nothing outside their own network and cannot open a connection into the platform. They have their own repository, Terraform root, state, and deployment identity. Every crossing starts on the orchestrator, except the operator's sessions through the router ([identities and state](docs/components/identities-and-state.md)) | [0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md), [0024](docs/decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md) |
| A VM exposed to the internet | No VM has a public address, on either side. An Azure policy refuses one ([checks](docs/validation/azure-policy.md)) | [0009](docs/decisions/0009-one-egress-point-on-the-orchestrator-subnet.md) |

The three regions follow quota, not preference: the subscription allows 4 vCPUs per region. The orchestrator and the AI worker run in Sweden Central, the edge VM and the router in Denmark East, and the targets in Poland Central ([0003](docs/decisions/0003-region-pair.md), [0020](docs/decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)).

## What can go wrong

A suggested fix and a fix that can be trusted are different things. Three failures separate them:

- **The model is wrong.** It proposes a fix that clears the finding and breaks the service.
- **The evidence lies.** A compromised target reports whatever it likes, and an advisory can carry instructions.
- **A job dies halfway.** The change ends up half applied, or applied twice.

The workflow is built around those failures: collect evidence, investigate, propose, rehearse on a disposable copy, open a pull request, wait for approval, deliver, verify. The agent gets narrowly scoped tools and no cloud, repository, or delivery credentials, and every proposal is rehearsed against the service's real consumer before a person sees it.

The agent also has to earn its place. Each result is compared with the same workflow run without it.

Three exercises test this on one target, a NetBox inventory service with a real API consumer that must keep working ([ADR 0004](docs/decisions/0004-netbox-as-first-target.md)):

1. **Excess inventory access.** The consumer's permissions expose records outside its approved scope.
2. **Excess network access.** NetBox is reachable from a network viewpoint that policy forbids.
3. **Vulnerable image or dependency.** A pinned artifact is affected by a real public advisory.

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

## Repository layout

<details>
<summary>Each directory, what it holds, and the page that describes it</summary>

| Path | What it holds | Described in |
| --- | --- | --- |
| [`infra/bootstrap/`](infra/bootstrap/) | Terraform for what the other roots depend on: resource groups, state storage, the two deployment identities, and the public address policy. Applied by the operator | [Identities and state](docs/components/identities-and-state.md) |
| [`infra/platform/`](infra/platform/) | Terraform for the platform side: networks, security group rules, the NAT gateway, all four VMs, and their first-boot templates | [Egress and policy](docs/components/egress-and-policy.md), [orchestrator](docs/components/orchestrator.md), [AI worker](docs/components/ai-worker.md) |
| [`ai-security-platform-test`](https://github.com/sindredg/ai-security-platform-test) | A separate repository. Terraform for the target network, and NetBox and its consumer | [ADR 0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md), [ADR 0024](docs/decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md) |
| [`infra/modules/network/`](infra/modules/network/) | The network module both sides use | [Architecture](docs/architecture.md) |
| [`platform/logs/`](platform/logs/) | Host units and scripts on the orchestrator that copy the tool service's audit lines and pull the AI worker's journal into append-only files, and their tests | [Audit log](docs/security/audit-log.md) |
| [`platform/tool-service/`](platform/tool-service/) | Kubernetes manifests and scripts that deploy the tool service to K3s: namespaces, network policies, the pod, the certificate, and job registration | [Tool service](docs/security/tool-service.md#deployment-controls), [checks](docs/validation/tool-service.md) |
| [`edge/`](edge/) | The fetch window command and the list of hosts Squid opens during a window, both installed on the edge VM | [Package proxy](docs/components/package-proxy.md#the-fetch-window) |
| [`worker/model-server/`](worker/model-server/) | Pins, download, build, and install scripts for the model server on the AI worker | [Runbook](docs/runbooks/model-server.md) |
| [`worker/log-export/`](worker/log-export/) | The forced command on the AI worker that hands its journal to the orchestrator's pull, and its install script | [Audit log](docs/security/audit-log.md#the-workers-journal) |
| [`worker/agent-runtime/`](worker/agent-runtime/) | Pins, install, and run scripts for the agent runtime, and the fixture tool | [Runbook](docs/runbooks/agent-runtime.md) |
| [`tool-service/`](tool-service/) | The tool service: its code, tests, and Dockerfile | [Tool service](docs/security/tool-service.md) |
| [`policies/`](policies/) | The tool service policy: the tools and arguments each job may use | [Tool service](docs/security/tool-service.md) |
| [`validation/`](validation/) | The script that runs every check against the live system | [Validation](docs/validation/README.md) |
| [`.github/`](.github/) | The checks on every pull request, the image build, and the signature check with its allowed signers | [Pipeline](docs/components/pipeline.md) |
| [`docs/`](docs/) | Everything in [Find your way around](#find-your-way-around) | |

</details>

## What this is not

- Not production. One node, one operator, no high availability, no compliance claim.
- Not real data. All inventory in the target is synthetic.
- Not protection from the cloud provider. The design trusts Azure and the platform administrator, and says so. See [trust boundaries](docs/architecture.md#trust-boundaries).

## License

[MIT](LICENSE).
