# Private AI security operations platform

Self-hosted AI workers investigate security findings on a service they don't run, and propose fixes that have already been tested. Nothing reaches the service without a human approving the exact change.

The split of work is strict. Ordinary tools collect evidence and establish facts. AI interprets the evidence and proposes a bounded change. Neither gets to approve anything.

## Target architecture

This is what gets built. The networks, their rules, the peering, both platform VMs, the mesh VPN, and an empty K3s cluster exist today. Everything that runs on them, and the whole target side, is planned. Component detail and the reasoning are in the [architecture](docs/architecture.md). The diagram source is [`docs/diagrams/target-architecture.html`](docs/diagrams/target-architecture.html).

![Target architecture: a trusted orchestrator VM is the only link between the AI worker, the targets, and the outside world](docs/diagrams/target-architecture.svg)

The blocked paths matter as much as the open ones:

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

The network foundation and the platform VMs are deployed: two peered virtual networks, deny-by-default rules, one egress point, an orchestrator running K3s, and a contained AI worker. Nothing runs on the cluster yet, and there are no targets.

| Area | State |
| --- | --- |
| Architecture and decision records | Drafted |
| Azure preflight (quota, VM size availability) | Done, see the worklog |
| Network foundation: state, identities, networks, peering | Done, see the [worklog](docs/worklogs/0001-network-foundation.md) |
| Platform compute: egress, VMs, mesh VPN, K3s | Done, see the [worklog](docs/worklogs/0002-platform-compute.md) |
| Platform components, targets, workflows | Not started |

## Design in brief

- **Platform:** a small K3s cluster for trusted orchestration, plus a separate VM for AI workers and model inference. Sweden Central.
- **Target:** a NetBox inventory service with a real API consumer that must keep working. Denmark East, on its own network.
- **Separation:** platform and targets share a subscription and nothing else. Separate Terraform roots, state, resource groups, networks, and identities.
- **Workflow:** collect evidence, investigate, propose, rehearse on a disposable copy, open a pull request, wait for approval, deliver, verify.
- **Inference:** open-weight models on CPU, inside the platform. No external model API.

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Boundaries, flows, networks, capacity |
| [Components](docs/components/README.md) | The stack, one page per part, with every version pin and links to vendor documentation |
| [Roadmap](docs/roadmap.md) | Milestones and what each has to prove |
| [Threat model](docs/threat-model.md) | What can go wrong at each trust boundary, the control, and what is left over |
| [Decision records](docs/decisions/README.md) | Why each major choice was made, and what it costs |
| [Runbooks](docs/runbooks/README.md) | Operator procedures, one per milestone |
| [Troubleshooting](docs/troubleshooting/README.md) | Failures worth remembering |
| [Worklogs](docs/worklogs/README.md) | What was done, with commands and evidence |
| [Validation](docs/validation/README.md) | What the platform claims, and the check that proves each claim on the running system |

## What this is not

- Not production. One node, one operator, no high availability, no compliance claim.
- Not real data. All inventory in the target is synthetic.
- Not protection from the cloud provider. The design trusts Azure and the platform administrator, and says so. See [trust boundaries](docs/architecture.md#trust-boundaries).
