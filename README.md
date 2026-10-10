# Private AI security operations platform

An infrastructure project that investigates security findings on a separately managed service with self-hosted AI workers, and proposes tested fixes as pull requests. Deterministic tools collect and verify facts. AI workers interpret evidence and propose bounded changes. A human approves every change before it reaches a persistent target.

## Status

Planning. No infrastructure is deployed. The documents below describe the planned design and the evidence behind the first decisions.

| Area | State |
| --- | --- |
| Architecture and decision records | Drafted |
| Azure preflight (quota, SKU availability) | Done, see the worklog |
| Terraform, platform, targets, workflows | Not started |

## Design in brief

- **Platform:** a small K3s cluster for trusted orchestration and a separate VM for AI workers and model inference, in Sweden Central.
- **Targets:** a NetBox inventory service with a legitimate API consumer, in Denmark East on its own network.
- **Separation:** platform and targets have separate Terraform roots, state, resource groups, networks, and deployment identities.
- **Workflow:** collect evidence, investigate, propose a change, rehearse it on a disposable copy, open a pull request, wait for approval, deliver, verify.
- **Inference:** open-weight models on CPU inside the platform. No external model API.

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | The planned system: components, boundaries, networks, capacity |
| [Roadmap](docs/roadmap.md) | Milestones and their exit gates |
| [Decision records](docs/decisions/README.md) | One record per consequential architecture choice |
| [Troubleshooting](docs/troubleshooting/README.md) | Failures that revealed something about the system or a procedure |
| [Worklogs](docs/worklogs/README.md) | What was done per milestone, with commands and evidence |

## Scope limits

- This is a lab. It makes no compliance claim and does not demonstrate production high availability.
- All inventory data in the target is synthetic.
- The design trusts the cloud provider and privileged platform administration. See [Architecture](docs/architecture.md#trust-boundaries).
