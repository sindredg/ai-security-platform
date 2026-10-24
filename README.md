# A private AI-driven security platform

An AI agent on a self-hosted model investigates security findings on a target service it cannot reach directly, and proposes fixes that are tested before review. No change reaches the target service without human approval of that exact change.

Tools establish facts. The agent proposes changes. Neither approves anything.

## Architecture

Detailed breakdown in [Architecture](docs/architecture.md).

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

## Status

| | |
| --- | --- |
| Milestone | 4, NetBox target and exercise 1 investigation, started on 2026-10-24 ([roadmap](docs/roadmap.md#status)) |
| Works since 2026-10-21 | A workflow hands a task to the agent on the worker. The agent calls the tool service with a token only that job holds, and the checked result comes back |
| Not yet | NetBox runs on its VM with no data. Nothing is seeded, so no finding has been investigated |

## Why it looks like this

| Concern | Design answer | Decided in |
| --- | --- | --- |
| Evidence reaching a model vendor | Open-weight model on CPU, inside the platform. No external model API | [Architecture](docs/architecture.md#why-the-model-runs-inside-the-platform) |
| The agent compromised by what it reads | Own VM, no cluster credentials. Reaches only the tool service and two package hosts | [0005](docs/decisions/0005-ai-workers-on-a-separate-vm.md), [0011](docs/decisions/0011-package-proxy-for-the-worker.md) |
| Root on the host with the secrets | No direct internet. The only way out is the edge VM's proxy | [0020](docs/decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) |
| The mesh VPN vendor | Its only node is a separate router VM. SSH certificates expire within 12 hours | [0025](docs/decisions/0025-the-mesh-node-on-its-own-vm.md), [0022](docs/decisions/0022-short-lived-ssh-certificates-for-the-operator.md) |
| A compromised target | Reaches nothing outside its own network. Own repository, state, and identity | [0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md), [0024](docs/decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md) |
| Exposure to the internet | No VM has a public address. An Azure policy refuses one | [0009](docs/decisions/0009-one-egress-point-on-the-orchestrator-subnet.md) |

Three regions, because each allows only 4 vCPUs ([0003](docs/decisions/0003-region-pair.md), [0020](docs/decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)).

## What can go wrong

- **The model is wrong.** The fix clears the finding and breaks the service.
- **The evidence lies.** A compromised target or an advisory carries false data or instructions.
- **A job dies halfway.** The change is half applied, or applied twice.

So the agent gets narrow tools and no cloud, repository, or delivery credentials, every proposal is rehearsed against the service's real consumer before review, and each result is compared with the same run without the agent.

Three exercises test this on a NetBox target ([ADR 0004](docs/decisions/0004-netbox-as-first-target.md)): excess inventory access, excess network access, and a vulnerable image or dependency.

## Find your way around

| Topic | Page |
| --- | --- |
| Status and milestones | [Roadmap](docs/roadmap.md#status) |
| How it is built | [Architecture](docs/architecture.md), [components](docs/components/README.md) |
| Why each choice | [Decision records](docs/decisions/README.md) |
| The check behind each claim | [Validation](docs/validation/README.md) |
| Commands and output per milestone | [Worklogs](docs/worklogs/README.md) |
| Threats and controls | [Security](docs/security/README.md) |
| Rebuild steps | [Runbooks](docs/runbooks/README.md) |
| Failures and causes | [Troubleshooting](docs/troubleshooting/README.md) |
| Known defects | [Open issues](https://github.com/sindredg/ai-security-platform/issues) |
| The code | [Repository layout](#repository-layout) |

## Repository layout

<details>
<summary>Show the directories</summary>

| Path | What it holds | Described in |
| --- | --- | --- |
| [`infra/bootstrap/`](infra/bootstrap/) | Terraform for what the other roots depend on: resource groups, state storage, the two deployment identities, and the public address policy. Also the flow logs and the Activity Log alert rules, which neither deployment identity can reach. Applied by the operator | [Identities and state](docs/components/identities-and-state.md) |
| [`infra/platform/`](infra/platform/) | Terraform for the platform side: networks, security group rules, the NAT gateway, all four VMs, their first-boot templates, and the Log Analytics workspace with its private endpoint and alert rules | [Egress and policy](docs/components/egress-and-policy.md), [orchestrator](docs/components/orchestrator.md), [AI worker](docs/components/ai-worker.md) |
| [`ai-security-platform-test`](https://github.com/sindredg/ai-security-platform-test) | A separate repository. Terraform for the target network, and NetBox and its consumer | [ADR 0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md), [ADR 0024](docs/decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md) |
| [`infra/modules/network/`](infra/modules/network/) | The network module both sides use | [Architecture](docs/architecture.md) |
| [`platform/logs/`](platform/logs/) | Host units and scripts on the orchestrator that copy the tool service's audit lines and pull the AI worker's journal into append-only files, and their tests | [Audit log](docs/security/audit-log.md) |
| [`platform/monitoring/`](platform/monitoring/) | The script that writes the monitoring private endpoint's addresses into the hosts file of each VM with a log agent | [Monitoring](docs/components/monitoring.md) |
| [`platform/tool-service/`](platform/tool-service/) | Kubernetes manifests and scripts that deploy the tool service to K3s: namespaces, network policies, the pod, the certificate, and job registration | [Tool service](docs/security/tool-service.md#deployment-controls), [checks](docs/validation/tool-service.md) |
| [`edge/`](edge/) | The fetch window command and the list of hosts Squid opens during a window, both installed on the edge VM | [Package proxy](docs/components/package-proxy.md#the-fetch-window) |
| [`worker/model-server/`](worker/model-server/) | Pins, download, build, and install scripts for the model server on the AI worker | [Runbook](docs/runbooks/model-server.md) |
| [`worker/log-export/`](worker/log-export/) | The forced command on the AI worker that hands its journal to the orchestrator's pull, and its install script | [Audit log](docs/security/audit-log.md#the-workers-journal) |
| [`worker/feed/`](worker/feed/) | The forced command of the feed account on the AI worker, which only unpacks staged files, and its install script | [ADR 0026](docs/decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md) |
| [`worker/agent-runtime/`](worker/agent-runtime/) | Pins, install, and run scripts for the agent runtime, and the fixture tool | [Runbook](docs/runbooks/agent-runtime.md) |
| [`tool-service/`](tool-service/) | The tool service: its code, tests, and Dockerfile | [Tool service](docs/security/tool-service.md) |
| [`policies/`](policies/) | The tool service policy: the tools and arguments each job may use | [Tool service](docs/security/tool-service.md) |
| [`validation/`](validation/) | The script that runs every check against the live system | [Validation](docs/validation/README.md) |
| [`.github/`](.github/) | The checks on every pull request, the image build, and the signature check with its allowed signers | [Pipeline](docs/components/pipeline.md) |
| [`docs/`](docs/) | Everything in [Find your way around](#find-your-way-around) | |

</details>

## What this is not

- **Not production:** one node, one operator, no high availability.
- **Not real data:** the target's inventory is synthetic.
- **Not protection from Azure:** the provider and the platform administrator are trusted ([trust boundaries](docs/architecture.md#trust-boundaries)).

## License

[MIT](LICENSE).
