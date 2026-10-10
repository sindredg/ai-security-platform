# Private AI security operations platform

Self-hosted AI workers investigate security findings on a service they don't run, and propose fixes that have already been tested. Nothing reaches the service without a human approving the exact change.

The split of work is strict. Ordinary tools collect evidence and establish facts. AI interprets the evidence and proposes a bounded change. Neither gets to approve anything.

## Why

Organizations that run sensitive infrastructure want AI to take over the slow parts of security work: investigating a finding and working out a safe fix. What stops them is control. The evidence is exactly the data they cannot hand to an outside model, and an unreviewed change to production is not something anyone signs off on.

This project is a design for getting the first without giving up the second: less investigation and remediation effort, with the data and every change still under the organization's control.

The engineering problem is making that hold when things go wrong. Self-hosted models, constrained tools, independent validation, and auditable approval have to work together so that a change is only delivered if it keeps the service working. That must stay true when the AI's proposal is wrong, when the evidence has been tampered with, and when a worker fails halfway through.

Whether the AI is worth its cost is an open question, not an assumption. Every result is measured against the same workflow run with ordinary automation alone.

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
