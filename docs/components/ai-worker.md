# AI worker

The machine that runs the agent and the model. It reads advisories, target evidence, and tool output, and any of those can carry instructions. The design assumes it can be compromised and restricts its credentials and network access.

| | |
| --- | --- |
| State | Runs the model server. The agent runtime is installed and runs once per job. The job socket is installed, and workflows dispatch jobs to it since 2026-10-21 ([worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows)) |
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

llama.cpp v0.7.0, build `b11669`, serves Qwen3.5-4B, quantized to `Q4_K_M`, on `127.0.0.1:8080`. Nothing outside the worker can reach it. The model was kept after a comparison with two others ([ADR 0031](../decisions/0031-qwen3-5-4b-stays-the-workers-model.md)), and on exercise 1's held-out cases 13 of 18 of its verdicts were the checks' ([evidence](../evidence/2026-10-25-2308-scored-cases.md)).

| | |
| --- | --- |
| Binaries | `/opt/aisec/llama.cpp/llama-b11669`, the project's release build, checked against its published checksum |
| Model file | `/opt/aisec/models/Qwen3.5-4B-Q4_K_M.gguf`, 2.78 GB. Built here from Qwen's weights, not downloaded ([ADR 0015](../decisions/0015-build-the-model-file-on-the-worker.md)) |
| Unit | `aisec-llama-server.service`: a throwaway account, a read-only file system, localhost only, a 6 GB memory limit |
| Settings | 2 threads, 8192-token context, one slot, no web interface, no RAM prompt cache. A slot save path that is empty and read-only to the server: without one, the server refuses to erase the slot ([troubleshooting 12](../troubleshooting/12-slot-erase-needs-a-save-path.md)) |
| Procedure | The [model server runbook](../runbooks/model-server.md) |

## The agent runtime

Goose 1.56.0, one static binary. It is not a service. A job starts it: the workflow's dispatch step opens an SSH session to the job runner, and the runner hands the job line to a socket that starts one sandboxed unit for that job. The job program in the unit checks the job, writes the recipe, runs Goose, and writes one result line back the same way ([ADR 0030](../decisions/0030-how-a-job-reaches-the-worker.md)).

![One dispatched job: the dispatch step on the orchestrator opens an SSH session to the job runner on the worker, which hands the job over a socket to a sandboxed unit started for that job. The job program checks it and runs Goose, which calls the model server on 127.0.0.1 port 8080 and the tool service on the orchestrator on port 30443 with the job's token. The result goes back the same way](../diagrams/agent-run.svg)

The diagram source is [`diagrams/agent-run.html`](../diagrams/agent-run.html). The operator can still start a run by hand with `run-agent.sh`, against the fixture tool, for the measurement in the [runbook](../runbooks/agent-runtime.md). That run uses a transient unit of its own, `aisec-agent-job`, which permits localhost only.

| | |
| --- | --- |
| Binary | `/opt/aisec/goose/goose-1.56.0/goose`, the project's release build, checked against the release's digest on the orchestrator and again on the worker. The unpacked binary has its own pin, which the install checks, and `G.1` on every check run |
| Unit | For a job, `aisec-agent-job@`, started by the socket: a throwaway account, a read-only file system, localhost and the orchestrator only, a 2 GB memory limit, a 30-minute time limit. For a run by hand, `aisec-agent-job`, transient, localhost only, with a 15-minute time limit. Exposure score 1.3 for the transient unit, the same as the model server |
| Tools | For the fixture run: one, named on the command line. `--no-profile` keeps Goose from loading its own, including the one that runs shell commands, and also disables tools declared in a recipe. For a dispatched job: the recipe's one extension, the tool service, with an empty configuration directory in place of `--no-profile`. Goose adds its own `load_skill` to a dispatched job, which no recipe or setting removes, an [accepted risk](../security/accepted-risks.md). The job program reads the tool list of each request Goose logged, and fails a completed job offered any other tool ([#139](https://github.com/sindredg/ai-security-platform/issues/139)). It refuses a task with template syntax, which Goose would render into the recipe, and one that Goose would run as a shell or slash command. It fails a completed job whose answer it had to cut to fit the result, and gives no call counts without the agent's transcript |
| Session | Goose writes a session database and a log of every prompt, even when told to keep no session. Both land in the unit's private `/tmp`, which systemd deletes when the unit stops |
| One at a time | For a job, the socket takes one connection at a time. For a run by hand, the unit's name is fixed, and a second run is refused while one exists |
| Today's tool | A fixture on the worker that returns one piece of synthetic evidence, used by the standalone measure run, whose unit permits only localhost. A dispatched job uses the [tool service](../security/tool-service.md) on the orchestrator instead: its unit adds the orchestrator's address to localhost, and a job over the socket called the tool service there with a job token on 2026-10-20 |
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

## Dispatch

A workflow hands a job to this machine over SSH, with a key that can only run the job runner ([ADR 0012](../decisions/0012-dispatch-over-ssh-with-a-forced-command.md)). The runner logs in as `aisec-job` and connects to a socket that starts the agent's sandboxed unit, one job at a time ([ADR 0030](../decisions/0030-how-a-job-reaches-the-worker.md)). The result comes back on the same session, with the agent's transcript. The socket, the runner, and the job unit are installed on the worker, and jobs have run over them by hand with a token since 2026-10-20, with the slot erased between jobs ([worklog](../worklogs/0003-toolchain-integration.md#installed-and-run-on-the-worker)). Since 2026-10-23 the job program erases the slot before each job as well, and refuses the job when that fails, seen with the model server stopped ([0032](../decisions/0032-erase-the-slot-before-each-job-and-refuse-on-failure.md), [worklog](../worklogs/0003-toolchain-integration.md#installed-the-erase-before-each-job-and-the-answer-lines)). Since 2026-10-21 the workflow's dispatch step opens that session: a round trip, a stopped workflow, and two workflows in turn ran through it ([worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows)). The worker can start a connection to the tool service's port on the orchestrator ([ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)) and to the proxy on the edge, and to nothing else.

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
