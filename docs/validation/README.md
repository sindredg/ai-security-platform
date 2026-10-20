# Validation

What the platform claims, and the check that proves each claim against the running system.

The [worklogs](../worklogs/README.md) are history: what was run on which day. These pages are the present: every claim has an ID, a reason, and a check that can be run again in about two minutes.

## Run the checks

From a workstation on the mesh VPN, signed in to Azure as the operator. The `Z` checks need `python3`. `P.19` and `P.21` need `terraform`, on the `PATH` or named by `TERRAFORM`, to render the edge template:

```bash
export AISEC_SSH="ssh -o UserKnownHostsFile=REPLACE_WITH_KNOWN_HOSTS_FILE -o StrictHostKeyChecking=yes -i REPLACE_WITH_OPERATOR_KEY -o CertificateFile=REPLACE_WITH_OPERATOR_KEY.aisec-cert.pub -o IdentitiesOnly=yes"
export AISEC_USER_CA=REPLACE_WITH_CA_PUBLIC_KEY_FILE
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
| [Containment](containment.md) | `C`, `E`, `Z.4` to `Z.9`, `Z.13` to `Z.25` | What the worker and the orchestrator cannot reach, and what they can |
| [Package proxy](package-proxy.md) | `P`, `U` | Squid on the edge, the one path out for the orchestrator and the worker, the fetch window, and whether updates arrive |
| [Model server](model-server.md) | `S` | The server runs, listens on loopback only, keeps its sandbox, and loads the file the build made |
| [Agent runtime](agent-runtime.md) | `G` | The Goose binary and the fixture are the pinned ones, and no finished job leaves its unit or its files |
| [Cluster](cluster.md) | `K` | K3s health and the hardening benchmark findings |
| [Workflows](workflows.md) | `W` | Argo's controller, kept to `orchestration` and to templates, the template itself, and the dispatch secret |
| [Tool service](tool-service.md) | `T` | The deployed tool service: its pod, namespaces, network paths, and certificate |
| [Audit log](audit-log.md) | `L`, `J` | The copier that stores the tool service's audit lines, the pull of the worker's journal, and the append-only files they write |
| [Monitoring](monitoring.md) | `O` | The log agents, their hosts entries, the workspace and its scope, heartbeats, and the identities |
| [Host hardening](host-hardening.md) | `HO`, `HW`, `HR`, `HE` | SSH daemon, kernel settings, file modes, on every VM |
| [Azure policy](azure-policy.md) | `Z.1` to `Z.3`, `Z.10` to `Z.12` | Public addresses and the policy that refuses them |

## Last run

| Date | Result | Notes |
| --- | --- | --- |
| 2026-10-11 | 92 of 94 passed | After a restart of both VMs. `M.3` and `M.4` failed: the mesh access policy still allowed every port. See [Access](access.md) |
| 2026-10-11 | 94 of 94 passed | After the mesh access policy was replaced |
| 2026-10-11 | 94 of 94 passed | After the worker was rebuilt from the current template |
| 2026-10-12 | 94 of 94 passed | First run of the corrected script, at commit `a9ca766`. Whole-rule comparison in `Z.4` and `Z.5`, and `timeout` expected where a rule is the claim |
| 2026-10-12 | 101 of 101 passed | First run with the seven `S` checks for the [model server](model-server.md) |
| 2026-10-12 | 100 of 101 passed | After the model server restart that turned thinking off. `U.1` failed: three security updates published that day were pending on the orchestrator, before the next unattended run. The seven `S` checks passed |
| 2026-10-13 | 100 of 101 passed | Baseline before the orchestrator rebuild. `U.5` failed: two security updates were pending on the worker. `U.1` passed again after the unattended run |
| 2026-10-13 | 101 of 101 passed | After the [orchestrator rebuild](../worklogs/0002-platform-compute.md#orchestrator-rebuild) and an update run on both VMs. `K.5` and `K.6` passed on settings that first boot applied |
| 2026-10-15 | 102 of 117 to 116 of 119 | Six runs during the [tool service deployment](../worklogs/0003-toolchain-integration.md#the-checks-run-by-run), with the new `T` checks, `E.5` to `E.7`, `M.5`, and `Z.13` |
| 2026-10-15 | 117 of 119 passed | From `main` at `131ba01`. `U.1` and `U.5` failed: security updates published after the last unattended run were pending on both VMs |
| 2026-10-16 | 119 of 119 passed | From `main` at `1e9a14f`, at 14:12 UTC. `U.1` and `U.5` passed after the unattended runs |
| 2026-10-16 | 119 of 120 passed | First run with `U.6`. It failed: the mesh agent's own updater was on (`AutoUpdate.Apply` `true`) |
| 2026-10-16 | 120 of 120 passed | After `tailscale set --auto-update=false` on the orchestrator, at 17:15 UTC |
| 2026-10-16 | 127 of 136 passed | After the audit copier and the new tool service image were installed, with the `L` and `J` checks. The nine `J` checks failed: the journal pull was not installed yet |
| 2026-10-16 | 135 of 136 passed | After the journal pull was installed. `J.5` failed on a correct pin: the check compared the scanner's banner too |
| 2026-10-16 | 136 of 136 passed | After the fix to `J.5`, at commit `0c1eba2`. See the [rollout](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies) |
| 2026-10-16 | 137 of 138 passed | First run with `L.8` and `J.10`, from a checkout with the [copier fix](../worklogs/0003-toolchain-integration.md#fix-whole-lines-only). `L.8` failed: the copier before the fix is installed |
| 2026-10-16 | 138 of 138 passed | After the [fixed copier](../worklogs/0003-toolchain-integration.md#rollout) was installed, from commit `9541326` |
| 2026-10-16 | 123 of 125 passed | Without the Azure and workstation checks, before the [orchestrator hardening](../worklogs/0004-edge-network-and-monitoring.md#rollout). `E.8` and `K.9` failed: the input chain was not loaded, and four namespaces admitted a privileged pod |
| 2026-10-16 | 143 of 143 passed | After the orchestrator hardening, at 20:18 UTC, from commit `7212a42` |
| 2026-10-16 | 143 of 143 passed | After the tool service image with the [rate limit](../worklogs/0004-edge-network-and-monitoring.md#on-the-live-system) was deployed, at 20:39 UTC |
| 2026-10-16 | 129 of 144 passed | Without the Azure checks, before the [SSH certificate rollout](../worklogs/0004-edge-network-and-monitoring.md#the-fail-side-of-each-new-check-1), with 14 new checks and 3 changed ones. The 15 that failed are the ones written down before the run |
| 2026-10-16 | 144 of 144 passed | Without the Azure checks, after the [rollout](../worklogs/0004-edge-network-and-monitoring.md#rollout-1), from commit `53c921c` |
| 2026-10-16 | 157 of 157 passed | Every check, the Azure ones included, at 21:44 UTC, from commit `2e2f6ff` |
| 2026-10-17 | 159 of 159 passed | From the branch at `081eab2`, at 08:50 UTC, after the target network was rebuilt in Poland Central. First run with `Z.14` and `Z.15` ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-targets-in-poland-central)) |
| 2026-10-17 | 193 of 194 passed | From the branch at `797d217`, at 14:24 UTC, after the [router](../worklogs/0004-edge-network-and-monitoring.md#the-router) took over the mesh. First run with the router's checks. `U.9` failed: 16 security updates pending on the new router |
| 2026-10-17 | 194 of 194 passed | At 14:34 UTC, after `unattended-upgrade` on the router |
| 2026-10-17 | 241 of 252 passed | From the branch with the 13 new `O` checks, at 22:50 UTC, before the [monitoring](../worklogs/0004-edge-network-and-monitoring.md#monitoring) apply. The 11 that failed are the ones written down before the run, each on absence. `O.4` and `O.13` passed |
| 2026-10-17 | 252 of 252 passed | At 23:39 UTC, after the [monitoring](../worklogs/0004-edge-network-and-monitoring.md#the-applies-3) apply |
| 2026-10-18 | 256 of 256 passed | At 09:07 UTC, after the [alert drills](../worklogs/0004-edge-network-and-monitoring.md#the-drills), with `O.14` to `O.17`. `O.17` then counted rows from any flow log. Since changed to name each flow log, it fails on the platform's |
| 2026-10-18 | 257 of 257 passed | From the branch at 14:00 UTC, after `O.17` changed to the edge flow log alone ([the platform flow log](../worklogs/0004-edge-network-and-monitoring.md#the-platform-flow-log)). A run from `main` just before it: 256 of 257, `O.17` the failure |
| 2026-10-18 | 257 of 257 passed | At 18:45 UTC, with the check script of `main` at `7f4a198`, in a review of the platform before the AI part |
| 2026-10-18 | 263 of 264 passed | From the branch at 19:03 UTC. First run with `G.1` to `G.4` and `P.20` to `P.22`. `G.2` failed, as written down before the run: the fixture on the worker predates a reformat of two of its files in the repository ([worklog](../worklogs/0004-edge-network-and-monitoring.md#before-the-ai-part)) |
| 2026-10-19 | 263 of 264 passed | From the branch, 16:20 to 16:25 UTC, after the [daily cap drill](../worklogs/0004-edge-network-and-monitoring.md#the-measured-day-and-the-daily-cap). `G.2` failed, as written down before the run |
| 2026-10-19 | 261 of 268 passed | From the branch at 18:30 UTC, [before dispatch](../worklogs/0003-toolchain-integration.md#before-dispatch). First run with `.21`. `G.1` and `G.2` passed on the reinstalled worker. `.1` failed on all four VMs, two timers the masking had failed, and `U.1`, `U.9`, and `U.13` on three pending security updates ([checks](../worklogs/0003-toolchain-integration.md#checks)) |
| 2026-10-19 | 268 of 268 passed | At 19:00 UTC, after the timers were reset and the updates installed |

The three runs on 2026-10-11 used the first version of the script. It had two weaknesses:

- `Z.4` and `Z.5` compared only the direction, priority, access, and name of each rule, and passed when both Azure calls failed.
- Every connection that did not open counted as closed, whether it timed out or was refused.

So those three passes for `Z.4`, `Z.5`, `C.1` to `C.8`, `E.3`, `M.3`, and `M.4` prove less than they appear to. The script now compares the whole rule and expects a timeout where a rule is the claim.

The run on 2026-10-12 is the first with that version. What it adds:

- `E.3`, `M.3`, and `M.4` timed out. The expected value had been reasoned from how the rules drop, and the run confirms it: no packet reached the worker on port 80, or the orchestrator on 3128 or 10250 through the mesh.
- `C.1`, `C.4`, and `C.6` to `C.8` timed out against ports that listen, so each is a drop on the path.
- `Z.4` and `Z.5` got an answer from Azure for both interfaces, and every field of every rule matched.

What it does not add: `C.2` and `C.3` also timed out, and still say nothing about the deny rule, because no target machine exists.

The second run on 2026-10-12 adds the seven `S` checks, which brings the script to 101. All seven passed on their first run against the system. [Model server](model-server.md) says what each proves and how each was shown to fail first.

## What the checks do not cover

- **A rebuild of everything at once.** Each VM has been rebuilt from its template and passed every check, the worker on 2026-10-11 and the orchestrator on 2026-10-13. Both together, or from an empty subscription, has not been run.
- **The target side.** No target exists yet.
- **The agent runtime during a run.** The [`G` checks](agent-runtime.md) read what is installed and what a finished job leaves. The transient unit's sandbox and the tools a run loads are not checked.
- **The tool service's round trip and audit lines.** They are steps in the [runbook](../runbooks/tool-service.md#round-trip), because they register and revoke jobs. Its rejection cases are tested in CI. The deployment itself is checked by the [tool service checks](tool-service.md).
- **Anything a benchmark tool finds.** kube-bench and Lynis results are in the [milestone 2 worklog](../worklogs/0002-platform-compute.md). The checks here hold the fixes in place.
- **Clean Terraform plans.** `terraform plan -detailed-exitcode` needs each root's own identity. The [runbook](../runbooks/platform-compute.md) has that step.
