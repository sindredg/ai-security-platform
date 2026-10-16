# Security

Everything about what can go wrong, what stops it, and what is still exposed. One page per topic, so a topic can grow with the milestone that works on it instead of stretching one long document.

The method is in [ADR 0010](../decisions/0010-threat-model-and-security-checks-per-milestone.md): threats are written down before the thing they threaten is built, and every security practice is tied to a milestone gate. A practice without a gate has no check that it was done.

## Topics

| Topic | What it holds | State |
| --- | --- | --- |
| [Threat model](threat-model.md) | Scope, assets, attackers, six trust boundaries, and 43 threats with the control and the gate for each | First pass. States reviewed on 2026-10-15. Rows decided by ADRs 0020 to 0025 moved, and T37 to T43 added, on 2026-10-16 |
| [AI-specific threats](ai-threats.md) | Eight threats that exist because a model reads untrusted text and can act on it | First pass. States reviewed on 2026-10-15 |
| [Tool service and job identity](tool-service.md) | Job authentication, tool authorization, and audit fields | Deployed on 2026-10-15, redeployed on 2026-10-16 with numbered audit lines. The deployment and one round trip from the worker are tested on the running system |
| [Credential inventory](credentials.md) | Every secret: where it lives, who can read it, how it is rotated | Current on 2026-10-16. The SSH certificate authority and its certificates are in use. The dispatch key and the other milestone 3a credentials are decided and have not been created |
| [Hardening](hardening.md) | The baseline on the VMs and the cluster, benchmark results, what was left alone, and what is open | Current on 2026-10-16. The benchmark results predate the orchestrator rebuild |
| [Accepted risks and open items](accepted-risks.md) | Risks carried on purpose, and threats that no decision covers yet | Current on 2026-10-16 |
| [Audit log](audit-log.md) | Where the tool service's audit lines are stored, and who can change them | Verified on 2026-10-16: both copies run on the live VMs ([worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies)) |
| [Lab against production](lab-vs-production.md) | Controls to retain, lab limitations, and risks that production infrastructure cannot remove | Rewritten on 2026-10-14. States moved on 2026-10-16 |

## Planned topics

No page yet. Each gets one when the milestone that builds it starts.

| Topic | Question it answers | Milestone |
| --- | --- | --- |
| Supply chain | Which artifacts are pinned by digest, which signatures are checked, and where an SBOM is needed | 3, 4, 8 |
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

1. **A compromised orchestrator can control the platform.** It holds every credential that matters and reaches any host on TCP 443 and 80. Accepted until milestone 3a builds the edge proxy of [ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md).
2. **One operator.** One Azure account owns both sides and one GitHub account approves every change. Accepted.
3. **Tool authorization relies on custom code.** The service is implemented, its rejection cases are tested in CI, and it is deployed. One round trip from the worker is tested on the running platform. Dispatch is not built. See [ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md).
4. **Monitoring is incomplete.** No audit daemon, remote log collection, or alerting is configured. The audit lines and the worker's journal are copied to append-only files on the orchestrator, where root can still edit them. Log storage outside the VMs and alerts are decided for [milestone 3a](../roadmap.md#3a-edge-network-and-monitoring) ([ADR 0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md)).
5. **Each VM has been rebuilt once, and never both together.** The worker and the orchestrator were each rebuilt from their templates and passed every check. A full rebuild from an empty subscription has not been tested. Accepted.
