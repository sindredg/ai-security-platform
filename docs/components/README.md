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

## Planned

Candidates, not selections, except the rows that name a decision record. Each has something to prove first.

| Role | Candidate | Has to prove | Milestone |
| --- | --- | --- | --- |
| Workflow engine and UI | Argo Workflows | Dispatch to the worker VM, restart recovery, footprint | 3 |
| Agent runtime | Goose 1.54.0, installed | Headless runs, a restricted tool set, and a private model endpoint are shown on one fixture. A TLS tool call with a job token was tested on a workstation. Still to test: Goose's call to the tool service on the worker, and validation of the result against a schema | 3 |
| Starting model | Qwen3.5-4B, running | Structured output and tool calling on held-out fixtures. One fixed exchange passes so far | 3 |
| Model gateway | LiteLLM | That it earns its footprint while there is only one model backend | 3 |
| Deterministic checks | Trivy, Checkov, Nmap, OPA | Coverage for the selected exercises | 3 |
| Monitoring | Azure Monitor, with a log agent on the orchestrator, the edge, and the router, [ADR 0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md). Decided | That logs and alerts stay out of reach of the machines they describe, and the agent's footprint | 3a |
| First target | NetBox | See [ADR 0004](../decisions/0004-netbox-as-first-target.md) | 4 |

## Versions

Every pin in one place. Checked against the official source on the date shown.

| Component | Version | Pinned in | Moves | Checked |
| --- | --- | --- | --- | --- |
| Terraform | 1.16.6 | `versions.tf` in each root, and the checks workflow | By hand | 2026-10-16 |
| `hashicorp/azurerm` | 5.10.0 | `versions.tf` and the lock files | Dependabot, weekly | 2026-10-16 |
| `hashicorp/azuread` | 3.10.0 | The same | Dependabot, weekly | 2026-10-16 |
| `hashicorp/random` | 3.9.1 | The same | Dependabot, weekly | 2026-10-16 |
| Ubuntu image | 26.04 LTS, `26.04.202610070`. `26.04.202610140` is the newest in Sweden Central | `infra/platform/variables.tf` | By hand, and only at a rebuild | 2026-10-16 |
| Ubuntu packages | Whatever the archive serves | Not pinned | Unattended upgrades, daily, security suite | |
| Mesh VPN agent | 1.104.1 | `infra/platform/variables.tf`, held on the VM | By hand. `U.7` fails when a newer stable release exists | 2026-10-16 |
| K3s | `v1.36.5+k3s1`, the `stable` channel | `infra/platform/variables.tf`, with two checksums | By hand | 2026-10-16 |
| Squid | 7.2, `7.2-2ubuntu2.2` on the edge | Not pinned, see [ADR 0011](../decisions/0011-package-proxy-for-the-worker.md) | Unattended upgrades | 2026-10-17 |
| `acl` package | Whatever the archive serves. Sets the default ACL on the pod logs for the audit copier | Not pinned. The archive drops old versions, as for Squid | Unattended upgrades | |
| kube-bench | 0.16.0 | The [runbook](../runbooks/platform-compute.md) | By hand, at each run | 2026-10-16 |
| Lynis | 3.1.7 | The runbook | By hand, at each run | 2026-10-16 |
| llama.cpp | Build `b11429`. Since 2026-10-15 the project marks its numbered builds as prereleases and publishes versioned releases, the first being v0.7.0 ([#82](https://github.com/sindredg/ai-security-platform/issues/82)) | `worker/model-server/pins.env` and `artifacts.tsv`, with a checksum | By hand | 2026-10-16 |
| Model | Qwen3.5-4B, revision `851bf6e8`, built to `Q4_K_M` on the worker | `worker/model-server/artifacts.tsv`, with a checksum per file | By hand | 2026-10-11 |
| Converter packages | 27, PyTorch 2.11.0 the largest | `worker/model-server/artifacts.tsv` and `converter-requirements.txt` | By hand. Used only during a build | 2026-10-11 |
| Goose | 1.54.0, one static binary. 1.55.0 released 2026-10-16 ([#83](https://github.com/sindredg/ai-security-platform/issues/83)) | `worker/agent-runtime/pins.env` and `artifacts.tsv`, with a checksum | By hand | 2026-10-16 |
| `actions/checkout` | v7.0.1, by commit | The checks workflow | Dependabot, weekly | 2026-10-16 |
| Checkov, Trivy, gitleaks images | 3.3.29, 0.76.0, and 8.30.1, by digest | The checks workflow | By hand | 2026-10-16 |
| ShellCheck, Ruff images | 0.11.0 and 0.17.1, by digest | The checks workflow | By hand | 2026-10-16 |
| hadolint image | 2.15.1, by digest | The checks workflow | By hand | 2026-10-16 |
| kubeconform image | 0.8.0, by digest. Validates the manifests against the schemas for Kubernetes 1.36.5, the cluster's release | The checks workflow | By hand, and the Kubernetes version with K3s | 2026-10-16 |
| Python image | 3.15.0 on Alpine 3.24, by digest. Runs the tool service and log copier tests, and is the base of the tool service image | The checks workflow and `tool-service/Dockerfile`. The pipeline fails until the two name the same digest | Dependabot, weekly, for the Dockerfile. The workflow by hand | 2026-10-16 |
| Tool service image | The digest the pipeline pushed from `main` at `b3cf4d9`, with the rate limit | `platform/tool-service/tool-service.yaml`. The pipeline and `deploy.sh` refuse a manifest image without a digest | By hand, after each image change merges | 2026-10-16 |
| Tool service packages | 28, with the MCP SDK 2.3.0, PyJWT 2.15.1, and cryptography 50.0.2 | `tool-service/requirements.in`, compiled to `requirements.txt` with hashes | Dependabot, weekly | 2026-10-16 |

The rows marked "By hand" need manual version reviews. There is no automated reminder. Prioritize the mesh VPN agent, K3s, and llama.cpp because they run continuously, and Goose because it runs for each job. Review this table at the start of each milestone. Last reviewed on 2026-10-16, at the start of milestone 3a, against each project's release page, the K3s channel server, PyPI, Docker Hub, and the Azure image list. Where the Version column names a newer release, the pin has not moved yet.
