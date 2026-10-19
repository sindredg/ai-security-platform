# AI worker

The machine that runs the agent and the model. It reads advisories, target evidence, and tool output, and any of those can carry instructions. The design assumes it can be compromised and restricts its credentials and network access.

| | |
| --- | --- |
| State | Runs the model server. The agent runtime is installed and runs once per job. Nothing dispatches a job yet |
| Where | Sweden Central, `snet-worker`, fixed private address `10.40.0.36` |
| Size | `Standard_D2ps_v6`: 2 vCPUs, 8 GiB, Arm64. Two physical cores for the same quota as one x64 core pair |
| Image | Ubuntu 26.04 LTS, `Canonical:ubuntu-26_04-lts:server-arm64` |
| Disk | 64 GB, Standard SSD |
| Defined in | `infra/platform/compute.tf`, `infra/platform/cloud-init/worker.yaml.tftpl`, `worker/model-server/`, `worker/agent-runtime/`, `worker/log-export/` |
| Decisions | [0005](../decisions/0005-ai-workers-on-a-separate-vm.md), [0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md), [0011](../decisions/0011-package-proxy-for-the-worker.md), [0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md), [0015](../decisions/0015-build-the-model-file-on-the-worker.md) |

## What it can reach

| Destination | Result |
| --- | --- |
| The internet | Nothing |
| The target network | Nothing |
| A name server | Nothing. It uses a hosts file |
| The edge VM, TCP 3128 | Squid, the [package proxy](package-proxy.md), since 2026-10-17. Before that it ran on the orchestrator |
| The orchestrator, TCP 30443 | The [tool service](../security/tool-service.md). Deployed, reached by `T.9` and the [round trip](../worklogs/0003-toolchain-integration.md#the-round-trip) |
| The orchestrator, any other port | Nothing |

It is not part of the cluster. It downloads nothing at first boot, because it has nothing to download from. First boot sets up only what cloud-init carries: the account the orchestrator pulls the journal through. The model server is pushed and built afterwards, from the orchestrator.

## What reaches it

SSH from the orchestrator subnet, and nothing else. The administrator account takes only the operator's certificate ([ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md), `HW.17`). The orchestrator's feed key logs in to `aisec-feed`, which has no sudo and can only unpack staged files into its own directory ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md), `E.9` to `E.11`). Both since 2026-10-16. The orchestrator's log export key goes on the `aisec-logexport` account and can run only the journal export ([audit log](../security/audit-log.md#the-workers-journal)). In place since 2026-10-16 (`J.7`).

## The model server

llama.cpp v0.7.0, build `b11669`, serves Qwen3.5-4B, quantized to `Q4_K_M`, on `127.0.0.1:8080`. Nothing outside the worker can reach it.

| | |
| --- | --- |
| Binaries | `/opt/aisec/llama.cpp/llama-b11669`, the project's release build, checked against its published checksum |
| Model file | `/opt/aisec/models/Qwen3.5-4B-Q4_K_M.gguf`, 2.78 GB. Built here from Qwen's weights, not downloaded ([ADR 0015](../decisions/0015-build-the-model-file-on-the-worker.md)) |
| Unit | `aisec-llama-server.service`: a throwaway account, a read-only file system, localhost only, a 6 GB memory limit |
| Settings | 2 threads, 8192-token context, one slot, no web interface, no RAM prompt cache |
| Procedure | The [model server runbook](../runbooks/model-server.md) |

## The agent runtime

Goose 1.55.0, one static binary. It is not a service. `run-agent.sh` starts one run in a transient unit, hands it the task on standard input, and gets the transcript back as one JSON document.

![One agent run on the worker: the task arrives from the operator over SSH on standard input, the job runner starts Goose in a sandboxed transient unit, Goose calls the model server on 127.0.0.1 port 8080 and one fixture tool over standard input and output, and the transcript goes back as one JSON document](../diagrams/agent-run.svg)

The diagram source is [`diagrams/agent-run.html`](../diagrams/agent-run.html). It shows what runs today. Nothing dispatches a run yet, so the task comes from the operator's shell, through the mesh VPN.

| | |
| --- | --- |
| Binary | `/opt/aisec/goose/goose-1.55.0/goose`, the project's release build, checked against the release's digest on the orchestrator and again on the worker. The unpacked binary has its own pin, which the install checks, and `G.1` on every check run |
| Unit | `aisec-agent-job`, transient: a throwaway account, a read-only file system, localhost only, a 2 GB memory limit, a 15-minute time limit. Exposure score 1.3, the same as the model server |
| Tools | One, and only the ones named on the command line. `--no-profile` keeps Goose from loading its own, including the one that runs shell commands. That option also disables tools declared in a recipe. The planned tool service integration will omit it and use an empty configuration directory. This approach was tested on a workstation; it has not been tested on the worker |
| Session | Goose writes a session database and a log of every prompt, even when told to keep no session. Both land in the unit's private `/tmp`, which systemd deletes when the unit stops |
| One at a time | The unit's name is fixed. A second run is refused while one exists |
| Today's tool | A fixture on the worker that returns one piece of synthetic evidence. The [tool service](../security/tool-service.md) on the orchestrator replaces it. The service is deployed. The job runner still starts Goose with the fixture, and the current worker unit permits only localhost connections |
| Procedure | The [agent runtime runbook](../runbooks/agent-runtime.md) |

## Measured

Empty, about 20 minutes after boot: 0.5 of 7.9 GiB memory used, CPU 99 to 100 % idle, 2.0 GB of disk. cloud-init finished 72 seconds after boot.

With the model loaded, on 2026-10-19, llama.cpp `b11669`:

| | |
| --- | --- |
| Memory | 5.30 GB resident, of which 2.0 GB is the mapped model file. 4.1 GB available for everything else |
| Prompt processing | 19 tokens per second |
| Generation | 6 tokens per second |
| One tool-call turn, 387 prompt tokens | 25 seconds without thinking, 36 with |
| Start | 3 seconds with the file cached, 26 after a reboot, measured on 2026-10-11 with `b11429` |
| Disk | 5.1 GB used |

One agent run on the same question, through Goose 1.54.0, on 2026-10-12. Goose 1.55.0 with `b11669` on 2026-10-19 took 86 seconds on the first run and 25 and 28 on the next two, with a memory peak of 56 to 59 MB:

| | |
| --- | --- |
| Whole run, two model turns | 24 seconds, median of three. 58 on the first run after the server starts |
| The same with thinking on | 59 seconds, and 97. Thinking is off on the server: it changed no answer |
| Agent memory | 56 MB at its peak, beside the model |
| Prompt | 672 tokens on the first turn. The bare exchange needs 385 |

The exchange and the full tables are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#measurements).

## Planned

| Role | Candidate | Has to prove |
| --- | --- | --- |
| Agent runtime | Goose, installed | Goose's network tool call with a job token on this worker, and validation of the result against a schema. A `curl` call with a job token works from here. Headless runs, a restricted tool set, and a private model endpoint are shown on one fixture. A TLS call to the tool service was tested on a workstation |
| Starting model | Qwen3.5-4B, running | Structured output and tool calling on held-out fixtures. One fixed exchange passes so far |

A workflow hands a job to this machine over SSH, with a key that can only run the job runner ([ADR 0012](../decisions/0012-dispatch-over-ssh-with-a-forced-command.md)). Decided, not built. The worker can start a connection to two ports on the orchestrator: the proxy and the tool service ([ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)).

## Validation

`C`, `P.5` to `P.11`, `U.3` to `U.5`, `S`, `T.9` to `T.13`, `J.7` to `J.9`, `G`, and `HW` in the [validation pages](../validation/README.md). The `G` checks read what is installed and what a finished job leaves. Nothing checks a run while it lasts.

## Limits

- **Everything on it has to be built for Arm64.**
- **Platform endpoints stay reachable.** The instance metadata service returns a VM's custom data, so no secret goes into the worker's custom data.
- **A rebuild loses everything on it.** The worker was rebuilt from the current template on 2026-10-11, while it was still empty. Now it carries a model, and a rebuild means pushing the inputs and building the model file again, about fifteen minutes.
- **Six tokens per second.** A turn that reads a long prompt takes minutes. This size proves the integration, not the speed.
- **The model port has no key.** Any process on the worker can call it.

## Official documentation

- [Default outbound access and private subnets](https://learn.microsoft.com/azure/virtual-network/ip-services/default-outbound-access)
- [What is IP address 168.63.129.16](https://learn.microsoft.com/azure/virtual-network/what-is-ip-address-168-63-129-16)
