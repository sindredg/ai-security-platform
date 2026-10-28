# Validation

What the platform claims, and the check that proves each claim against the running system.

The [worklogs](../worklogs/README.md) are history: what was run on which day. These pages are the present: every claim has an ID, a reason, and a check that can be run again in about two minutes.

## Run the checks

From a workstation on the mesh VPN, signed in to Azure as the operator. The `Z` checks need `python3`. `P.19` and `P.21` need `terraform`, on the `PATH` or named by `TERRAFORM`, to render the edge template. `VN.9`, `VL.9`, and `N.5` need a checkout of the targets repository, named by `AISEC_TARGETS`:

```bash
export AISEC_SSH="ssh -o UserKnownHostsFile=REPLACE_WITH_KNOWN_HOSTS_FILE -o StrictHostKeyChecking=yes -i REPLACE_WITH_OPERATOR_KEY -o CertificateFile=REPLACE_WITH_OPERATOR_KEY.aisec-cert.pub -o IdentitiesOnly=yes"
export AISEC_USER_CA=REPLACE_WITH_CA_PUBLIC_KEY_FILE
export AISEC_TARGETS=REPLACE_WITH_TARGETS_CHECKOUT
validation/platform-checks.sh
```

Expected: one `PASS` line per check, a summary, and exit `0`. A `FAIL` prints what was expected and what was found, and the script exits `1`.

| Option | Effect |
| --- | --- |
| `--no-azure` | Skips the `Z` checks and `O.5` to `O.13`. The rest need no Azure sign-in |
| `--no-workstation` | Skips the `M` checks, which test the mesh policy from the machine that runs the script |

A connection check reports `open`, `refused`, `timeout`, or `unreachable`, and each check expects exactly one of them. [Containment](containment.md#what-a-failed-connection-proves) says why.

The script changes nothing. It opens connections that should fail, reads settings, and asks Azure to validate one template that it never deploys.

## Areas

| Page | Checks | What it covers |
| --- | --- | --- |
| [Access](access.md) | `A`, `M`, `R` | Who can get in, and through what |
| [Containment](containment.md) | `C`, `E`, `Z.4` to `Z.9`, `Z.13` to `Z.30` | What the worker and the orchestrator cannot reach, and what they can |
| [Targets](targets.md) | `VN`, `VL`, `N`, `Q`, `D`, `U.14`, `U.15` | The NetBox and lab VMs: logins, update runs, and no way out. NetBox: its image, port, and secrets. The staging copy, and delivery |
| [Package proxy](package-proxy.md) | `P`, `U` | Squid on the edge, the one path out for the orchestrator and the worker, the just-in-time (JIT) egress window, and whether updates arrive |
| [Model server](model-server.md) | `S` | The server runs, listens on loopback only, keeps its sandbox, and loads the file the build made |
| [Agent runtime](agent-runtime.md) | `G` | The Goose binary and the fixture are the pinned ones, and no finished job leaves its unit or its files |
| [Cluster](cluster.md) | `K` | K3s health and the hardening benchmark findings |
| [Workflows](workflows.md) | `W` | Argo's controller, kept to `orchestration` and to templates, the template itself, the dispatch secret, and that no workload account may change config maps in `orchestration` |
| [Tool service](tool-service.md) | `T` | The deployed tool service (an MCP server): its pod, namespaces, network paths, and certificate |
| [Audit log](audit-log.md) | `L`, `J` | The copier that stores the tool service's audit lines, the pull of the worker's journal, and the append-only files they write |
| [Monitoring](monitoring.md) | `O` | The log agents, their hosts entries, the workspace and its scope, heartbeats, and the identities |
| [Host hardening](host-hardening.md) | `HO`, `HW`, `HR`, `HE`, `HN`, `HL` | SSH daemon, kernel settings, file modes, on every VM |
| [Azure policy](azure-policy.md) | `Z.1` to `Z.3`, `Z.10` to `Z.12` | Public addresses and the policy that refuses them |
| [Investigation](investigation.md) | None: scored per job | Exercise 1's investigation on held-out cases, the rules that score it, and the run without the agent beside it |

## Last run

From `a4f3b32`, ending at 15:40 UTC on 2026-10-28, after the accounts in the job line went live: 425 of 426 passed. `U.7` failed because the mesh VPN agent's upstream released 1.104.4 while the pin holds 1.104.2 ([worklog](../worklogs/0006-remediation-pull-requests-and-delivery.md#accounts-in-the-job-line)).

Each earlier run is in the worklog of its milestone, with what it was run for: [0002](../worklogs/0002-platform-compute.md), [0003](../worklogs/0003-toolchain-integration.md), [0004](../worklogs/0004-edge-network-and-monitoring.md), [0005](../worklogs/0005-netbox-target-and-exercise-1.md), and [0006](../worklogs/0006-remediation-pull-requests-and-delivery.md).

## What the checks do not cover

- **A rebuild of everything at once.** Each VM has been rebuilt from its template and passed every check, the worker on 2026-10-11 and the orchestrator on 2026-10-13. Both together, or from an empty subscription, has not been run.
- **The target side's later parts.** The unintended viewpoint is not built yet, and the staging copy has no checks for its secrets and database yet ([#186](https://github.com/sindredg/ai-security-platform/issues/186)). NetBox, its seed, and the collect command are checked by the [`N` checks](targets.md#netbox).
- **The agent runtime during a run.** The [`G` checks](agent-runtime.md) read what is installed and what a finished job leaves. The transient unit's sandbox and the tools a run loads are not checked.
- **The tool service's round trip and audit lines.** They are steps in the [runbook](../runbooks/tool-service.md#round-trip), because they register and revoke jobs. Its rejection cases are tested in CI, and the [tool service checks](tool-service.md) read the deployment.
- **Anything a benchmark tool finds.** kube-bench and Lynis results are in the [milestone 2 worklog](../worklogs/0002-platform-compute.md). The checks here hold the fixes in place.
- **Clean Terraform plans.** `terraform plan -detailed-exitcode` needs each root's own identity. The [runbook](../runbooks/platform-compute.md) has that step.
