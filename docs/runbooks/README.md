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
| [SSH certificates and the feed account](ssh-certificates.md) | 3a | Implemented on 2026-10-16. Applied once to both running VMs. Revocation, replacement of the authority, and first boot from the templates not run |
| [Repository settings and signed commits](repository-settings.md) | 3a | Implemented on 2026-10-17. Settings made in the web interface and read back. Fail side run once. The API steps not run from the start |
| [Mesh VPN router](mesh-router.md) | 3a | Implemented on 2026-10-17. Run once, on the live platform |
| [Edge VM](edge-vm.md) | 3a | Implemented on 2026-10-17. Run once, on the live platform, partly from scripts. A rebuild of the orchestrator through a fetch window not run |
| [Monitoring](monitoring.md) | 3a | Implemented on 2026-10-17 to 2026-10-19. Run once, on the live platform, alert rules, flow logs, drills, and the daily cap included. Undo and rebuild not run |
