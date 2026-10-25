# Security

Everything about what can go wrong, what stops it, and what is still exposed. One page per topic, so a topic can grow with the milestone that works on it instead of stretching one long document.

The method is in [ADR 0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md): threats are written down before the thing they threaten is built, and every security practice is tied to a milestone gate. A practice without a gate has no check that it was done.

## Topics

| Topic | What it holds | State |
| --- | --- | --- |
| [Threat model](threat-model.md) | Scope, assets, attackers, six trust boundaries, and the threats at each, with the control and the gate for each | First pass. States reviewed on 2026-10-15, and revised on 2026-10-16 to 2026-10-19 as milestone 3a was decided, built, reviewed, and measured. Dispatch and Argo rows moved on 2026-10-21, after the first workflows. States read again on 2026-10-23 for the milestone 3 close. Rows moved through milestone 4, the last on 2026-10-25 for the comparison. The page's status line lists each revision |
| [AI-specific threats](ai-threats.md) | Threats that exist because a model reads untrusted text and can act on it | First pass. States reviewed on 2026-10-15. A4 and A6 moved on 2026-10-18, A6 and A7 on 2026-10-21, and A3, A4, and A6 on 2026-10-23. A1, A3, and A7 moved on 2026-10-25 for the comparison. The page's status line lists each move |
| [Tool service and job identity](tool-service.md) | Job authentication, tool authorization, and audit fields | Deployed on 2026-10-15, redeployed on 2026-10-16 with numbered audit lines. The deployment and one round trip from the worker are tested on the running system. Since 2026-10-25 it keeps NetBox's evidence per job and hands the model only the fields each schema names, verified on the live service |
| [Credential inventory](credentials.md) | Every secret: where it lives, who can read it, how it is rotated | Current on 2026-10-25. Milestone 4 added NetBox's secrets and tokens, the targets' update key, and NetBox's observer key. The Argo executor's token, in use since 2026-10-21, does not expire |
| [Hardening](hardening.md) | The baseline on the VMs and the cluster, benchmark results, what was left alone, and what is open | Current on 2026-10-25, with the target VMs and NetBox's containers from milestone 4. kube-bench ran again on 2026-10-23 with the same result, and its 50 warnings were read one by one. Lynis ran on 2026-10-19. One kube-bench fail is not explained ([#127](https://github.com/sindredg/ai-security-platform/issues/127)), and no pod has a limit on its processes ([#166](https://github.com/sindredg/ai-security-platform/issues/166)). The comparison step's pod added on 2026-10-25 |
| [Supply chain](supply-chain.md) | Which artifacts are pinned, where each pin is checked before the artifact runs, and which signatures are checked | Written on 2026-10-23 from the code and the release pages. K3s's system images come from the release's archive since the same day ([ADR 0033](../decisions/0033-k3s-system-images-from-the-release-archive.md)). NetBox's image added on 2026-10-24, and the tool service's packages read again on 2026-10-25 |
| [Accepted risks and open items](accepted-risks.md) | Risks carried on purpose, and threats that no decision covers yet | Current on 2026-10-26: Goose's own `load_skill` and the 24 hours a transcript is kept were added, and operator sessions to targets moved to milestone 6. The converter's advisories were read again on 2026-10-19, at the new llama.cpp commit |
| [Audit log](audit-log.md) | Where the tool service's audit lines are stored, and who can change them | Verified on 2026-10-16: both copies run on the live VMs ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)). Verified on 2026-10-17: each line also reaches Azure Monitor ([worklog](../worklogs/0004-edge-network-and-monitoring.md#monitoring)) |
| [Lab against production](lab-vs-production.md) | Controls to retain, lab limitations, and risks that production infrastructure cannot remove | Rewritten on 2026-10-14. States moved on 2026-10-16 and 2026-10-18. A row for the comparison's stop added on 2026-10-25 |

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

1. **A compromised orchestrator can control the platform.** It holds every credential that matters. Its only way out is Squid on the edge VM, since 2026-10-17 ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)). During a fetch window it can still upload to a listed host (T40).
2. **One operator.** One Azure account owns both sides and one GitHub account approves every change. Accepted.
3. **Tool authorization relies on custom code.** The service is implemented, its rejection cases are tested in CI, and it is deployed. Since 2026-10-21 workflows dispatch jobs to the worker, and each job's tool calls go through it ([worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows)). See [ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md).
4. **Monitoring is incomplete.** The audit lines, the worker's journal, Squid's log, logins, and load reach a Log Analytics workspace over Private Link, which no VM can read or delete from ([monitoring](../components/monitoring.md)). Alert rules show in the portal and send nothing, so an alert waits for someone to look. No audit daemon runs.
5. **The platform has never been rebuilt as a whole.** The worker and the orchestrator were each rebuilt once, on 2026-10-11 and 2026-10-13, and passed every check. Their templates have changed since, and neither has booted from the current one. The router and the edge were built once, on 2026-10-17. A full rebuild from an empty subscription has not been tested. Accepted.
