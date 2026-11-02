# 0009. Exercise 2: excess network access

Date: 2026-11-01
Milestone: 7, exercise 2: excess network access

## Summary

A pair of port rules lets the staging subnet reach the live NetBox's port, and both deterministic checks find it: the rules at the targets repository's `main` and a connection from the staging address each call the staging viewpoint `excess`, while the consumer and both accounts stay `within`. Three NetBox jobs ran on the seed, and none gave a final output within its 1200 seconds ([#253](https://github.com/sindredg/ai-security-platform/issues/253)). So no fix was proposed, approved, or delivered, and the probes after a fix did not run.

The chain for a rule's fix is built and covered by unit tests: the policy, the rules judged without the rule, the pull request body, and `edit_rules.py`. It never ran on the live system.

The system was torn down on 2026-11-02. Every apply destroyed the count its plan gave, and nothing named for the project is left in the subscription ([the teardown](#the-teardown)).

| Criterion | Result |
| --- | --- |
| Probes from both viewpoints, before and after | **Tested** with the seed live: both addresses reach `10.50.0.4:8443`, and three collections agree ([the seed](#the-seed)). **Accepted gap**: before the seed, only the configured rules were read; no fix to probe after ([#253](https://github.com/sindredg/ai-security-platform/issues/253)) |
| The change touches only allowlisted target network fields | **Configured, not tested** live: the policy allows only removing the inbound rule that lets an excess viewpoint in, and its outbound half. Unit tests ([the fix's chain](#the-fixs-chain)) |
| The access specification and the exercise 1 denials still hold | **Tested** with the seed live: both accounts `within/within`, and `N.14` and `N.17` passed ([the checks after](#the-checks-after)). **Accepted gap**: after a fix, not run ([#253](https://github.com/sindredg/ai-security-platform/issues/253)) |
| Outer containment is unchanged | **Tested** with the seed live: only `N.25` and `Z.25` failed, which read the seed's path ([the checks after](#the-checks-after)). **Accepted gap**: after a fix's apply, not run ([#253](https://github.com/sindredg/ai-security-platform/issues/253)) |
| The threat model is rechecked for the new change surface | **Tested** by reading: ten rows moved, T15, T23, T24, T26 to T28, T53, T58, T59, and A5 ([the threat model](#the-threat-model)) |

## The start pass

No open issue fits the milestone. [#220](https://github.com/sindredg/ai-security-platform/issues/220) is the nearest: the seed's fix left exercise 1 without a fix to propose, and exercise 2's seed gives the live seed one again, though not a held-out case.

The design is [ADR 0056](../decisions/0056-exercise-2-judges-viewpoints-by-netboxs-port-rules-kept-as-data.md). The unintended viewpoint is the lab VM's staging address, `10.50.1.4`, because the lab VM routes from it already and the `unintended` subnet has no machine. Every target subnet ends in `deny-all-outbound` at 4096, so the seed is a pair of rules, not one.

## The seed

Two pull requests in the targets repository, each with its checks:

| Pull request | Change | Merge |
| --- | --- | --- |
| [targets #21](https://github.com/sindredg/ai-security-platform-test/pull/21) | NetBox's port rules move from `main.tf` into `infra/targets/netbox-rules.json`, which the approval check guards, with the seed's pair | `b4e2027`, after a signed approval of its head |
| [targets #22](https://github.com/sindredg/ai-security-platform-test/pull/22) | The contract's network part: NetBox's address, port, and subnet, and the viewpoints `consumer` (open) and `staging` (closed) | `978de95` |

The pair is `allow-netbox-from-rehearsal` at priority 1120, inbound on the `netbox` subnet and outbound on the `rehearsal` subnet, from `10.50.1.0/27` to `10.50.0.4/32` on 8443.

Stated before the plan: `0 to add, 2 to change, 0 to destroy`, the two security groups each gaining the rule; then the staging address reaches the port, the consumer's path stays open, and `Z.25` fails on the new rule.

Result, 2026-11-01 20:38 UTC, on the live system: the plan and the apply were `0 added, 2 changed, 0 destroyed`. A TCP connection from the lab VM, bound to each address, to `10.50.0.4:8443`:

| Source | Result |
| --- | --- |
| `10.50.0.36`, the consumer | `open` |
| `10.50.1.4`, the staging address | `open` |
| `10.50.1.4` to ports 22 and 9999 | timeout |

The closed state before the seed was not probed: the probe was written with the seed and first ran after its apply, and the checks before it read the configured rules (`Z.25`), not a connection. `N.25` holds it as a check from now on.

The seed opened no new host's way to NetBox: the lab VM reached the port already, from the consumer's address. It opened the staging copy's address, which the copy and every other process on the lab VM can bind to (T58).

## The guard on the rules file

The seed's pull request failed "Approved commit" on the check's own files, not on the rules file. `pull_request_target` runs the base's check, which did not guard the file yet, so the rules file's fail side was not seen there.

Stated before the run: a pull request that changes only a description in `infra/targets/netbox-rules.json` fails "Approved commit" with `The pull request changes infra/targets/netbox-rules.json, so its head needs an approval`, and the signature check passes.

Result, 2026-11-01 22:54 UTC, [targets #24](https://github.com/sindredg/ai-security-platform-test/pull/24): as stated, and the pipeline's checks passed. Closed without merging.

## The install

Stated before the run: every check from the branch, before the install, fails `N.18` and `N.22` (the installed collector is `main`'s), `N.25` (the seed is live), `N.26` (the delivery mirror's `main` has no rules file), and `Z.25` (the seed's rule).

Result, 2026-11-01 21:08 to 21:17 UTC, on the live system, from `178bab1`: 442 passed, 6 failed. The five stated, and `D.2`: the installed change commands differed from the branch's too, which the statement missed.

Then, 21:17 to 21:19 UTC:

- The collector and the change commands on the orchestrator, with the contract: the same five SHA-256 on the host as in the two checkouts.
- The observer's copy on the lab VM: the four `sshd -T` lines, and the same SHA-256 as the checkout.
- The tool service's policy with `deploy.sh`: the token's claims, two audit copier passes, the rollout, and the live policy's SHA-256 equal to the branch's.
- The mirror fetched `main` in a JIT egress window: `978de95`.

The collection for the first job, `nb-11012108-e2`, gave `ev-0001` to `ev-0005` in 52 seconds, and the verdicts stated before it:

```text
inventory-reader:within/within inventory-reader-control:within/within viewpoint-consumer:within/within viewpoint-staging:excess/excess
```

## The jobs

Stated before each job: `Succeeded`, the verification gate's outcome `match`, and `viewpoint-staging` `excess` with one proposal that names priority 1120. A `Failed` with `stop: ...` would be the gate refusing the answer.

Result, on the live system, 2026-11-01 21:19 to 22:33 UTC, each with 1200 seconds and 12 turns ([run set](../evidence/2026-11-01-2108-exercise-2.md)):

| Job | Task | Collection | Outcome |
| --- | --- | --- | --- |
| `nb-11012108-e2` | At `178bab1`, 3,251 bytes | 52 s, the verdicts as stated | Time limit. `ev-0001` to `ev-0003`, the first call 7 m 57 s in |
| `nb-11012108-e2b` | The same | 36 s, the same | Time limit. The same three documents, the first call 7 m 57 s in |
| `nb-11012211-e2c` | At `a902bfc`, 2,214 bytes | 63 s, the same | Time limit. The same three documents, the first call 7 m 20 s in |

No job asked for `ev-0004` or `ev-0005`, the rules and the connections that hold the finding. After the third call, about 10 minutes passed with no call and no output. A timed-out job keeps no transcript past the system prompt, so what the model did then is not recorded.

The shorter task cut a third of the text and asked for the final output with no text before it. Its first call came 37 seconds sooner, and nothing else changed. Exercise 1's closing job on the same model made its first call 5 m 14 s in ([closing run](../evidence/2026-11-01-1704-the-closing-run.md)).

The cause is not confirmed. The five documents total about 6.1 KB, read on the orchestrator, and the first call comes before any of them is read. A longer prompt than exercise 1's, the task and an answer schema with four subjects instead of two, is a hypothesis ([#253](https://github.com/sindredg/ai-security-platform/issues/253)).

The audit log holds, for each job, the registration, one allowed `get_evidence` per call, and the revoke. Sequence number 11, between the second and the third job, is the checks' own request without a token, refused. On the worker, each job's slot was erased before it and after it.

## The checks after

Stated before the run: every check passes but `N.25`, which the seed opens, and `Z.25`, which reads the seed's rule.

Result, 22:01 to 22:11 UTC, on the live system, from `c071900` with the targets at `978de95`: 446 passed, 2 failed, `N.25` and `Z.25`. The checkout had moved from `178bab1` to `c071900` by then. The files that `D.2` and `N.18` hash did not change between the two.

`Z.25` passed in every run before the seed. `N.25` is new and has only been seen failing, while the seed was live: its pass side was not seen.

## The fix's chain

A rule's fix goes through five programs. Each has unit tests, and none ran a rule's fix on the live system.

| Command | What it checks | Tests |
| --- | --- | --- |
| `policy.py` | A removal of the inbound rule that lets an excess viewpoint in, with its outbound half, and nothing else moving | `test_the_seeds_rule_and_its_outbound_half_are_allowed`, and eight refusals |
| `propose.py` | The rules judged without the pair, in the bundle and the pull request body | `test_an_allowed_fix_writes_the_bundle`, and two refusals |
| `edit_rules.py` | Only the bundle's removals, in the file the job judged by SHA-256 | `test_the_fix_removes_the_two_rules_and_nothing_else`, `test_refusals_leave_the_file_as_it_was`, `test_an_edit_that_removes_another_rule_is_refused` |
| `compare.py` | A viewpoint's verdict and a rule's priority, read as an account's and a permission's | `test_a_viewpoint_and_its_rule_go_through_as_an_account_does` |
| `open_fixes.py` | A rule fix's rows in the open pull requests, as `propose.py` writes them | `test_a_rule_fix_matches_the_rows_the_propose_command_writes` |

Result, locally, on 2026-11-01, after the review's fixes: the change commands' 113 tests, the verification gate's 81, the collector's 92, and the evidence tools' 48 pass. The two tests the review added failed first: the editor's against a `removed_from` that drops a third rule, and the gate's against an ID pattern cut to three digits. The tool service's tests passed in the pipeline.

## The threat model

Read again for a change surface that is a port rule. Ten rows moved, each with its evidence on the [threat model](../security/threat-model.md) and [AI threats](../security/ai-threats.md).

| Threat | What moved |
| --- | --- |
| T15 | A merged port rule, in either file, reaches Azure at the operator's next apply, which reads no approval |
| T23 | The network comparison is built for viewpoints, and the halves agreed in three collections. The cloud API comparison stays [accepted](../security/accepted-risks.md#accepted-risks) |
| T24 | A new target-side input: the rules file, parsed as root on the orchestrator within `netbox_rules.load`'s limits |
| T26, T27 | A port rule's fix and its policy check, unit-tested only |
| T28 | The outside checks passed with the seed live |
| T53 | The observed half also connects from each viewpoint's address |
| T58 | The seed opened the staging subnet to NetBox's port |
| T59 | A port rule's delivery reads no tag: the merge check is its only approval |
| A5 | A port rule's pull request body, unit-tested, never published |

## The teardown

The [teardown runbook](../runbooks/teardown.md) ran on the live system after the last job, from scripts with the same commands. Each apply used a plan saved and read before it. Stated before the run: each apply destroys the count its plan gave, and step 8 gives three empty answers.

| Step | Result |
| --- | --- |
| 1. No workflow running | 2026-11-01: 13 workflows listed, none running, each with its record |
| 2. A copy of each state | 2026-11-01, 22:38 UTC: three files, none empty |
| 3. The flow logs | 07:00 UTC: `Apply complete! Resources: 0 added, 0 changed, 2 destroyed.` |
| 4. The targets root | 07:00 to 07:02 UTC: `20 destroyed`. The plan named `rg-aisec-platform` only as its two peerings' remote networks |
| 5. The platform root | 07:02 to 07:07 UTC: `79 destroyed`, the four VMs and four peerings among them |
| 6. The bootstrap root made destroyable | Two files changed on the working tree. Both provider registrations removed from the state |
| 7. The bootstrap root | Four `NWTA-` resources deleted first, then `34 destroyed`, 07:15 to 07:23 UTC |
| 8. What is left | Three empty answers. `infra/bootstrap` back as committed |
| 9. The mesh VPN console | The router's node removed by hand. Not read back by a command |
| 10. The local files | The two identities' six files and the bootstrap state deleted |

Step 8's group query can fail: before step 7 it listed the four `rg-aisec` groups. A read of the whole subscription after step 10 found no resource named for the project or `NWTA-`. Left on purpose: `NetworkWatcherRG`, Azure's own, and the log workspace in Azure's 14-day soft delete.

Traffic analytics' data collection rules and endpoints, two of each, were still in `rg-aisec-platform` after step 5. Terraform does not manage them, and the provider refuses by default to delete a group that holds resources. They were deleted before the apply, so that refusal was not seen, and the runbook's step 7 now does the same.

The plans read on 2026-11-01 were saved in a temporary directory that was gone by the next morning. Steps 3 to 5 were planned again at 06:58 UTC and read again, with the same counts. The runbook saves its plans beside the state copies.
