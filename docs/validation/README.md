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
| [Containment](containment.md) | `C`, `E`, `Z.4` to `Z.9`, `Z.13` to `Z.28` | What the worker and the orchestrator cannot reach, and what they can |
| [Targets](targets.md) | `VN`, `VL`, `N`, `U.14`, `U.15` | The NetBox and lab VMs: the operator's login, the update account, the update runs, and no way out. NetBox: its image, its port, and its secrets |
| [Package proxy](package-proxy.md) | `P`, `U` | Squid on the edge, the one path out for the orchestrator and the worker, the fetch window, and whether updates arrive |
| [Model server](model-server.md) | `S` | The server runs, listens on loopback only, keeps its sandbox, and loads the file the build made |
| [Agent runtime](agent-runtime.md) | `G` | The Goose binary and the fixture are the pinned ones, and no finished job leaves its unit or its files |
| [Cluster](cluster.md) | `K` | K3s health and the hardening benchmark findings |
| [Workflows](workflows.md) | `W` | Argo's controller, kept to `orchestration` and to templates, the template itself, the dispatch secret, and that no workload account may change config maps in `orchestration` |
| [Tool service](tool-service.md) | `T` | The deployed tool service: its pod, namespaces, network paths, and certificate |
| [Audit log](audit-log.md) | `L`, `J` | The copier that stores the tool service's audit lines, the pull of the worker's journal, and the append-only files they write |
| [Monitoring](monitoring.md) | `O` | The log agents, their hosts entries, the workspace and its scope, heartbeats, and the identities |
| [Host hardening](host-hardening.md) | `HO`, `HW`, `HR`, `HE`, `HN`, `HL` | SSH daemon, kernel settings, file modes, on every VM |
| [Azure policy](azure-policy.md) | `Z.1` to `Z.3`, `Z.10` to `Z.12` | Public addresses and the policy that refuses them |
| [Investigation](investigation.md) | None: scored per job | Exercise 1's investigation on held-out cases, the rules that score it, and the run without the agent beside it |

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
| 2026-10-20 | 222 of 237 passed | Without the Azure and workstation checks, at 19:27 UTC, after the job socket, runner, and job unit were installed on the worker and the [first jobs ran over the socket](../worklogs/0003-toolchain-integration.md#installed-and-run-on-the-worker). `G.6` to `G.9` passed; `G.8` held the installed files equal to the checkout; `G.5` failed on the absent dispatch key. The rest were the Argo-side, pending-update, and mesh-agent-pin checks |
| 2026-10-20 | 223 of 238 passed | Without the Azure and workstation checks, at 20:16 UTC, after the [slot-erase fix](../worklogs/0003-toolchain-integration.md#installed-and-run-on-the-worker) ([PR 140](https://github.com/sindredg/ai-security-platform/pull/140)). First run with `G.10`, which passed, and `G.8` passed. The 15 failures were the Argo-side checks (`E.6`, `W.1` to `W.6`, `W.8` to `W.10`, `G.5`, `P.18`), two pending security updates (`U.5`, `U.13`), and the mesh VPN agent pin (`U.7`) |
| 2026-10-21 | 279 of 284 passed | From `main` at `fa99384`, at 04:24 UTC, after Argo, the dispatch key, and the host rule were installed ([worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows)). `W.1` to `W.10`, `G.5`, `E.6`, and `P.18` passed. `O.17` failed as written: traffic analytics had begun processing the platform's flow log. `U.5`, `U.9`, and `U.13` failed on pending security updates, `U.7` on a new mesh agent release |
| 2026-10-21 | 281 of 285 passed | From the branch at `5f3c27d`, at 15:26 UTC, after the first workflows. First run with `W.11` and the new `O.17`, both passed. `U.5` and `U.7` failed as before, and `HR.1` and `HE.1` on a failed firmware metadata refresh ([#145](https://github.com/sindredg/ai-security-platform/issues/145)) |
| 2026-10-21 | 282 of 285 passed | From the branch at `5d0b550`, at 15:44 UTC, after the UI's config map. `U.5`, `U.7`, and `HR.1` failed as before |
| 2026-10-21 | 283 of 285 passed | From the branch at `fd12a42`, ending at 16:37 UTC, after the worker's security updates and the mesh agent's move to 1.104.2 ([worklog](../worklogs/0003-toolchain-integration.md#pins-and-updates-before-the-model-comparison)). `U.5` and `U.7` passed. `HR.1` and `HE.1` failed on the firmware metadata refresh ([#145](https://github.com/sindredg/ai-security-platform/issues/145)) |
| 2026-10-21 | 283 of 285 passed | From `main` at `b58a7f6`, ending at 18:31 UTC, after the [first model comparison run](../worklogs/0003-toolchain-integration.md#first-run). The output kept only its last lines, so the failed IDs were read from a run that finished at 19:00 UTC: `HR.1` and `HE.1`, the firmware metadata refresh. `S.7` passed against Qwen3.5-4B |
| 2026-10-21 | 285 of 285 passed | From the branch at `0fa8f65`, ending at 20:14 UTC, after the [second model comparison run](../worklogs/0003-toolchain-integration.md#second-run). Written before: `HR.1` and `HE.1` failing. Both passed. `S.7` passed against Qwen3.5-4B |
| 2026-10-22 | 233 of 239 passed | Without the Azure and workstation checks, at 16:18 UTC, from `96f91ba` with the two manifests on the new image digests, before the [deploy](../worklogs/0003-toolchain-integration.md#checks-before-and-after). `T.2` and `W.9` failed, the cluster still on the old images. `U.1`, `U.5`, `U.9`, and `U.13` on two security updates published after the morning's unattended runs |
| 2026-10-22 | 281 of 285 passed | The same checkout, at 16:26 UTC, after the deploy. `T.2` and `W.9` passed. The four `U` checks failed as before |
| 2026-10-23 | 281 of 285 passed | From the branch of [#159](https://github.com/sindredg/ai-security-platform/pull/159) at 05:06 UTC, with the fetch window command it tested on the edge. `U.1`, `U.5`, `U.9`, and `U.13`: security updates pending on each VM before the morning's unattended runs |
| 2026-10-23 | 283 of 285 passed | From the same branch at 14:02 UTC, the tree of `main` at `ce914a7`, after that command was installed on the edge. `P.17` passed. `U.1` and `U.13` failed on `zlib1g`, published after the morning's unattended runs on the orchestrator and the edge |
| 2026-10-23 | 283 of 285 passed | From the branch of [#163](https://github.com/sindredg/ai-security-platform/pull/163) at `83fe17f`, ending at 15:14 UTC, after the [erase before each job and the answer lines](../worklogs/0003-toolchain-integration.md#installed-the-erase-before-each-job-and-the-answer-lines) were installed. `G.2`, `G.8`, `G.10`, and `W.9` passed. `U.1` and `U.13` failed on `zlib1g` |
| 2026-10-23 | 284 of 286 passed | From the branch of [#165](https://github.com/sindredg/ai-security-platform/pull/165) at `ea6c501`, ending at 16:39 UTC, after [K3s's system images](../worklogs/0003-toolchain-integration.md#installed-k3ss-system-images-from-the-releases-archive) came from the release's archive and the edge's list lost Docker Hub. First run with `K.11`, which passed, and `P.18` passed on the new list. `U.1` and `U.13` failed on `zlib1g`, as before |
| 2026-10-24 | 286 of 286 passed | From `main` at `2117b2d`, ending at 06:53 UTC, after the morning's unattended upgrades installed `zlib1g`. `U.1` and `U.13` passed. Again from the branch of [#172](https://github.com/sindredg/ai-security-platform/pull/172) at `5be567e`, 07:12 to 07:18 UTC, for the [milestone 3 close](../worklogs/0003-toolchain-integration.md#read-for-the-close-the-orchestrators-footprint-and-the-daily-volume) |
| 2026-10-24 | 286 of 286 passed | From the branch `chore/move-pins` at `4b18089`, with the Goose 1.56.0 and Argo v4.1.6 pins not yet committed, 13:08 to 13:13 UTC, after both were installed ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-install)) |
| 2026-10-24 | 295 of 295 passed | From the branch of [#183](https://github.com/sindredg/ai-security-platform/pull/183) with the changes uncommitted, 14:38 to 14:43 UTC, after the [targets' package port](../worklogs/0005-netbox-target-and-exercise-1.md#every-check) was installed. First run with `P.23` to `P.29`, `M.9`, and `Z.26` |
| 2026-10-24 | 380 of 380 passed | From the branch with the target checks uncommitted, ending at 16:51 UTC, after the [target VMs](../worklogs/0005-netbox-target-and-exercise-1.md#the-checks-for-the-targets) were built. First run with `VN`, `VL`, `HN`, `HL`, `C.11`, `E.15`, `E.16`, `Z.27`, and `Z.28`, and with `Z.1` reading both groups |
| 2026-10-24 | 330 of 336 passed | Without the Azure and workstation checks, from the branch with the update run uncommitted, at 17:30 UTC. First run with `E.17`, `E.18`, `VN.20`, `VL.20`, `U.14`, and `U.15`. The six failed as written before the run: nothing installed, and the targets' apt sources on hosts the target port refuses ([troubleshooting 16](../troubleshooting/16-targets-apt-sources-fall-back-without-dns.md)) |
| 2026-10-24 | 386 of 386 passed | The same branch, ending at 18:12 UTC, after both targets were rebuilt and the [first update runs](../worklogs/0005-netbox-target-and-exercise-1.md#the-update-run) |
| 2026-10-24 | 396 of 398 passed | From the branch with NetBox's install uncommitted, ending at 20:09:57 UTC, after [NetBox](../worklogs/0005-netbox-target-and-exercise-1.md#netbox-on-its-vm) was installed. First run with `N.1` to `N.11` and `C.12`. `Z.25` failed on the two new rules its expected value did not name, and `N.7` on a path in a value |
| 2026-10-24 | 398 of 398 passed | The same branch with both checks fixed, ending at 20:19:58 UTC |
| 2026-10-25 | 404 of 404 passed | From `main` at `c41f2cb` with the seed's checks uncommitted, 06:55 to 07:03 UTC, after [the seed](../worklogs/0005-netbox-target-and-exercise-1.md#the-seed-and-the-two-checks). First run with `N.12` to `N.17` |
| 2026-10-25 | 411 of 411 passed | From the branch `feat/netbox-evidence-collection` at `6f74fe5`, 12:24 to 12:33 UTC, after the collect command, the observer account, and the images from #194 were installed and the [first jobs on NetBox's evidence](../worklogs/0005-netbox-target-and-exercise-1.md#every-check-after-the-collection) ran. First run with `N.18` to `N.23` and `T.14` |
| 2026-10-25 | 411 of 411 passed | From the same branch at `47477ed`, 14:30 to 14:39 UTC, after the [fixes from its review](../worklogs/0005-netbox-target-and-exercise-1.md#fixes-from-the-review) were installed on both hosts |
| 2026-10-25 | 412 of 412 passed | From the branch `feat/verdict-comparison` at `73f0f9d`, 18:24 to 18:32 UTC, after the comparison step, its image, and the system text were installed and the [first jobs with the comparison](../worklogs/0005-netbox-target-and-exercise-1.md#the-rollout-and-the-first-jobs) ran. First run with `W.12` |
| 2026-10-25 | 361 of 362 passed | Without the Azure and workstation checks, from the same branch at `5cc0ed9`, 20:07 to 20:11 UTC, while `argo-operator` was given `patch` on config maps in `orchestration`. `W.12` failed, as written before the run ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#w12-fails-on-a-broken-input)) |
| 2026-10-25 | 362 of 362 passed | The same, 20:11 to 20:15 UTC, after the grant was removed |
| 2026-10-25 | 361 of 362 passed | Without the Azure and workstation checks, from the branch at `dde15f2`, at 21:58 UTC, with one line added to the installed case file. `N.18` failed, as written before the run ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-rollout)) |
| 2026-10-25 | 412 of 412 passed | The same branch, 22:01 to 22:10 UTC, after the case file was put back, with #202's image and the job program's checks installed. `N.18` reads the case file |

The three runs on 2026-10-11 used the first version of the script. It had two weaknesses:

- `Z.4` and `Z.5` compared only the direction, priority, access, and name of each rule, and passed when both Azure calls failed.
- Every connection that did not open counted as closed, whether it timed out or was refused.

So those three passes for `Z.4`, `Z.5`, `C.1` to `C.8`, `E.3`, `M.3`, and `M.4` prove less than they appear to. The script now compares the whole rule and expects a timeout where a rule is the claim.

The run on 2026-10-12 is the first with that version. What it adds:

- `E.3`, `M.3`, and `M.4` timed out. The expected value had been reasoned from how the rules drop, and the run confirms it: no packet reached the worker on port 80, or the orchestrator on 3128 or 10250 through the mesh.
- `C.1`, `C.4`, and `C.6` to `C.8` timed out against ports that listen, so each is a drop on the path.
- `Z.4` and `Z.5` got an answer from Azure for both interfaces, and every field of every rule matched.

What it does not add: `C.2` and `C.3` also timed out, and still say nothing about the deny rule, because no target machine existed then.

The second run on 2026-10-12 adds the seven `S` checks, which brings the script to 101. All seven passed on their first run against the system. [Model server](model-server.md) says what each proves and how each was shown to fail first.

## What the checks do not cover

- **A rebuild of everything at once.** Each VM has been rebuilt from its template and passed every check, the worker on 2026-10-11 and the orchestrator on 2026-10-13. Both together, or from an empty subscription, has not been run.
- **The target side's later parts.** The unintended viewpoint and the rehearsal copy are not built yet. NetBox, its seed, and the collect command are checked by the [`N` checks](targets.md#netbox).
- **The agent runtime during a run.** The [`G` checks](agent-runtime.md) read what is installed and what a finished job leaves. The transient unit's sandbox and the tools a run loads are not checked.
- **The tool service's round trip and audit lines.** They are steps in the [runbook](../runbooks/tool-service.md#round-trip), because they register and revoke jobs. Its rejection cases are tested in CI. The deployment itself is checked by the [tool service checks](tool-service.md).
- **Anything a benchmark tool finds.** kube-bench and Lynis results are in the [milestone 2 worklog](../worklogs/0002-platform-compute.md). The checks here hold the fixes in place.
- **Clean Terraform plans.** `terraform plan -detailed-exitcode` needs each root's own identity. The [runbook](../runbooks/platform-compute.md) has that step.
