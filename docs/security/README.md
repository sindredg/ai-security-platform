# Security

Everything about what can go wrong, what stops it, and what is still exposed. One page per topic, so a topic can grow with the milestone that works on it instead of stretching one long document.

The method is in [ADR 0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md): threats are written down before the thing they threaten is built, and every security practice is tied to a milestone gate. A practice with no gate behind it is a good intention.

## Topics

| Topic | What it holds | State |
| --- | --- | --- |
| [Threat model](threat-model.md) | Scope, assets, attackers, six trust boundaries, and 36 threats with the control and the gate for each | First pass, revised after milestone 2 |
| [AI-specific threats](ai-threats.md) | Eight threats that exist because a model reads untrusted text and can act on it | First pass. Most controls arrive in milestone 3 |
| [Credential inventory](credentials.md) | Every secret: where it lives, who can read it, how it is rotated | Current through milestone 2 |
| [Hardening](hardening.md) | The baseline on the VMs and the cluster, benchmark results, what was left alone, and what is open | Current through milestone 2 |
| [Accepted risks and open items](accepted-risks.md) | Risks carried on purpose, and threats that no decision covers yet | Current through milestone 2 |
| [Lab against production](lab-vs-production.md) | Where this lab cuts a corner, and what a production deployment would do instead | First pass |

## Planned topics

No page yet. Each gets one when the milestone that builds it starts.

| Topic | Question it answers | Milestone |
| --- | --- | --- |
| Tool services and job identity | How a tool call proves which job it belongs to, and what the policy check refuses | 3 |
| Audit log | What is recorded, where it is stored, and who can delete it | 3 |
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

1. **A compromised orchestrator is the end.** It holds every credential that matters and reaches any host on port 443. Accepted.
2. **One operator.** One Azure account owns both sides and one GitHub account approves every change. Accepted.
3. **The tool services are the wall, and they are not designed yet.** Every limit on the AI worker will end at one service that reads hostile input.
4. **Nothing watches the machines.** No audit daemon, no remote logs, no alerting.
5. **The orchestrator has not been rebuilt.** Its template and the running machine agree only because the same text was applied by hand. The worker was rebuilt from its template and passed every check. Accepted.
