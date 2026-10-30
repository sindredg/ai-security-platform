# Runbooks

One operator procedure per milestone, or per slice of a milestone that is built on its own. Each lists the inputs and access it needs, numbered steps with the exact commands, and the expected result of every step. Local values appear as placeholders.

| Runbook | Milestone | Status |
| --- | --- | --- |
| [Network foundation](network-foundation.md) | 1 | Validated on 2026-10-10 |
| [Platform compute](platform-compute.md) | 2 | Implemented on 2026-10-11. Built once. Each VM rebuilt once |
| [Model server](model-server.md) | 3 | Implemented on 2026-10-11. Built once |
| [Agent runtime](agent-runtime.md) | 3 | Implemented on 2026-10-12. Installed once |
| [Tool service](tool-service.md) | 3 | Implemented on 2026-10-15. Deployed once. Deployed again on 2026-10-22 for a new image |
| [Audit log and journal copies](audit-log.md) | 3 | Implemented on 2026-10-16. Installed once. Archive not run |
| [Orchestrator hardening](orchestrator-hardening.md) | 3a | Implemented on 2026-10-16. Applied once to a running orchestrator. First boot from the template not run |
| [SSH certificates and the feed account](ssh-certificates.md) | 3a | Implemented on 2026-10-16. Applied once to both running VMs. Revocation, replacement of the authority, and first boot from the templates not run |
| [Repository settings and signed commits](repository-settings.md) | 3a | Implemented on 2026-10-17. Settings made in the web interface and read back. Fail side run once. The API steps not run from the start |
| [Mesh VPN router](mesh-router.md) | 3a | Implemented on 2026-10-17. Run once, on the live platform |
| [Edge VM](edge-vm.md) | 3a | Implemented on 2026-10-17. Run once, on the live platform, partly from scripts. A rebuild of the orchestrator through a just-in-time (JIT) egress window not run |
| [Workflows and dispatch](workflows.md) | 3 | Implemented on 2026-10-21. Run once, on the live platform. A new dispatch image on 2026-10-22 |
| [Monitoring](monitoring.md) | 3a | Implemented on 2026-10-17 to 2026-10-19. Run once, on the live platform, alert rules, flow logs, drills, and the daily cap included. Undo and rebuild not run |
| [Target VMs](targets.md) | 4 | Implemented on 2026-10-24. Built once and rebuilt once, on the live system, with one update run on each target |
| [NetBox on its VM](netbox.md) | 4 | Implemented on 2026-10-24. Run once, on the live system, from a script. The install ran twice, the second time after a wait that was too short. The seed, implemented on 2026-10-25, ran once from a script, which stopped three times before it ran to its end |
| [Evidence collection and the verification gate for a NetBox job](evidence-collection.md) | 4 | Implemented on 2026-10-25. Run once, on the live system, from two scripts, and the install and one collection again after fixes from a review. The verification gate's steps ran the same day. Undo and the steps after a rebuild not run |
| [Test evidence](test-evidence.md) | Any | Implemented on 2026-10-26. The records of 18 run sets, built from saved output and from the live system |
| [Containment drills](containment-drills.md) | 6 | Ran on 2026-10-28 to 2026-10-30, on the live system |
| [Incident response](incident-response.md) | 6 | Written on 2026-10-31. The containment, rotation, and restore steps have not run; the replacement steps are rebuilds, not run |
