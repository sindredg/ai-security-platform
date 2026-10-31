# A private AI-driven security platform

An AI agent on a self-hosted model investigates security findings on a target service it cannot reach directly, and proposes fixes that are tested before review. No change reaches the target service without human-in-the-loop approval of that exact change.

## How a fix gets made

1. Collectors on the trusted orchestrator gather a job's evidence, and deterministic checks give their own verdicts.
2. The agent, on its own VM with no credentials, reads the evidence through one tool and returns structured output: a verdict per account, and the permission to remove from each over-privileged (`excess`) account ([the agent's job](docs/components/agent-job.md)).
3. A verification gate compares each verdict with the deterministic checks', and fails closed: any difference stops the workflow for the operator.
4. A policy check and a staging test on a copy of the target vet the fix. The pull request carries checked fields only, never the model's output.
5. A tag signed with a separate approval key approves that exact commit, once. Delivery applies it and checks the target again before the merge.

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
| Just-in-time (JIT) egress window | A time-limited allowlist: an operator command on the edge VM that opens code and package hosts for at most 60 minutes |

</details>

## Status

| | |
| --- | --- |
| Milestone | 6, operational and containment drills, in progress: the drills have run, and a rebuild of each VM is left ([roadmap](docs/roadmap.md#status)) |
| Works | A fix the deterministic checks imply goes from the model's proposal to delivery: policy check, staging test, pull request, and signed approval, then a rollback ([evidence](docs/evidence/2026-10-26-2214-proposal-lines.md)) |
| Not yet | A rebuild of each VM from the current templates, and exercises 2 and 3: excess network access and a vulnerable image |

## Why it looks like this

| Concern | Design answer | Decided in |
| --- | --- | --- |
| Evidence reaching a model vendor | Open-weight model on CPU, inside the platform. No external model API | [Architecture](docs/architecture.md#why-the-model-runs-inside-the-platform) |
| The agent compromised by what it reads | Own VM, no cluster credentials. Reaches only the tool service (an MCP server) and two package hosts | [0005](docs/decisions/0005-ai-workers-on-a-separate-vm.md), [0011](docs/decisions/0011-package-proxy-for-the-worker.md) |
| Root on the host with the secrets | No direct internet. The only way out is the edge VM's proxy | [0020](docs/decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) |
| The mesh VPN vendor | Its only node is a separate router VM. SSH certificates expire within 12 hours | [0025](docs/decisions/0025-the-mesh-node-on-its-own-vm.md), [0022](docs/decisions/0022-short-lived-ssh-certificates-for-the-operator.md) |
| A compromised target | Reaches nothing outside its own network. Own repository, state, and identity | [0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md), [0024](docs/decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md) |
| Exposure to the internet | No VM has a public address. An Azure policy refuses one | [0009](docs/decisions/0009-one-egress-point-on-the-orchestrator-subnet.md) |

Three regions, because each allows only 4 vCPUs ([0003](docs/decisions/0003-region-pair.md), [0020](docs/decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)).

## What can go wrong

- **The model is wrong.** The fix clears the finding and breaks the service.
- **The evidence lies.** A compromised target or an advisory carries false data or instructions. Every model tried here followed injected instructions ([A1](docs/security/ai-threats.md)).
- **A job dies halfway.** The change is half applied, or applied twice.

So the agent gets narrow tools and no cloud, repository, or delivery credentials, every remediation proposal gets a staging test against the service's real consumer before review, and each result is compared with the same run without the agent.

Three exercises test this on a NetBox target ([ADR 0004](docs/decisions/0004-netbox-as-first-target.md)): excess inventory access, excess network access, and a vulnerable image or dependency.

## Find your way around

| Topic | Page |
| --- | --- |
| Status and milestones | [Roadmap](docs/roadmap.md#status) |
| How it is built | [Architecture](docs/architecture.md), [components](docs/components/README.md) |
| Why each choice | [Decision records](docs/decisions/README.md) |
| The terms, and their older names | [Glossary](docs/glossary.md) |
| The check behind each claim | [Validation](docs/validation/README.md) |
| What each test run showed | [Test evidence](docs/evidence/README.md), [lessons](docs/evidence/lessons.md) |
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
| [`infra/bootstrap/`](infra/bootstrap/) | Terraform the operator applies first: resource groups, state storage, both deployment identities, the public address policy, and the flow logs and Activity Log alerts neither identity can reach | [Identities and state](docs/components/identities-and-state.md) |
| [`infra/platform/`](infra/platform/) | Platform Terraform: networks, security group rules, the NAT gateway, all four VMs, their first-boot templates, and the Log Analytics workspace with its private endpoint and alert rules | [Egress and policy](docs/components/egress-and-policy.md), [orchestrator](docs/components/orchestrator.md), [AI worker](docs/components/ai-worker.md) |
| [`ai-security-platform-test`](https://github.com/sindredg/ai-security-platform-test) | A separate repository. Terraform for the target network, and NetBox and its consumer | [ADR 0002](docs/decisions/0002-separate-platform-and-target-infrastructure.md), [ADR 0024](docs/decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md) |
| [`infra/modules/network/`](infra/modules/network/) | The network module both sides use | [Architecture](docs/architecture.md) |
| [`platform/argo/`](platform/argo/) | Argo Workflows: its pins, controller, accounts, network policies, and the workflow template, and the scripts that fetch and install them and make the dispatch key | [Workflows runbook](docs/runbooks/workflows.md) |
| [`platform/dispatch/`](platform/dispatch/) | The image of the workflow's dispatch and comparison steps: their code, tests, and Dockerfile | [ADR 0030](docs/decisions/0030-how-a-job-reaches-the-worker.md), [ADR 0041](docs/decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md) |
| [`platform/logs/`](platform/logs/) | Host units and scripts on the orchestrator that copy the tool service's audit lines and pull the AI worker's journal into append-only files, and their tests | [Audit log](docs/security/audit-log.md) |
| [`platform/monitoring/`](platform/monitoring/) | The script that writes the monitoring private endpoint's addresses into the hosts file of each VM with a log agent | [Monitoring](docs/components/monitoring.md) |
| [`platform/target-images/`](platform/target-images/) | The script that fetches NetBox's image by digest during a JIT egress window, and checks it before it goes to the NetBox VM | [NetBox runbook](docs/runbooks/netbox.md) |
| [`platform/target-update/`](platform/target-update/) | The update run, which brings the targets' packages through a port the orchestrator forwards, and its install script | [Targets runbook](docs/runbooks/targets.md) |
| [`platform/tool-service/`](platform/tool-service/) | Kubernetes manifests and scripts that deploy the tool service to K3s: namespaces, network policies, the pod, the certificate, job registration, and the synthetic evidence | [Tool service](docs/security/tool-service.md#deployment-controls), [checks](docs/validation/tool-service.md) |
| [`edge/`](edge/) | The JIT egress window command and the list of hosts Squid opens during a window, both installed on the edge VM | [Package proxy](docs/components/package-proxy.md#the-jit-egress-window) |
| [`worker/model-server/`](worker/model-server/) | Pins, download, build, and install scripts for the model server on the AI worker | [Runbook](docs/runbooks/model-server.md) |
| [`worker/log-export/`](worker/log-export/) | The forced command on the AI worker that hands its journal to the orchestrator's pull, and its install script | [Audit log](docs/security/audit-log.md#the-workers-journal) |
| [`worker/feed/`](worker/feed/) | The forced command of the feed account on the AI worker, which only unpacks staged files, and its install script | [ADR 0026](docs/decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md) |
| [`worker/agent-runtime/`](worker/agent-runtime/) | Pins, install, and run scripts for the agent runtime, the job runner and its socket unit, and the fixture tool | [Runbook](docs/runbooks/agent-runtime.md) |
| [`tool-service/`](tool-service/) | The tool service: its code, tests, and Dockerfile | [Tool service](docs/security/tool-service.md) |
| [`collectors/netbox/`](collectors/netbox/) | NetBox's collector: each account's access by its permissions and by what its token returns, a job's evidence, the task, and the held-out cases | [Evidence collection](docs/runbooks/evidence-collection.md), [investigation](docs/validation/investigation.md) |
| [`policies/`](policies/) | The tool service policy: the tools and arguments each job may use | [Tool service](docs/security/tool-service.md) |
| [`validation/`](validation/) | The script that runs every check against the live system, and the test evidence's record builder and page generator | [Validation](docs/validation/README.md), [test evidence](docs/runbooks/test-evidence.md) |
| [`.github/`](.github/) | The checks on every pull request, the image build, and the signature check with its allowed signers | [Pipeline](docs/components/pipeline.md) |
| [`docs/`](docs/) | Everything in [Find your way around](#find-your-way-around) | |

</details>

## What this is not

- **Not production:** one node, one operator, no high availability.
- **Not real data:** the target's inventory is synthetic.
- **Not protection from Azure:** the provider and the platform administrator are trusted ([trust boundaries](docs/architecture.md#trust-boundaries)).

## License

[MIT](LICENSE).
