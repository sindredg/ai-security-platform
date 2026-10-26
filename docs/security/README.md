# Security

Everything about what can go wrong, what stops it, and what is still exposed. One page per topic, so a topic can grow with the milestone that works on it instead of stretching one long document.

The method is in [ADR 0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md): threats are written down before the thing they threaten is built, and every security practice is tied to a milestone gate. A practice without a gate has no check that it was done.

## Topics

| Topic | What it holds | State |
| --- | --- | --- |
| [Threat model](threat-model.md) | Scope, assets, attackers, six trust boundaries, and the threats at each, with the control for each | Current after milestone 4. Each state names its evidence |
| [AI-specific threats](ai-threats.md) | Threats that exist because a model reads untrusted text and can act on it | Current after milestone 4. Each state names its evidence |
| [Tool service and job identity](tool-service.md) | Job authentication, tool authorization, and audit fields | Deployed. Refusals tested in the pipeline and on the live service, with NetBox's evidence kept per job |
| [Credential inventory](credentials.md) | Every secret: where it lives, who can read it, how it is rotated | Current through milestone 4. Most rotation procedures have not been run. The Argo executor's token does not expire |
| [Hardening](hardening.md) | The baseline on the VMs and the cluster, benchmark results, what was left alone, and what is open | Current through milestone 4. One kube-bench fail unexplained ([#127](https://github.com/sindredg/ai-security-platform/issues/127)), and no limit on a pod's processes ([#166](https://github.com/sindredg/ai-security-platform/issues/166)) |
| [Supply chain](supply-chain.md) | Which artifacts are pinned, where each pin is checked before the artifact runs, and which signatures are checked | Read from the code and the release pages. No SBOM |
| [Accepted risks and open items](accepted-risks.md) | Risks carried on purpose, and threats that no decision covers yet | Current. Seven converter advisories are not read yet ([#211](https://github.com/sindredg/ai-security-platform/issues/211)) |
| [Audit log](audit-log.md) | Where the tool service's audit lines are stored, and who can change them | Verified: both copies on the orchestrator (`L`, `J` checks) and in Azure Monitor |
| [Lab against production](lab-vs-production.md) | Controls to retain, lab limitations, and risks that production infrastructure cannot remove | Current through milestone 4 |

## Planned topics

No page yet. Each gets one when the milestone that builds it starts.

| Topic | Question it answers | Milestone |
| --- | --- | --- |
| Pull request content | What the broker allows a worker's proposal to carry into a public page | 5 |
| Incident response | What to do about a compromised worker, a compromised target, or a leaked credential | 6 |

## Validation evidence

| Kind | Where |
| --- | --- |
| Checks that run against the live system | [Validation](../validation/README.md) |
| What was run on which day | [Worklogs](../worklogs/README.md) |
| Why a control is designed the way it is | [Decision records](../decisions/README.md) |
| What each component can and cannot do | [Components](../components/README.md) |

## Standing weak points

The short list, for a reader who opens only this page. Detail is in the topic pages.

1. **A compromised orchestrator can control the platform.** It holds every credential that matters, and its only outbound access is Squid on the edge VM. During a fetch window it can still upload to a listed host (T05, T40).
2. **One operator.** One Azure account owns both sides, and one GitHub account approves every change. Accepted: the design constrains automation, not that person (T15, T30).
3. **Tool authorization relies on custom code.** The tool service checks each call's job, tool, and arguments, and parses what a compromised worker sends. Its refusals are tested in the pipeline and on the live service (T16, T18, T22).
4. **The repository is the approval channel.** A ruleset requires a pull request, its required checks, and the operator's signature on every commit. A tag signed with a separate key approves one delivery. The command that checks it is written and installed, not yet used (T10, T11).
5. **A proposal is a data path to a public page.** The worker reads evidence and proposes a fix. The pull request carries checked fields only, never the answer's text, and none has been opened yet (A5).
6. **Monitoring is incomplete.** Logs reach a workspace that no VM can read or delete from, and alert rules show in the portal and send nothing ([monitoring](../components/monitoring.md)). No audit daemon runs, and the targets ship no logs.
7. **The platform has never been rebuilt as a whole.** No VM has booted from its current template, and no rebuild from an empty subscription has run. Accepted.
