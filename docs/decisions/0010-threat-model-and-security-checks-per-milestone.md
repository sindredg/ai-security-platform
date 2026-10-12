# 0010. A threat model, with security checks tied to milestone gates

Status: Accepted
Date: 2026-10-11

## Context

The design already takes security positions. The architecture has a trust boundary table, assumes the AI worker can be turned, and keeps containment out of the target's reach. Each of those came from looking at one component at a time.

Nothing walks the whole system and asks what can go wrong at each boundary. So there is no list to check a new decision against, and no way to tell which risks are handled, which are accepted, and which were never considered.

The timing matters. Milestone 2 creates the first credentials: the mesh VPN key, the SSH keys the orchestrator uses to feed the other machines, and the cluster token. Milestones 3 to 5 wait on decisions that are security decisions underneath: dispatch to the worker, cloud identity for workloads, worker isolation, and repository permissions.

The lab is small. Its controls should not be. One node and one operator are capacity limits, and the project says so. Weak hardening, unscanned changes, and secrets nobody can rotate would be design faults, and they would follow the design into any larger deployment.

## Options

| Option | What it produces | Problem |
| --- | --- | --- |
| Keep reasoning per decision record | Nothing new | Coverage is whatever each record happened to think of. Gaps between records stay invisible |
| One security review before the drills in milestone 6 | A findings list at the end | Finds problems when they are most expensive to fix. The drills test whatever came to mind that week |
| A compliance framework: ISO 27001, SOC 2, or a full NIST CSF programme | Policies, roles, and audit evidence | These describe an organisation. With one operator they produce paperwork about people who do not exist. A mapping to one of them would be the same paperwork in a smaller font |
| A threat model now, and technical baselines attached to the milestone that builds what they cover | One list of threats and controls, with checks in the completion criteria | Costs a document before compute, and upkeep after |

## Decision

Write the threat model before any VM exists. Keep it current. Attach each supporting practice to the milestone that builds the thing it checks.

**The threat model**

It lives in `docs/security/threat-model.md`. The parts listed below that are not threats per boundary have their own pages in `docs/security/` since 2026-10-11.

- **Method:** STRIDE, applied to each trust boundary on the existing diagrams.
- **A second pass for the AI parts,** using the OWASP Top 10 for LLM Applications and MITRE ATLAS. STRIDE has no good place for instructions hidden in evidence, or for an agent with more reach than its job needs.
- **One table at the core:** threat, boundary, control, where the control is verified, and the risk left over. "Verified" means a roadmap gate or a drill, not a sentence.
- **The credential inventory:** every secret, where it lives, what can read it, and how it is rotated.
- **Lab against production:** for each deliberate lab compromise, what a production deployment would use instead. The mesh VPN, the single operator, the single node, and unfiltered orchestrator egress all belong here.
- **The operator workstation is out of scope.** This project is the infrastructure. The model covers what a key taken from that machine can reach, not how the machine is kept.
- **It stays small.** One table of a few dozen threats, each rated high, medium, or low. No scoring scheme.

Later decision records name the threats they answer. Milestone 6 is the test: every threat rated high maps to a drill or to a stated accepted risk.

**Supporting practices**

| Practice | What it checks | Lands in |
| --- | --- | --- |
| Repository protection | Secret scanning with push protection, and a ruleset on `main`: pull request required, no force push, checks required | Milestone 2 |
| Static checks on pull requests | Checkov and Trivy on Terraform and manifests, and a secret scan over the history | Milestone 2 |
| Dependency updates | Automated pull requests for Terraform providers and pipeline actions, so a pin has a way to move | Milestone 2 |
| Hardening baselines | The CIS benchmarks for the operating system and Kubernetes, and the K3s hardening guide | Milestone 2 |
| Credential inventory and rotation | Each new secret is listed before it is created. Long-lived ones get a rotation procedure that has been run once | Milestone 2, then every milestone |
| Audit log | Every tool call recorded with caller, job, and decision, somewhere the worker cannot write | Milestone 3 |
| Supply chain | Images and the model pinned by digest, signatures verified where upstream signs. An SBOM where an exercise needs one | Milestones 3 and 4, SBOM in milestone 8 |
| Incident response runbook | What to do about a turned worker, a compromised target, and a leaked credential | Milestone 6 |

Repository protection is not housekeeping. In milestone 5 the repository becomes the approval channel, and approval binds to a commit. A `main` that accepts a force push makes that binding worthless.

The Azure side gets no benchmark of its own. Checkov already runs those checks against the Terraform, and a second pass would find the same things.

Target VMs are rebuilt, not patched. They are disposable by design, and a rebuild from a newer pin is the update.

Three rules keep these honest:

- **A failed benchmark check is fixed or accepted in writing, with the reason.** A benchmark is a checklist someone else wrote for a general case. Passing all of it is not the goal.
- **The pipeline holds no cloud credentials and runs no plans.** Its checks are static. Third-party actions are pinned by commit, and the workflow token is read-only. Applies stay on the workstation, from a saved plan.
- **A suppressed scanner finding carries its reason next to the suppression.**

## Trade-offs

- **Compute waits for one document.** The network exists and nothing runs on it. That is the cheapest moment there will be.
- **The designer writes the model.** It shares the design's blind spots, and nobody independent reviews it. The published threat lists catch some of what one person misses, not all of it.
- **A stale model is worse than none.** It reads as coverage. The tie to decision records and to milestone 6 is what keeps it current, and that tie is a habit, not a mechanism.
- **Benchmarks will fail checks this design cannot meet.** A single-node cluster and machines without DNS will not satisfy every item. Each accepted failure is work to justify.
- **The pipeline is a new component next to the repository.** Pinning, a read-only token, and no secrets limit what a hijacked action can do. They do not remove the trust placed in the hosted runner.
- **One person writes and approves every change.** The required checks are the only second reader there is. They catch what a scanner can express and nothing else.
- **Update pull requests are noise too.** Each one still needs its plan read. Ignoring them turns the pins back into the problem they were meant to solve.
- **Scanners are noisy.** Every false positive costs a suppression, and suppressions are where real findings go to hide.
- **The threat model is public.** It lists the weak points of a running lab. The lab holds synthetic data and nothing in it relies on being unknown, so this is accepted. An unfixed weakness with real exposure gets fixed before it gets published.
- **None of this is a compliance claim.** It makes the controls defensible. It does not make the lab production.
