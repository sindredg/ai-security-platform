# Security

Everything about what can go wrong, what stops it, and what is still exposed. One page per topic, so a topic can grow with the milestone that works on it instead of stretching one long document.

The method is in [ADR 0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md): threats are written down before the thing they threaten is built, and every security practice is tied to a milestone gate. A practice with no gate behind it is a good intention.

## Topics

| Topic | What it holds | State |
| --- | --- | --- |
| [Threat model](threat-model.md) | Scope, assets, attackers, six trust boundaries, and 36 threats with the control and the gate for each | First pass. States read again on 2026-10-14 |
| [AI-specific threats](ai-threats.md) | Eight threats that exist because a model reads untrusted text and can act on it | First pass. States read again on 2026-10-14 |
| [Tool service and job identity](tool-service.md) | How a tool call proves which job it belongs to, what is refused, and what the audit line holds | Written with the service. Nothing in it is tested on the running system |
| [Credential inventory](credentials.md) | Every secret: where it lives, who can read it, how it is rotated | Current on 2026-10-14. Four milestone 3 credentials are decided and not made |
| [Hardening](hardening.md) | The baseline on the VMs and the cluster, benchmark results, what was left alone, and what is open | Current through milestone 2. The benchmark results predate the orchestrator rebuild |
| [Accepted risks and open items](accepted-risks.md) | Risks carried on purpose, and threats that no decision covers yet | Current on 2026-10-14 |
| [Lab against production](lab-vs-production.md) | What carries over to production as it is, where this lab cuts a corner and what that leaves open, and what no deployment solves | Rewritten on 2026-10-14 |

## Planned topics

No page yet. Each gets one when the milestone that builds it starts.

| Topic | Question it answers | Milestone |
| --- | --- | --- |
| Audit log | Where the lines are stored, and who can delete them. What is recorded is on the [tool service](tool-service.md#the-audit-line) page | 3 |
| Supply chain | Which artifacts are pinned by digest, which signatures are checked, and where an SBOM is needed | 3, 4, 8 |
| Pull request content | What the broker allows a worker's proposal to carry into a public page | 5 |
| Incident response | What to do about a turned worker, a compromised target, or a leaked credential | 6 |

## Where the proof is

| Kind | Where |
| --- | --- |
| Checks that run against the live system | [Validation](../validation/README.md) |
| What was run on which day | [Worklogs](../worklogs/README.md) |
| Why a control is designed the way it is | [Decision records](../decisions/README.md) |
| What each component can and cannot do | [Components](../components/README.md) |

## Standing weak points

The short list, for a reader who opens only this page. Detail is in the topic pages.

1. **A compromised orchestrator is the end.** It holds every credential that matters and reaches any host on TCP 443 and 80 and on any UDP port. Accepted.
2. **One operator.** One Azure account owns both sides and one GitHub account approves every change. Accepted.
3. **The tool service is the wall, and it is written but not deployed.** Every limit on the AI worker will end at one small custom service that reads hostile input. Its refusals are tested in the pipeline. Nothing about it is tested on the running system yet. See [ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md).
4. **Nothing watches the machines.** No audit daemon, no remote logs, no alerting. The tool service prints an audit line that nothing stores yet.
5. **Each VM has been rebuilt once, and never both together.** The worker and the orchestrator were each rebuilt from their templates and passed every check. A build of everything from nothing has not been run. Accepted.
