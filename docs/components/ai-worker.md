# AI worker

The machine that will run the agent and the model. It reads advisories, target evidence, and tool output, and any of those can carry instructions. So the design assumes it can be turned, and gives it nothing worth stealing and nowhere to go.

| | |
| --- | --- |
| State | Built, empty. No agent runtime or model yet |
| Where | Sweden Central, `snet-worker`, fixed private address `10.40.0.36` |
| Size | `Standard_D2ps_v6`: 2 vCPUs, 8 GiB, Arm64. Two physical cores for the same quota as one x64 core pair |
| Image | Ubuntu 26.04 LTS, `Canonical:ubuntu-26_04-lts:server-arm64` |
| Disk | 64 GB, Standard SSD |
| Defined in | `infra/platform/compute.tf`, `infra/platform/cloud-init/worker.yaml.tftpl` |
| Decisions | [0005](../decisions/0005-ai-workers-on-a-separate-vm.md), [0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md), [0011](../decisions/0011-package-proxy-for-the-worker.md) |

## What it can reach

| Destination | Result |
| --- | --- |
| The internet | Nothing |
| The target network | Nothing |
| A name server | Nothing. It uses a hosts file |
| The orchestrator, TCP 3128 | The package proxy |
| The orchestrator, any other port | Nothing |

It is not part of the cluster. It installs nothing at first boot, because it has nothing to install from.

## What reaches it

SSH from the orchestrator subnet, and nothing else. Two keys are authorized: the operator's and the orchestrator's feed key.

## Measured

About 20 minutes after boot: 0.5 of 7.9 GiB memory used, CPU 99 to 100 % idle, 2.0 GB of disk. cloud-init finished 72 seconds after boot.

## Planned

| Role | Candidate | Has to prove |
| --- | --- | --- |
| Agent runtime | Goose | Headless runs, a restricted tool set, a private model endpoint |
| Model server | llama.cpp | Tool-call format, memory, throughput on this size |
| Starting model | Qwen3-4B-Instruct-2507, quantized | Structured output and tool calling on held-out fixtures |

How a workflow hands a job to this machine is open. Today the worker cannot start a connection to anything on the orchestrator except the proxy, so dispatch starts from the orchestrator or gets its own rule.

## Validation

`C`, `P.5` to `P.11`, `U.3` to `U.5`, and `HW` in the [validation pages](../validation/README.md).

## Limits

- **Everything on it has to be built for Arm64.**
- **Platform endpoints stay reachable.** The instance metadata service returns a VM's custom data, so no secret goes into the worker's custom data.
- **Not rebuilt from the current template.**

## Official documentation

- [Default outbound access and private subnets](https://learn.microsoft.com/azure/virtual-network/ip-services/default-outbound-access)
- [What is IP address 168.63.129.16](https://learn.microsoft.com/azure/virtual-network/what-is-ip-address-168-63-129-16)
