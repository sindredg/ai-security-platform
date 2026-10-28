# 0007. Operational and containment drills

Date: 2026-10-28 to
Milestone: 6, operational and containment drills

## Summary

In progress. The drills run in slices, each a pull request of code and expectations and then one live run whose results land here, with its records in the [test evidence](../evidence/README.md). The milestone's own gate is below, and after it the gate for every high threat, which the [roadmap](../roadmap.md#6-operational-and-containment-drills) requires.

| Gate | Result |
| --- | --- |
| Worker and orchestrator interruption without duplicate changes | **Planned**: slice 1 terminates a workflow ([#174](https://github.com/sindredg/ai-security-platform/issues/174)); a later slice interrupts delivery ([#216](https://github.com/sindredg/ai-security-platform/issues/216)) |
| Duplicate findings without duplicate pull requests | **Planned**: a later slice |
| Forbidden tool calls, storage reads, network connections, and policy edits from a worker | **Planned**: a later slice |
| Instructions embedded in advisories and tool results | **Planned**: a later slice |
| Forged and stale target evidence | **Planned**: slice 1 ([stale and forged items](#stale-and-forged-checks-verdicts)) |
| Cleanup verification and measured resource use per investigation | **Planned**: slice 1 measures ([#176](https://github.com/sindredg/ai-security-platform/issues/176)); a later slice verifies cleanup |
| The incident response runbook, run for three cases | **Planned**: after the drills without an apply |
| An audit daemon and file integrity monitoring on both VMs, with a drill each | **Planned**: after the drills without an apply |
| A rebuild of each VM from the current templates | **Planned**: last. An accepted gap if the subscription window ends first |
| Operator sessions to the targets in the audit log (T04) | **Planned**: slice 1 ([sessions](#operator-sessions-to-the-targets)) |
| The KV-cache clear after a job that timed out ([#199](https://github.com/sindredg/ai-security-platform/issues/199)) | **Planned**: slice 1 ([timeout](#a-job-that-times-out)) |

## The gate for the high threats

Each threat the [threat model](../security/threat-model.md) rates high has a drill in this milestone, or an [accepted risk](../security/accepted-risks.md#accepted-risks). The state column is the threat model's, read on 2026-10-28, and moves with the drills.

| Threat | State | Drill or accepted risk | Evidence |
| --- | --- | --- | --- |
| T01 rogue mesh device | Verified | None needed | `M.1` to `M.7`, router joined under node signing ([worklog 0004](0004-edge-network-and-monitoring.md#first-boot-and-the-change-over)) |
| T02 mesh auth key leaks | Built | Accepted risk: the key is spent and expired | [Accepted risks](../security/accepted-risks.md#accepted-risks) |
| T37 certificate authority key stolen | Verified | None needed | Refused certificates ([worklog 0004](0004-edge-network-and-monitoring.md#rollout-1)) |
| T38 router reaches an operator device | Verified | None needed | `Z.17`, `R.5`, `U.6`, the policy's own tests |
| T05 orchestrator sends on 443 or 80 | Verified | None needed | `E.12`, `Z.22`, `P.14`, `P.15` |
| T06 malicious artifact | Verified | None needed | [Supply chain](../security/supply-chain.md) |
| T07 DNS leak | Verified | None needed | `C.4`, `C.5`, `C.10`, `E.13`, `E.14`, `VN.14`, `VL.14` |
| T08 storage account without a gateway | Verified | None needed | `C.1`, `Z.7`, `VN.13`, `VL.13`, `Z.27`, `Z.28` |
| T39 Squid exploited to root on the edge | Built | Accepted risk: no credential on the edge, nothing to drill short of an exploit | [Accepted risks](../security/accepted-risks.md#accepted-risks) |
| T40 upload during a JIT egress window | Verified | None needed | `P.15` to `P.22` ([worklog 0004](0004-edge-network-and-monitoring.md#the-edge-vm)) |
| T10 push past the ruleset | Verified | None needed | [Worklog 0004](0004-edge-network-and-monitoring.md#the-fail-side-on-github) |
| T11 approval reused | Verified | None needed | [Worklog 0006](0006-remediation-pull-requests-and-delivery.md#fixes-after-the-close) |
| T12 repository credential stolen | Verified | None needed | [Credential inventory](../security/credentials.md) |
| T13 secret in the public repository | Verified | Push-protection drill, slice 1 | [Push protection](#push-protection) |
| T15 GitHub account taken over | Accepted | Accepted risk | [Accepted risks](../security/accepted-risks.md#accepted-risks) |
| T56 approval key stolen | Accepted | Accepted risk | [Accepted risks](../security/accepted-risks.md#accepted-risks) |
| T59 stolen GitHub session | Verified | None needed | [Worklog 0006](0006-remediation-pull-requests-and-delivery.md#one-fix-end-to-end) |
| T16 tool call outside the job | Verified | Forbidden calls drill, later slice | [Worklog 0003](0003-toolchain-integration.md#the-round-trip) |
| T17 worker reaches a target or the internet | Verified | Forbidden connections drill, later slice | `P.5` to `P.11`, `C.1` to `C.10` |
| T18 worker as another job | Verified | Another job's token, later slice | [Record](../evidence/2026-10-21-1511-first-workflows.md) |
| T21 worker edits its audit record | Verified | None needed | `L.1` to `L.7` |
| T22 tool service exploited | Verified | None needed | `T.3` to `T.5`, `T.8`, `T.9`, `M.5`, `Z.13`, `E.8` |
| T23 target reports false evidence | Built | Stale and forged items, slice 1. The cloud API and network comparison: accepted risk | [Stale and forged items](#stale-and-forged-checks-verdicts) |
| T24 target attacks the collector | Verified | Injected instructions drill, later slice | [Record](../evidence/2026-10-25-1208-first-netbox-jobs.md) |
| T25 target side removes containment | Verified | None needed | `Z.10`, `Z.11` |
| T26 delivery changes more than approved | Verified | None needed | [Worklog 0006](0006-remediation-pull-requests-and-delivery.md#one-fix-end-to-end) |
| T57 delivery token kept or stolen | Verified | None needed | `D.4` ([worklog 0006](0006-remediation-pull-requests-and-delivery.md#a-token-for-each-delivery)) |
| T29 deployment key used by another | Verified | None needed | [Worklog 0001](0001-network-foundation.md#identity-separation) |
| T30 Owner account taken over | Accepted | Accepted risk | [Accepted risks](../security/accepted-risks.md#accepted-risks) |
| T33 one side changes the other | Verified | None needed | [Worklog 0001](0001-network-foundation.md#identity-separation) |
| T36 workload reaches another's credentials | Verified | None needed | `T.3`, `K.9` |
| T44 feed key runs commands as root | Verified | None needed | `E.4`, `E.9` to `E.11` |
| T50 compromised Argo controller image | Verified | None needed | `W.2`, `W.3`, `W.7` ([worklog 0005](0005-netbox-target-and-exercise-1.md#argo)) |
| A1 prompt injection | Verified | Injected instructions drill, later slice | [Records](../evidence/README.md) |
| A2 excessive agency | Built | Forbidden calls drill, later slice | [AI threats](../security/ai-threats.md) |
| A3 wrong and convincing | Verified | None needed | [Records](../evidence/2026-10-27-0653-scored-proposals.md) |

## Slice 1: drills without an apply

The code is in pull request #TBD. The expected results below were written before the live run, and the run fills in the results. The procedure is the [containment drills runbook](../runbooks/containment-drills.md).

### A job that times out

The model server's prompt batch is 512 tokens ([ADR 0052](../decisions/0052-a-smaller-prompt-batch-so-a-cancel-reaches-the-model-server-in-time.md)), and `S.8` reads it. The fail side ran on the workstation on 2026-10-28: the probe's expression on a command line without `--batch-size` gives an empty value, and `2048` on one at the default, so `S.8` fails on both.

Expected: a NetBox job with a 120-second limit times out inside its first prompt, its journal line has `"outcome": "timeout"` and `"slot_erased": true`, and the model server's journal shows the cancel taken within one 512-token batch. The first prompt's rate at 512 is read against 12.3 tokens per second at 2048 on 2026-10-28.

Result: not yet run.

### A terminated workflow

The dispatch step revokes the job's token in its stop handler, since `argo terminate` skips the exit handler ([#174](https://github.com/sindredg/ai-security-platform/issues/174)). The pipeline's stop test asserts the `DELETE` at the tool service and the exit code 143.

Expected: after `argo terminate` the dispatch step's log ends with `"stopped": 15, "revoked": 200`, the audit file has the job's `revoke` by the dispatch caller, the worker's line has `"outcome": "cancelled"` and `"slot_erased": true`, and the workflow is `Failed`.

Result: not yet run.

### Operator sessions to the targets

The router logs each new SSH connection from the mesh to the target range, and `R.8` reads the rule ([mesh router runbook](../runbooks/mesh-router.md), step 20). The log agent's `system` source sends kernel lines at Warning and above, which is the level `nft log` writes.

Expected: `R.8` fails on the router before the rule loads and passes after, and one session from the workstation to the NetBox VM gives one `Syslog` row from `aisec-router` whose message has `aisec-target-ssh`, `SRC=` the workstation's mesh address, `DST=10.50.0.4`, and `DPT=22`.

Result: not yet run.

### Stale and forged checks' verdicts

The dispatch step refuses a checks' verdicts item older than an hour, or more than five minutes ahead of its clock, before the job runs (T23). The pipeline tests cover 3601 seconds old, 301 ahead, 3599 old, and 299 ahead.

Expected, stale: an item written by hand with a `collected` two hours old fails the dispatch step with `the checks' verdicts are N s old`, no `register` in the audit file, and the workflow `Failed`. Expected, forged: an item written by hand with a fresh time and `within` for an account the live seed gives `excess` runs the job, the model answers `excess`, and the verification gate stops on the disagreement. The forged item was trusted: `W.12` says who can write it, and that is the boundary.

Result: not yet run.

### Resource use per investigation

Two readings of `orchestrator-footprint` around the forged item's job, diffed for the average CPU per component, with the `Perf` rows for the job's minutes ([#176](https://github.com/sindredg/ai-security-platform/issues/176)). The day's volume for 2026-10-27, the busiest so far, decides the cap ([#175](https://github.com/sindredg/ai-security-platform/issues/175)).

Result: not yet run.

### Push protection

Expected: a signed commit holding a GitHub token with a valid checksum, on a scratch branch, is refused at the push with GitHub's push-protection message naming the token type, and nothing lands on the remote. A push that goes through means the pattern alone does not catch a made-up token, and the accepted risk stays, with that evidence.

Result, 2026-10-28 17:24 UTC, from the workstation: the push was refused with `GH013: Repository rule violations`, a `Push cannot contain secrets` block naming `GitHub Personal Access Token` at `drill.txt:1` of the commit, and `push declined due to repository rule violations`. `git ls-remote` found no branch after it. The token was 40 characters of `ghp_`, 30 random characters, and their CRC32 in base62, made for the drill and never a credential.

### The pin and every check

The mesh VPN agent pin moved to 1.104.4 ([#225](https://github.com/sindredg/ai-security-platform/issues/225)), loaded on the running router by the runbook's step 21. Expected after the slice: every check passes, 428 of 428, with `S.8` and `R.8` new and `U.7` passing again.

Result: not yet run.
