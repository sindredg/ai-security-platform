# Accepted risks and open items

## Accepted risks

These have no control and no gate. They are carried on purpose.

- **T05:** a compromised orchestrator can send anything anywhere on port 443, and in cleartext on port 80. [ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) denies egress to pods, which will narrow this to root on the host once it is built. Closing port 80 was tried and costs more than it removes. See [troubleshooting 03](../troubleshooting/03-proxy-cannot-fetch-upstream-over-tls.md).
- **T15, T30:** a takeover of the operator's GitHub or Azure account defeats the design.
- **Provider compromise:** Azure, GitHub, and the mesh VPN provider are trusted.
- **Single approver:** nobody checks the operator.
- **T31:** the bootstrap state has one copy off the operator machine, uploaded by hand after each apply. A forgotten upload leaves the copy behind the real thing, and a restore from it has not been run. Losing both costs imports, not resources.
- **No CIS benchmark result for the operating system.** No tool has a CIS profile for Ubuntu 26.04 yet: not ComplianceAsCode 0.1.82, and not the vendor's Ubuntu Security Guide. A Lynis audit stands in. Run the CIS profile when either ships one.
- **Push protection is not tested.** Secret scanning with push protection is read as enabled on the repository. No secret was pushed to see it refused, because a real secret must not go to a public repository and a fake one proves little. The secret scan in the pipeline has been seen to fire once, on a false positive.
- **The orchestrator has not been rebuilt from its current template.** It was changed by hand to match cloud-init. The worker was rebuilt on 2026-10-11 and passed every [validation check](../validation/README.md), so the worker template is proven and the orchestrator's is not. An orchestrator rebuild takes a new mesh VPN key, a signed node, and K3s from nothing, and was not run. The first real one is the test.
- **The workstation:** out of scope. A deployment key taken from it is covered by T29.

## Open items

Threats that no decision or gate covers yet. Each needs an answer before the milestone named.

| Item | Threats | Needed before |
| --- | --- | --- |
| Cloud identity for cluster workloads | T36 | Milestone 4 |
| Operator sessions to targets in the audit log | T04 | Milestone 4 |
| What the broker allows into a pull request | A5 | Milestone 5 |
| Repository app permissions | T12 | Milestone 5 |
| Sign-in strength on the operator's accounts cannot be shown by a gate | T15, T30 | Not planned |
