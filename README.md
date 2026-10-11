# Private AI security operations platform

Self-hosted AI workers investigate security findings on a service they don't run, and propose fixes that have already been tested. Nothing reaches the service without a human approving the exact change.

The split of work is strict. Ordinary tools collect evidence and establish facts. AI interprets the evidence and proposes a bounded change. Neither gets to approve anything.

## Target architecture

This is what gets built. The networks, their rules, and the peering exist today. Everything on a VM is planned. Component detail and the reasoning are in the [architecture](docs/architecture.md).

```mermaid
flowchart LR
    Operator["Operator device"]
    Internet["Internet: registries, package mirrors, security feeds, mesh VPN service"]
    GitHub["GitHub: pull requests and approval"]

    subgraph Azure["One Azure subscription"]
        subgraph Platform["Platform: Sweden Central, 10.40.0.0/20"]
            NAT["NAT gateway: the only way out"]

            subgraph Orch["Orchestrator VM, trusted: subnet 10.40.0.0/27"]
                Mesh["Mesh VPN agent and subnet router"]
                Feed["Artifact fetch, verify, push"]
                subgraph K3s["K3s"]
                    Argo["Argo Workflows"]
                    Collect["Collectors and deterministic checks"]
                    Tools["MCP tool services and policy"]
                    Change["PR broker and delivery runner"]
                end
            end

            subgraph Worker["AI worker VM, untrusted: subnet 10.40.0.32/27"]
                Agent["Agent runtime"]
                Model["Model server, CPU inference"]
            end
        end

        subgraph Targets["Targets: Denmark East, 10.50.0.0/20"]
            NetBox["NetBox VM: the service under investigation"]
            Lab["Lab VM: consumer, unintended viewpoint, rehearsal copy"]
        end
    end

    Operator -->|"mesh VPN: SSH and Argo UI"| Mesh
    Orch -->|"outbound only"| NAT
    NAT --> Internet
    NAT --> GitHub

    Argo -->|"dispatch job"| Agent
    Agent --> Model
    Agent -->|"scoped tool calls"| Tools

    Collect -->|"evidence collection"| NetBox
    Tools -->|"named probes and rehearsals"| Lab
    Change -->|"approved change"| NetBox
    Lab -->|"inventory API"| NetBox

    Feed -.->|"verified artifacts over SSH"| Worker
    Feed -.->|"verified artifacts over SSH"| Targets
```

The lines that are missing matter as much as the ones drawn:

- **The AI worker reaches the tool services and nothing else.** No target, no internet, no public DNS.
- **The targets reach nothing outside their own network.** They cannot open a connection into the platform, and they have no internet path.
- **No VM has a public address.** The operator comes in over the mesh VPN. Outbound traffic leaves through one NAT gateway on the orchestrator subnet.
- **The two sides cross only over network peering**, between separate Terraform roots, state, and deployment identities. Every crossing starts on the orchestrator.

## What can go wrong

A suggested fix and a fix that can be trusted are different things. Three failures separate them:

- **The model is wrong.** It proposes a fix that clears the finding and breaks the service.
- **The evidence lies.** A compromised target reports whatever it likes, and an advisory can carry instructions.
- **A worker dies halfway.** The change ends up half applied, or applied twice.

The design is built around those failures. Models run inside the platform, so evidence never leaves it. Workers get narrow tools and no credentials. Every proposal is rehearsed against the service's real consumer before a person sees it, and nothing is delivered without approval of the exact change.

The AI also has to earn its place. Each result is compared with the same workflow run without it.

## Status

The network foundation is deployed: two peered virtual networks, deny-by-default rules, separate state, and a separate deployment identity per side. There is no compute yet.

| Area | State |
| --- | --- |
| Architecture and decision records | Drafted |
| Azure preflight (quota, VM size availability) | Done, see the worklog |
| Network foundation: state, identities, networks, peering | Done, see the [worklog](docs/worklogs/0001-network-foundation.md) |
| Compute, platform components, targets, workflows | Not started |

## Design in brief

- **Platform:** a small K3s cluster for trusted orchestration, plus a separate VM for AI workers and model inference. Sweden Central.
- **Target:** a NetBox inventory service with a real API consumer that must keep working. Denmark East, on its own network.
- **Separation:** platform and targets share a subscription and nothing else. Separate Terraform roots, state, resource groups, networks, and identities.
- **Workflow:** collect evidence, investigate, propose, rehearse on a disposable copy, open a pull request, wait for approval, deliver, verify.
- **Inference:** open-weight models on CPU, inside the platform. No external model API.

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Components, boundaries, networks, capacity |
| [Roadmap](docs/roadmap.md) | Milestones and what each has to prove |
| [Decision records](docs/decisions/README.md) | Why each major choice was made, and what it costs |
| [Runbooks](docs/runbooks/README.md) | Operator procedures, one per milestone |
| [Troubleshooting](docs/troubleshooting/README.md) | Failures worth remembering |
| [Worklogs](docs/worklogs/README.md) | What was done, with commands and evidence |

## What this is not

- Not production. One node, one operator, no high availability, no compliance claim.
- Not real data. All inventory in the target is synthetic.
- Not protection from the cloud provider. The design trusts Azure and the platform administrator, and says so. See [trust boundaries](docs/architecture.md#trust-boundaries).
