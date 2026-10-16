# Validation

What the platform claims, and the check that proves each claim against the running system.

The [worklogs](../worklogs/README.md) are history: what was run on which day. These pages are the present: every claim has an ID, a reason, and a check that can be run again in about two minutes.

## Run the checks

From a workstation on the mesh VPN, signed in to Azure as the operator. The `Z` checks need `python3`:

```bash
export AISEC_SSH="ssh -o UserKnownHostsFile=REPLACE_WITH_KNOWN_HOSTS_FILE -o StrictHostKeyChecking=yes -i REPLACE_WITH_OPERATOR_KEY -o IdentitiesOnly=yes"
validation/platform-checks.sh
```

Expected: one `PASS` line per check, a summary, and exit `0`. A `FAIL` prints what was expected and what was found, and the script exits `1`.

| Option | Effect |
| --- | --- |
| `--no-azure` | Skips the `Z` checks. The rest need no Azure sign-in |
| `--no-workstation` | Skips the `M` checks, which test the mesh policy from the machine that runs the script |

A connection check reports `open`, `refused`, `timeout`, or `unreachable`, and each check expects exactly one of them. [Containment](containment.md#what-a-failed-connection-proves) says why.

The script changes nothing. It opens connections that should fail, reads settings, and asks Azure to validate one template that it never deploys.

## Areas

| Page | Checks | What it covers |
| --- | --- | --- |
| [Access](access.md) | `A`, `M` | Who can get in, and through what |
| [Containment](containment.md) | `C`, `E`, `R`, `Z.4` to `Z.9`, `Z.13` | What the worker cannot reach, and what the orchestrator can |
| [Package proxy](package-proxy.md) | `P`, `U` | The worker's one path out, and whether updates arrive |
| [Model server](model-server.md) | `S` | The server runs, listens on loopback only, keeps its sandbox, and loads the file the build made |
| [Cluster](cluster.md) | `K` | K3s health and the hardening benchmark findings |
| [Tool service](tool-service.md) | `T` | The deployed tool service: its pod, namespaces, network paths, and certificate |
| [Host hardening](host-hardening.md) | `HO`, `HW` | SSH daemon, kernel settings, file modes, on both VMs |
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
- **The agent runtime.** Its install and its cleanup were checked by hand and are not in the script.
- **The tool service's round trip and audit lines.** They are steps in the [runbook](../runbooks/tool-service.md#round-trip), because they register and revoke jobs. Its rejection cases are tested in CI. The deployment itself is checked by the [tool service checks](tool-service.md).
- **Anything a benchmark tool finds.** kube-bench and Lynis results are in the [milestone 2 worklog](../worklogs/0002-platform-compute.md). The checks here hold the fixes in place.
- **Clean Terraform plans.** `terraform plan -detailed-exitcode` needs each root's own identity. The [runbook](../runbooks/platform-compute.md) has that step.
