# Components

The stack, one page per part. Each page says what the part does, where it is defined, which decision is behind it, how it is checked, what it cannot do, and where the vendor documents it.

The [architecture](../architecture.md) is the overview: trust, flows, and boundaries. This folder is the detail.

![The stack on the orchestrator and the worker: both share the private network, Ubuntu 26.04, and host hardening, on two machine sizes. The orchestrator runs K3s with the tool service and Argo Workflows, is not on the mesh VPN, and has no way out of its own. The worker runs the model server and the agent runtime](../diagrams/stack.svg)

The diagram source is [`diagrams/stack.html`](../diagrams/stack.html).

## Built

| Component | What it is | Runs on |
| --- | --- | --- |
| [Orchestrator](orchestrator.md) | The one trusted VM | Sweden Central |
| [AI worker](ai-worker.md) | The contained VM for the agent and the model | Sweden Central |
| [K3s](k3s.md) | The cluster | Orchestrator |
| [Mesh VPN](mesh-vpn.md) | The only way in. The agent runs alone on the router VM, [ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md) | The router VM, operator devices |
| [Egress and policy](egress-and-policy.md) | The outbound paths, and what blocks outbound access everywhere else | Azure |
| [Package proxy](package-proxy.md) | Squid: the one way out for the orchestrator and the worker, the fetch window, and the targets' package port, [ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) and [ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md) | The edge VM |
| [Deployment identities and state](identities-and-state.md) | Who can change which side | Azure, Microsoft Entra ID |
| [Repository and pipeline](pipeline.md) | The approval channel and its checks | GitHub |
| [Tool service](../security/tool-service.md) | A small MCP server written for this project. Authorizes every tool call from the worker | Orchestrator, in K3s |
| Workflow engine | Argo Workflows. The controller runs in the cluster, and the UI on the operator's machine, [ADR 0029](../decisions/0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md). Each workflow's dispatch step hands one job to the worker, [ADR 0030](../decisions/0030-how-a-job-reaches-the-worker.md), [runbook](../runbooks/workflows.md). Since 2026-10-25 a NetBox job's comparison step follows it, and fails on anything but a match with the checks, [ADR 0041](../decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md) | Orchestrator, in K3s |
| [Model server](ai-worker.md#the-model-server) | llama.cpp's server with Qwen3.5-4B, thinking off, built on the worker from the publisher's weights, [ADR 0015](../decisions/0015-build-the-model-file-on-the-worker.md), [ADR 0031](../decisions/0031-qwen3-5-4b-stays-the-workers-model.md). Scored on exercise 1's held-out cases ([evidence](../evidence/2026-10-25-2308-scored-cases.md)) | AI worker |
| [Agent runtime](ai-worker.md#the-agent-runtime) | Goose, one run per job in a sandboxed unit that a socket starts | AI worker |
| SSH certificates | OpenSSH's own certificate authority. The administrator account takes only a certificate that expires within 12 hours, [ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md), [credentials](../security/credentials.md) | Every VM |
| [Monitoring](monitoring.md) | The Azure Monitor Agent and a Log Analytics workspace reached over Private Link, alert rules shown in the portal, flow logs, and a workbook | The orchestrator, the edge, the router, and Azure |
| Target VMs | The NetBox VM and the lab VM, from the [targets repository](https://github.com/sindredg/ai-security-platform-test). No way out. Packages only during an update run from the orchestrator, [ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md), [checks](../validation/targets.md), [runbook](../runbooks/targets.md) | Poland Central |
| NetBox | NetBox v4.7.3 and its background worker, from the `netbox-docker` image pinned by digest, in two Podman Quadlet units. PostgreSQL 18 and Valkey 9 from Ubuntu on the VM's loopback. TLS on port 8443 from Granian, with a key made on the VM, [ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md), [ADR 0038](../decisions/0038-netboxs-tls-key-made-on-the-netbox-vm.md), [checks](../validation/targets.md#netbox), [runbook](../runbooks/netbox.md). It takes a client's address from the connection only, [ADR 0039](../decisions/0039-netbox-takes-a-clients-address-from-the-connection.md). Seeded with exercise 1's synthetic inventory, accounts, and tokens on 2026-10-25 ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-seed-and-the-two-checks)) | The NetBox VM |
| NetBox collector | `collectors/netbox/netbox_access.py`: what each account may see, by its configured permissions and by the records its own token returns. Python's standard library only. The checks send it to the host as an argument and the contract on standard input, [ADR 0037](../decisions/0037-an-unscoped-copy-of-the-consumers-permission.md), [checks](../validation/targets.md#netbox). Since 2026-10-25 also installed for one job's evidence: `collect-netbox-evidence` on the orchestrator runs the configured half there and the observed half through an observer account on the lab VM, and writes the facts into the tool service's config map, [ADR 0040](../decisions/0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md), [runbook](../runbooks/evidence-collection.md). The verdicts go into another, `netbox-verdicts`, for the comparison step, [ADR 0041](../decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md). With a case's name it collects against a held-out case's contract, [ADR 0042](../decisions/0042-held-out-cases-and-the-baseline-without-the-agent.md) | The orchestrator and the lab VM |

## Planned

Candidates, not selections. Each has something to prove first.

| Role | Candidate | Has to prove | Milestone |
| --- | --- | --- | --- |
| Deterministic checks | Trivy, Checkov, Nmap, OPA | Coverage for exercises 2 and 3. Exercise 1's checks are the NetBox collector's | 7, 8 |

## Versions

Every pin in one place. Checked against the official source on the date shown.

| Component | Version | Pinned in | Moves | Checked |
| --- | --- | --- | --- | --- |
| Terraform | 1.17.0, released on 2026-10-21. Checked against HashiCorp's signed checksums | `versions.tf` in each root, and the checks workflow | By hand | 2026-10-26 |
| `hashicorp/azurerm` | 5.11.0, released on 2026-10-23 | `versions.tf` and the lock files | Dependabot, weekly | 2026-10-26 |
| `hashicorp/azuread` | 3.10.0 | The same | Dependabot, weekly | 2026-10-26 |
| `hashicorp/random` | 3.9.1 | The same | Dependabot, weekly | 2026-10-26 |
| Ubuntu image | 26.04 LTS, `26.04.202610070`. The newest version the release offer serves in Sweden Central is `26.04.202610210`, read on 2026-10-26, which the pin takes at the next rebuild. `az vm image list` names `26.04.202610240`, which `az vm image show` did not find. The daily builds offer newer versions that the release offer does not have ([troubleshooting 01](../troubleshooting/01-image-version-only-in-daily-offer.md)) | `infra/platform/variables.tf` | By hand, and only at a rebuild | 2026-10-26 |
| Ubuntu image on the targets | 26.04 LTS, `26.04.202610210`, the newest version `az vm image show` found in Poland Central on 2026-10-26. `az vm image list` names `26.04.202610240`, which the region did not serve | `infra/targets/variables.tf` in the targets repository | By hand, at a rebuild of the targets | 2026-10-26 |
| NetBox image | `netbox-docker` 5.1.1 with NetBox v4.7.3, the newest of each on 2026-10-24. `ghcr.io/netbox-community/netbox:v4.7.3-5.1.1`, by the digest of its image index, `sha256:1d6e0b5fbd48da9868376900561ee55992e04446ce7861dab5e9a42ae01f3fcb`. The file also pins the index's linux/amd64 manifest and that manifest's config, whose digest is the image ID the NetBox VM compares ([ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)) | `netbox/image.env` in the targets repository | By hand, in a signed pull request to the targets repository | 2026-10-26 |
| Ubuntu packages | Whatever the archive serves | Not pinned | Unattended upgrades, daily, security suite. On the targets, only an update run from the orchestrator ([ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)) | |
| Mesh VPN agent | 1.104.2 | `infra/platform/variables.tf`, held on the VM | By hand. `U.7` fails when a newer stable release exists | 2026-10-26 |
| K3s | `v1.36.5+k3s1`, the `stable` channel | `infra/platform/variables.tf`, with checksums for the binary, the install script, and the system images' archive. The images' digests in `infra/platform/k3s-images.txt` ([ADR 0033](../decisions/0033-k3s-system-images-from-the-release-archive.md)) | By hand | 2026-10-26 |
| Azure Monitor Agent | Extension `1.45`. The newest version is `1.45.1`, read in Sweden Central on 2026-10-26 | `monitor_agent_version` in `infra/platform/variables.tf`, automatic upgrades off | By hand. Azure picks the patch release within the minor version | 2026-10-26 |
| Squid | 7.2, `7.2-2ubuntu2.2` on the edge | Not pinned, see [ADR 0011](../decisions/0011-package-proxy-for-the-worker.md) | Unattended upgrades | 2026-10-17 |
| `acl` package | Whatever the archive serves. Sets the default ACL on the pod logs for the audit copier | Not pinned. The archive drops old versions, as for Squid | Unattended upgrades | |
| kube-bench | 0.16.0 | The [runbook](../runbooks/platform-compute.md) | By hand, at each run | 2026-10-26 |
| Lynis | 3.1.7 | The runbook | By hand, at each run | 2026-10-26 |
| llama.cpp | v0.7.0, the newest stable release, as build `b11669`, the same commit. The release carries no binaries, its numbered build does | `worker/model-server/pins.env` and `artifacts.tsv`, with a checksum | By hand | 2026-10-26 |
| Model | Qwen3.5-4B, revision `851bf6e8`, built to `Q4_K_M` on the worker. Two more models are pinned beside it, compared with it on 2026-10-21 ([ADR 0031](../decisions/0031-qwen3-5-4b-stays-the-workers-model.md)) | `worker/model-server/models/Qwen3.5-4B.tsv`, with a checksum per file. `MODEL_NAME` in `pins.env` picks the list | By hand | 2026-10-26: the revision is still the newest |
| Converter packages | 27, PyTorch 2.11.0 the largest. `filelock` 4.2.4 and `setuptools` 84.2.1 since 2026-10-26, for seven advisories in the earlier pins ([#211](https://github.com/sindredg/ai-security-platform/issues/211)) | `worker/model-server/artifacts.tsv` and `converter-requirements.txt` | By hand. Used only during a build | 2026-10-26 for those two. The other 25 were not read |
| Goose | 1.56.0, released on 2026-10-23, one static binary. Its provenance checked with cosign ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#goose)) | `worker/agent-runtime/pins.env` and `artifacts.tsv`, with a checksum for the archive and one for the binary | By hand | 2026-10-26 |
| `actions/checkout` | v7.0.1, by commit | The checks workflow | Dependabot, weekly | 2026-10-26 |
| Checkov, Trivy images | 3.3.30 and 0.76.1, by digest | The checks workflow | By hand | 2026-10-26 |
| gitleaks | 8.30.1, the release's archive for linux x64, by SHA-256, since 2026-10-23. The release has no signature. The image ran its own `git`, linked to an affected musl ([#155](https://github.com/sindredg/ai-security-platform/issues/155)) | The checks workflow | By hand | 2026-10-26 |
| ShellCheck, Ruff images | 0.11.0 and 0.17.2, by digest | The checks workflow | By hand | 2026-10-26 |
| hadolint image | 2.15.1, by digest | The checks workflow | By hand | 2026-10-26 |
| kubeconform image | 0.8.0, by digest. Validates the manifests against the schemas for Kubernetes 1.36.5, the cluster's release | The checks workflow | By hand, and the Kubernetes version with K3s | 2026-10-26 |
| Python image | 3.15.1 on Alpine 3.24, by digest, since 2026-10-22: its musl 1.2.6-r3 fixes CVE-2026-107891, which Alpine's security database lists and NVD did not yet describe. Runs the tool service tests and the dispatch step's, and is the base of the tool service and dispatch images | The checks workflow, `tool-service/Dockerfile`, and `platform/dispatch/Dockerfile`. The pipeline fails until the three name the same digest | Dependabot, weekly, for the tool service's Dockerfile. The workflow and the dispatch Dockerfile by hand | 2026-10-26: the tag's digest is still the pinned one. Python 3.15.2 is released, with no image yet |
| Host Python | 3.14, Ubuntu 26.04's `python3`. The host units on the VMs run it: the job runner and the job program on the worker, the audit copier and the journal pull on the orchestrator | `HOST_PYTHON` in the checks workflow. The host suites run on the runner's `python3`, the same Ubuntu release, and fail on another ([#168](https://github.com/sindredg/ai-security-platform/issues/168)) | With the Ubuntu image | 2026-10-23: 3.14.4 on the runner, read by the pipeline. The VMs' patch release was not read that day |
| Argo Workflows | v4.1.6, released on 2026-10-22. The release's `namespace-install.yaml` by its listed digest, for the custom resource definitions. `workflow-controller` and `argoexec` by digest, each signature checked with cosign against the release's key | `platform/argo/pins.env` and `argo.yaml` | By hand | 2026-10-26 |
| Argo's command line image | `argocli` v4.1.6 by digest, its signature checked the same way. Lints the workflow templates offline | The checks workflow | By hand, with Argo | 2026-10-26 |
| Dispatch image | The digest the pipeline pushed from `main` at `731de86`, on the Python image above. It registers the job for the workflow's target, reads `slot_erased` in a job's result, and fails a job whose answer is longer than 8 KiB or holds `{{`, a control character, or a character above U+FFFF. It also runs the comparison step, which reads only verdict lines in the exact form. Public, so the cluster pulls it without a token | `platform/argo/workflow-template.yaml`, three times. The pipeline refuses a manifest image without a digest | By hand, after each image change merges | 2026-10-25 |
| Tool service image | The digest the pipeline pushed from `main` at `91bace4`, on the Python image above | `platform/tool-service/tool-service.yaml`. The pipeline and `deploy.sh` refuse a manifest image without a digest | By hand, after each image change merges | 2026-10-25 |
| Tool service packages | 28, with the MCP SDK 2.3.0, PyJWT 2.15.1, and cryptography 50.0.2 | `tool-service/requirements.in`, compiled to `requirements.txt` with hashes | Dependabot, weekly | 2026-10-26: the three named here are still the newest on PyPI. The other 25 were not read |

The rows marked "By hand" need manual version reviews. There is no automated reminder. Prioritize the mesh VPN agent, K3s, and llama.cpp because they run continuously, and Goose because it runs for each job. Review this table at the start of each milestone. Last reviewed on 2026-10-26, at the start of milestone 5, against each project's release page, the K3s channel server, the Terraform registry, PyPI, Docker Hub, and the Azure image and extension lists. The rows with an older date were not read that day. Where the Version column names a newer release, the pin has not moved yet.
