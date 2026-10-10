# Private AI security operations platform

Self-hosted AI workers investigate security findings on a service they don't run, and propose fixes that have already been tested. Nothing reaches the service without a human approving the exact change.

The split of work is strict. Ordinary tools collect evidence and establish facts. AI interprets the evidence and proposes a bounded change. Neither gets to approve anything.

## Status

Planning. Nothing is deployed yet. The documents below are the design and the evidence behind the first decisions.

| Area | State |
| --- | --- |
| Architecture and decision records | Drafted |
| Azure preflight (quota, VM size availability) | Done, see the worklog |
| Terraform, platform, targets, workflows | Not started |

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
| [Troubleshooting](docs/troubleshooting/README.md) | Failures worth remembering |
| [Worklogs](docs/worklogs/README.md) | What was done, with commands and evidence |

## What this is not

- Not production. One node, one operator, no high availability, no compliance claim.
- Not real data. All inventory in the target is synthetic.
- Not protection from the cloud provider. The design trusts Azure and the platform administrator, and says so. See [trust boundaries](docs/architecture.md#trust-boundaries).
