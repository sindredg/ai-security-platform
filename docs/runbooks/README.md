# Runbooks

One operator procedure per milestone, or per slice of a milestone that is built on its own. Each lists the inputs and access it needs, numbered steps with the exact commands, and the expected result of every step. Local values appear as placeholders.

| Runbook | Milestone | Status |
| --- | --- | --- |
| [Network foundation](network-foundation.md) | 1 | Validated on 2026-10-10 |
| [Platform compute](platform-compute.md) | 2 | Implemented on 2026-10-11. Built once. Each VM rebuilt once |
| [Model server](model-server.md) | 3 | Implemented on 2026-10-11. Built once |
| [Agent runtime](agent-runtime.md) | 3 | Implemented on 2026-10-12. Installed once |
| [Tool service](tool-service.md) | 3 | Implemented on 2026-10-15. Deployed once |
| [Audit log and journal copies](audit-log.md) | 3 | Implemented on 2026-10-16. Installed once. Archive not run |
| [Orchestrator hardening](orchestrator-hardening.md) | 3a | Implemented on 2026-10-16. Applied once to a running orchestrator. First boot from the template not run |
| [SSH certificates and the feed account](ssh-certificates.md) | 3a | Written, not yet run |
