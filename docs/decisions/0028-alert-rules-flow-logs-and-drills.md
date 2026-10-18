# 0028. Alert rules, flow logs, and their drills: flow logs in the bootstrap root, stateful rules, and a drill file

Status: Proposed
Date: 2026-10-18

Adds to [0021](0021-monitoring-in-azure-monitor-over-private-link.md) and [0027](0027-how-the-monitoring-is-built.md): how the alert rules, the flow logs, and the Activity Log rules are built, and how each alert is fired on purpose.

## Context

0021 lists the alert rules, decides flow logs with traffic analytics, and puts the Activity Log rules in the bootstrap root. Building them raised four questions it does not answer.

- **Who may write a flow log.** A virtual network flow log is a child of the region's network watcher. Azure keeps the watchers in `NetworkWatcherRG`, a group it created and that neither deployment identity can reach. Traffic analytics also creates a collection rule and endpoint of its own, and Azure checks that permission on the workspace's subscription. On 2026-10-18 the platform identity, Contributor on the platform group only ([0008](0008-deployment-identities-and-bootstrap-scope.md)), got `TAUserDoesNotHavePermissions` with a role on both watchers.
- **How often a rule fires.** A log alert rule without state fires on every run while its condition holds. A hole in the audit sequence stays in the window for two days, which is 576 alerts at a five-minute frequency.
- **Where an Activity Log rule lives.** In the platform group, the platform identity could delete the rule that watches it.
- **How to fire each alert once without damaging the record.** The sequence and marker alerts read the audit copy. A false line there stays forever, and `L.6` would fail on it from then on.

## Options

For the flow logs:

| Option | Cost |
| --- | --- |
| A custom role with the flow log actions only, on the two platform watchers | Not enough. Traffic analytics was refused with it in place |
| That role, plus collection rule and endpoint write on the whole subscription | The platform identity reaches past its group for the first time, into the targets' group too |
| The bootstrap root writes the flow logs, as the operator | Its state holds two more resources that depend on the platform's networks and workspace, so the platform root is applied first. Every change needs the operator's Owner sign-in |
| Flow logs without traffic analytics | Nothing turns the flow records into rows an alert can read |

For the drills:

| Option | Cost |
| --- | --- |
| Write the drill lines into the real audit copy | The record holds false lines, and `L.6` fails on them forever |
| A second file, collected into the same table | Root on the orchestrator can write it. Root can already append to the real copy |
| Change the rule's query for the drill | The drill proves a query that is not the one running |

## Decision

- **The flow logs are in the bootstrap root.** It reads the two networks and the workspace by name and writes the flow logs, with traffic analytics every 10 minutes, as the operator. Their storage accounts are in the platform state group, one per region, with Entra authentication only. The platform identity gets no role outside its group.
- **Every log alert rule is stateful.** It fires when its condition starts and resolves when it ends. A condition that lasts is one alert.
- **The Activity Log rules sit in the platform state group**, where neither deployment identity holds a role. One rule each for security groups, security rules, role assignments, and policy assignments, on successful writes and deletes in the whole subscription.
- **The drill file is `/var/log/aisec/alert-drill.jsonl` on the orchestrator.** The audit collection rule reads it into the audit table beside the real copy. Its lines carry a `start` that begins with `drill-`. The sequence rule groups by start and file, so a drill line never makes a hole in a real start.
- **Alerts that the checks fire are left to fire.** The checks request a tunnel from the orchestrator (`P.15`), open connections to the internet from the worker and the orchestrator (`C.1`, `E.12`), and log in. Each run raises the Squid, denied flow, and login alerts. An exception for the checks would also be an exception for someone who imitates them.

## Trade-offs

- **The bootstrap root now depends on the platform root.** A build from scratch applies the bootstrap root, the platform root, and the bootstrap root again. The platform identity can still delete a network, and its flow log goes with it.
- **Activity Log alerts have no severity of their own.** The portal shows them without the severity 1 that 0021 gives them. The rule's description says what it watches.
- **A check run raises three or four alerts.** The portal's alert list needs reading with that in mind. A fired alert outside a check run is the one that matters.
- **A drill line is a real row.** The workbook counts it, and the table keeps it for 31 days. Its `start` and `FilePath` mark it.
- **Traffic analytics runs every 10 minutes.** A denied flow shows up to 40 minutes after it happened: the interval, ingestion, and a rule that runs every 10 minutes over 30.
- **The traffic analytics table appears only after its first write.** That rule skips query validation when it is created, so a typo in it shows only when it runs.
