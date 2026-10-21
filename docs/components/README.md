# Components

The stack, one page per part. Each page says what the part does, where it is defined, which decision is behind it, how it is checked, what it cannot do, and where the vendor documents it.

The [architecture](../architecture.md) is the overview: trust, flows, and boundaries. This folder is the detail.

![The stack on the orchestrator and the worker: both share the private network, the machine type, Ubuntu 26.04, and host hardening. The orchestrator runs K3s with the tool service, is not on the mesh VPN, and has no way out of its own. The worker runs the model server and the agent runtime](../diagrams/stack.svg)

The diagram source is [`diagrams/stack.html`](../diagrams/stack.html).

## Built

| Component | What it is | Runs on |
| --- | --- | --- |
| [Orchestrator](orchestrator.md) | The one trusted VM | Sweden Central |
| [AI worker](ai-worker.md) | The contained VM for the agent and the model | Sweden Central |
| [K3s](k3s.md) | The cluster | Orchestrator |
| [Mesh VPN](mesh-vpn.md) | The only way in. The agent runs alone on the router VM, [ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md) | The router VM, operator devices |
| [Egress and policy](egress-and-policy.md) | The outbound paths, and what blocks outbound access everywhere else | Azure |
| [Package proxy](package-proxy.md) | Squid: the one way out for the orchestrator and the worker, and the fetch window, [ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) | The edge VM |
| [Deployment identities and state](identities-and-state.md) | Who can change which side | Azure, Microsoft Entra ID |
| [Repository and pipeline](pipeline.md) | The approval channel and its checks | GitHub |
| [Tool service](../security/tool-service.md) | A small MCP server written for this project. Authorizes every tool call from the worker | Orchestrator, in K3s |
| SSH certificates | OpenSSH's own certificate authority. The administrator account takes only a certificate that expires within 12 hours, [ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md), [credentials](../security/credentials.md) | Every VM |
| [Monitoring](monitoring.md) | The Azure Monitor Agent and a Log Analytics workspace reached over Private Link, alert rules shown in the portal, flow logs, and a workbook | The orchestrator, the edge, the router, and Azure |

## Planned

Candidates, not selections, except the rows that name a decision record. Each has something to prove first.

| Role | Candidate | Has to prove | Milestone |
| --- | --- | --- | --- |
| Workflow engine and UI | Argo Workflows v4.1.5, the controller in the cluster and the UI on the operator's machine, [ADR 0029](../decisions/0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md), proposed. Installed on 2026-10-21, and the first workflows ran ([runbook](../runbooks/workflows.md), [worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows)) | Dispatch to the worker VM, restart recovery, footprint | 3 |
| Agent runtime | Goose 1.55.0, installed | Headless runs, a restricted tool set, and a private model endpoint are shown on one fixture. Goose's call to the tool service from the worker, with a job token, was seen on 2026-10-20, allowed and logged on the orchestrator. Still to test: validation of the result against a schema by the dispatch step | 3 |
| Starting model | Qwen3.5-4B, running | Structured output and tool calling on held-out fixtures. One fixed exchange passes so far | 3 |
| Model gateway | LiteLLM | That it earns its footprint while there is only one model backend | 3 |
| Deterministic checks | Trivy, Checkov, Nmap, OPA | Coverage for the selected exercises | 3 |
| First target | NetBox | See [ADR 0004](../decisions/0004-netbox-as-first-target.md) | 4 |

## Versions

Every pin in one place. Checked against the official source on the date shown.

| Component | Version | Pinned in | Moves | Checked |
| --- | --- | --- | --- | --- |
| Terraform | 1.16.6 | `versions.tf` in each root, and the checks workflow | By hand | 2026-10-19 |
| `hashicorp/azurerm` | 5.10.0 | `versions.tf` and the lock files | Dependabot, weekly | 2026-10-19 |
| `hashicorp/azuread` | 3.10.0 | The same | Dependabot, weekly | 2026-10-19 |
| `hashicorp/random` | 3.9.1 | The same | Dependabot, weekly | 2026-10-19 |
| Ubuntu image | 26.04 LTS, `26.04.202610070`. The release offer in Sweden Central has `26.04.202610180` since 2026-10-18, which the pin takes at the next rebuild. The daily builds offer newer versions that the release offer does not have ([troubleshooting 01](../troubleshooting/01-image-version-only-in-daily-offer.md)) | `infra/platform/variables.tf` | By hand, and only at a rebuild | 2026-10-19 |
| Ubuntu packages | Whatever the archive serves | Not pinned | Unattended upgrades, daily, security suite | |
| Mesh VPN agent | 1.104.2 | `infra/platform/variables.tf`, held on the VM | By hand. `U.7` fails when a newer stable release exists | 2026-10-21 |
| K3s | `v1.36.5+k3s1`, the `stable` channel | `infra/platform/variables.tf`, with two checksums | By hand | 2026-10-19 |
| Azure Monitor Agent | Extension `1.45`. The newest version in both regions is `1.45.1` | `monitor_agent_version` in `infra/platform/variables.tf`, automatic upgrades off | By hand. Azure picks the patch release within the minor version | 2026-10-19 |
| Squid | 7.2, `7.2-2ubuntu2.2` on the edge | Not pinned, see [ADR 0011](../decisions/0011-package-proxy-for-the-worker.md) | Unattended upgrades | 2026-10-17 |
| `acl` package | Whatever the archive serves. Sets the default ACL on the pod logs for the audit copier | Not pinned. The archive drops old versions, as for Squid | Unattended upgrades | |
| kube-bench | 0.16.0 | The [runbook](../runbooks/platform-compute.md) | By hand, at each run | 2026-10-19 |
| Lynis | 3.1.7 | The runbook | By hand, at each run | 2026-10-19 |
| llama.cpp | v0.7.0, the newest stable release, as build `b11669`, the same commit. The release carries no binaries, its numbered build does | `worker/model-server/pins.env` and `artifacts.tsv`, with a checksum | By hand | 2026-10-19 |
| Model | Qwen3.5-4B, revision `851bf6e8`, built to `Q4_K_M` on the worker. Two more models are pinned beside it for a [comparison](../worklogs/0003-toolchain-integration.md#model-comparison) | `worker/model-server/models/Qwen3.5-4B.tsv`, with a checksum per file. `MODEL_NAME` in `pins.env` picks the list | By hand | 2026-10-19 |
| Converter packages | 27, PyTorch 2.11.0 the largest | `worker/model-server/artifacts.tsv` and `converter-requirements.txt` | By hand. Used only during a build | 2026-10-11 |
| Goose | 1.55.0, one static binary | `worker/agent-runtime/pins.env` and `artifacts.tsv`, with a checksum for the archive and one for the binary | By hand | 2026-10-19 |
| `actions/checkout` | v7.0.1, by commit | The checks workflow | Dependabot, weekly | 2026-10-19 |
| Checkov, Trivy, gitleaks images | 3.3.30, 0.76.1, and 8.30.1, by digest | The checks workflow | By hand | 2026-10-21 |
| ShellCheck, Ruff images | 0.11.0 and 0.17.1, by digest | The checks workflow | By hand | 2026-10-19 |
| hadolint image | 2.15.1, by digest | The checks workflow | By hand | 2026-10-19 |
| kubeconform image | 0.8.0, by digest. Validates the manifests against the schemas for Kubernetes 1.36.5, the cluster's release | The checks workflow | By hand, and the Kubernetes version with K3s | 2026-10-19 |
| Python image | 3.15.0 on Alpine 3.24, by digest. Runs the tool service and log copier tests, and is the base of the tool service image | The checks workflow and `tool-service/Dockerfile`. The pipeline fails until the two name the same digest | Dependabot, weekly, for the Dockerfile. The workflow by hand | 2026-10-19 |
| Argo Workflows | v4.1.5. The release's `namespace-install.yaml` by its listed digest, for the custom resource definitions. `workflow-controller` and `argoexec` by digest, each signature checked with cosign against the release's key | `platform/argo/pins.env` and `argo.yaml` | By hand | 2026-10-19 |
| Argo's command line image | `argocli` v4.1.5 by digest, its signature checked the same way. Lints the workflow templates offline | The checks workflow | By hand, with Argo | 2026-10-20 |
| Dispatch image | The digest the pipeline pushed from `main` at `084ff13`. Public, so the cluster pulls it without a token | `platform/argo/workflow-template.yaml`, twice. The pipeline refuses a manifest image without a digest | By hand, after each image change merges | 2026-10-20 |
| Tool service image | The digest the pipeline pushed from `main` at `b3cf4d9`, with the rate limit | `platform/tool-service/tool-service.yaml`. The pipeline and `deploy.sh` refuse a manifest image without a digest | By hand, after each image change merges | 2026-10-16 |
| Tool service packages | 28, with the MCP SDK 2.3.0, PyJWT 2.15.1, and cryptography 50.0.2 | `tool-service/requirements.in`, compiled to `requirements.txt` with hashes | Dependabot, weekly | 2026-10-16 |

The rows marked "By hand" need manual version reviews. There is no automated reminder. Prioritize the mesh VPN agent, K3s, and llama.cpp because they run continuously, and Goose because it runs for each job. Review this table at the start of each milestone. Last reviewed on 2026-10-19, before dispatch, against each project's release page, the K3s channel server, Docker Hub, and the Azure image and extension lists. The rows with an older date were not read that day. Where the Version column names a newer release, the pin has not moved yet.
