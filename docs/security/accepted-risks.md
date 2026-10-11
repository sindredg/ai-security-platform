# Accepted risks and open items

## Accepted risks

These have no control and no gate. They are carried on purpose.

- **T05:** a compromised orchestrator can send anything anywhere on port 443.
- **T15, T30:** a takeover of the operator's GitHub or Azure account defeats the design.
- **Provider compromise:** Azure, GitHub, and the mesh VPN provider are trusted.
- **Single approver:** nobody checks the operator.
- **T31:** the bootstrap state has one copy. Losing it costs imports, not resources.
- **No CIS benchmark result for the operating system.** No tool has a CIS profile for Ubuntu 26.04 yet: not ComplianceAsCode 0.1.82, and not the vendor's Ubuntu Security Guide. A Lynis audit stands in. Run the CIS profile when either ships one.
- **The workstation:** out of scope. A deployment key taken from it is covered by T29.

## Open items

Threats that no decision or gate covers yet. Each needs an answer before the milestone named.

| Item | Threats | Needed before |
| --- | --- | --- |
| How a job proves which job it is | T18 | Milestone 3 |
| What stands between a tool service bug and the rest of the orchestrator | T22, T36 | Milestone 3 |
| Where the audit log is stored, and who can delete it | T04, T21 | Milestone 3 |
| What the broker allows into a pull request | A5 | Milestone 5 |
| Repository app permissions | T12 | Milestone 5 |
| Sign-in strength on the operator's accounts cannot be shown by a gate | T15, T30 | Not planned |
