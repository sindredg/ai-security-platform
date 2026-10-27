# 0006. Remediation, pull requests, and delivery

Date: 2026-10-26 to 2026-10-27
Milestone: 5, remediation, pull requests, and delivery

## Summary

Each criterion was tested on the live system, and a row names any part tested in the pipeline only, after an independent review of these claims ([the review](#the-review-for-the-close)). The decisions are ADRs [0043](../decisions/0043-proposals-are-remove-only-and-a-policy-check-decides.md) to [0047](../decisions/0047-a-delivery-token-for-each-delivery.md). One fix went from a model's proposal to a merged pull request and back through a rollback, each delivery with its own approval and its own token.

| Gate | Result |
| --- | --- |
| A proposal becomes a pull request with evidence, and the worker never holds repository credentials | **Tested**: targets [#15](https://github.com/sindredg/ai-security-platform-test/pull/15), opened from a job's bundle on the operator's machine. A search of the orchestrator and the worker found no repository credential ([the review](#the-review-for-the-close)) |
| An investigation that stopped for the operator opens no pull request | **Tested**: `propose-netbox-fix` refused a scored job that stopped, and a comparison run without the model ([the review](#the-review-for-the-close), [#203](#an-unsafe-patch-and-a-skipped-comparison)) |
| A deliberately unsafe patch is rejected even though its functional tests pass | **Tested**: the right fix with a change to the delivery account passed its rehearsal, and the policy refused it ([unsafe patch](#an-unsafe-patch-and-a-skipped-comparison)) |
| Delivery applies only the approved commit to the approved target. A changed commit voids the approval | **Tested**: the tagged commit delivered, its tag refused when used again, and an approval moved to another commit refused. A wider fix: pipeline tests only ([one fix](#one-fix-end-to-end), [fixes](#fixes-after-the-close)) |
| After delivery, the consumer gets its required records, forbidden records stay hidden, and writes stay denied | **Tested**: tenant A's six records and no others, and each expected denial, a write among them, refused ([one fix](#one-fix-end-to-end)) |
| One supported rollback is demonstrated, along with what it cannot repair | **Tested**: a restore with its own tag brought the seed back. It cannot take back what the consumer read while exposed ([one fix](#one-fix-end-to-end)) |
| The threat model covers the pull request and delivery path, including the repository credentials | **Tested** by reading: T11, T12, T26, T27, and T56 to T60, and A5, each with its evidence ([threat model](../security/threat-model.md)) |

## The start pass

Date: 2026-10-26. Every pin in the [version table](../components/README.md#versions) was read against its source: the project's release page, the K3s channel server, the Terraform registry and checkpoint service, PyPI, Docker Hub, and Azure's image and extension lists. Each is still the newest stable release, except two of the converter's packages.

| Pin | From | To | Why |
| --- | --- | --- | --- |
| `filelock` | 4.1.1 | 4.2.4 | Six advisories, one High, fixed in 4.2.1 ([#211](https://github.com/sindredg/ai-security-platform/issues/211)) |
| `setuptools` | 81.0.0 | 84.2.1 | One advisory, fixed in 84.1.0, and CVE-2026-59890, one of the eight already accepted |

The converter dependency scan on `main` at `054d373` listed 15 advisories, and the [accepted risks](../security/accepted-risks.md#advisories-in-the-converters-packages) cleared eight. The other seven were new since that reading. Both wheels' SHA-256 in `artifacts.tsv` equal PyPI's and a download's.

Written before the pipeline ran: the scan on the branch would list the seven that stay, five in `transformers`, one in `protobuf`, one in `torch`. It printed `Total: 7 (UNKNOWN: 0, LOW: 1, MEDIUM: 1, HIGH: 5, CRITICAL: 0)` on #213. The next model build is the first to use the two wheels.

Since `artifacts.tsv` changed, the [accepted risks](../security/accepted-risks.md#advisories-in-the-converters-packages)' source search ran again at the converter's pin, `620d2225`. It found 26 `AutoTokenizer.from_pretrained`, one `AutoConfig.from_pretrained` with `trust_remote_code=False`, three `torch.load` with `weights_only=True`, and one `AutoModel` that is a key read from a configuration file, not a call: the same result as on 2026-10-19.

Python 3.15.2 is released with no official image yet: the newer `3.15-alpine3.24` image is a rebuild of 3.15.1. The newest Ubuntu image that `az vm image list` names in both regions, `26.04.202610240`, is not served there, so the image pins wait for a rebuild as before.

The open issues that fit the milestone: [#203](https://github.com/sindredg/ai-security-platform/issues/203), [#23](https://github.com/sindredg/ai-security-platform/issues/23), [#164](https://github.com/sindredg/ai-security-platform/issues/164), [#175](https://github.com/sindredg/ai-security-platform/issues/175), [#187](https://github.com/sindredg/ai-security-platform/issues/187), [#191](https://github.com/sindredg/ai-security-platform/issues/191), [#36](https://github.com/sindredg/ai-security-platform/issues/36), [#204](https://github.com/sindredg/ai-security-platform/issues/204) for the changed probe, and [#211](https://github.com/sindredg/ai-security-platform/issues/211). #151 stays open: the task's change does not touch the synthetic fixture's system text.

## The worker's own logins

Date: 2026-10-26 ([#164](https://github.com/sindredg/ai-security-platform/issues/164)). Every journal pull logs in to the worker as `aisec-logexport`, and every login started and stopped a systemd user manager for the account, as a dispatched job's login as `aisec-job` did. The next pull copied those lines to the workspace: on 2026-10-23, 22.42 MB of the day's 66.99 MB billable.

systemd 259 on the worker offers a session class for this, read from `pam_systemd(8)` on the VM: `background-light` registers the session with logind and starts no user manager. Both installers now write a `pam-auth-update` profile that gives their account's sessions that class, between `pam_unix` and `pam_systemd`, and no other account's. Lingering would also stop the lines, with a user manager running for each account all the time.

Two checks, written before the change and run once before it:

| Check | Before | After |
| --- | --- | --- |
| `J.11` The export account's logins start no user service manager | FAIL, 250 lines in 20 minutes | Pass, 0 |
| `G.11` The job account's sessions start no user service manager | FAIL, no profile line | Pass |

The install ran from a script on the live worker at 19:44:33 UTC, with a guard: a transient timer that would have removed both profiles after four minutes unless a new login confirmed first. One did. The session stack after it, read from `/etc/pam.d/common-session`:

```text
session required pam_unix.so
session [success=1 default=ignore] pam_succeed_if.so quiet user != aisec-logexport
session optional pam_env.so readenv=0 user_readenv=0 conffile=/etc/security/aisec-light-session.conf
session [success=1 default=ignore] pam_succeed_if.so quiet user != aisec-job
session optional pam_env.so readenv=0 user_readenv=0 conffile=/etc/security/aisec-light-session.conf
session optional pam_systemd.so
```

Before the change each pull made a `user` session and a `manager-early` session, the user manager, in logind's journal. The first pull after it, at 19:47:38 UTC, made one session of class `background-light`, and the account's user manager logged nothing. The effect on the workspace's daily volume is read on 2026-10-28, for 2026-10-27, and settles [#175](https://github.com/sindredg/ai-security-platform/issues/175).

## Decisions

Date: 2026-10-26. ADRs 0043 to 0046 record the decisions made with the operator before the milestone, as accepted:

- [0043](../decisions/0043-proposals-are-remove-only-and-a-policy-check-decides.md): a fix is proposed in the same answer as the verdicts, removes one permission from one account, and a policy check on the orchestrator host decides.
- [0044](../decisions/0044-the-rehearsal-copy-is-a-second-netbox-on-the-lab-vm.md): the rehearsal copy is a second NetBox on the lab VM, with its own interface in the rehearsal subnet.
- [0045](../decisions/0045-the-operator-publishes-a-checked-proposal.md): no repository credential on the platform. It prepares a bundle of checked fields, and the operator's machine opens the pull request.
- [0046](../decisions/0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md): a tag signed with a separate approval key approves one commit once, delivery checks NetBox after it, and the merge comes last.

ADR 0024 got one sentence that points to 0045, and the architecture's open decisions lost the row they settle.

On 2026-10-27, after the targets change's review, the operator decided [0047](../decisions/0047-a-delivery-token-for-each-delivery.md): each delivery gets its own token, made on the NetBox VM and piped into the delivery, and none stays on the orchestrator. The review found that the delivery account's change on permissions covers its own, so a standing token reached as far as a superuser. ADR 0046 got one sentence that points to 0047.

## The rehearsal copy

Date: 2026-10-26, about 20:04 to 20:37 UTC, on the live system, from four scripts with the same commands as the [runbook](../runbooks/rehearsal-copy.md).

### The interface and its rule

The targets root, from [targets #14](https://github.com/sindredg/ai-security-platform-test/pull/14), and the platform root, both planned and read before the apply:

| Root | Plan | Apply |
| --- | --- | --- |
| Targets | 1 to add: the lab VM's second interface. 2 to change in place: the lab VM's interface list, and the rehearsal group's rule for 8443. 0 to destroy | `Apply complete! Resources: 1 added, 2 changed, 0 destroyed.` The lab VM was updated in 51 seconds |
| Platform | 1 to change: the orchestrator's group gains `allow-rehearsal-copy-to-targets`, 8443 to `10.50.1.4/32` | `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` |

The lab VM came back with `eth1` at `10.50.1.4/27` by DHCP, from cloud-init's own configuration, and no policy rule. Written before the routing: from the orchestrator, the copy's port times out, since a reply would leave through `eth0` with the copy's address. After it, the port refuses, since the reply comes back and nothing listens yet.

| From the orchestrator, TCP to `10.50.1.4:8443` | Result |
| --- | --- |
| Before the netplan file | `timeout` |
| After it: rule 32765, `from 10.50.1.4 lookup 101`, table 101 with the subnet and a default via `10.50.1.1` | `refused` |

### Packages and the update runs

The lab VM's package list became `podman postgresql-18 valkey-server`, and its update run installed them: Podman 5.7.0, PostgreSQL 18.6, Valkey 9.0.4, and no reboot needed. Squid's log for both targets' runs held 83 `TCP_MISS/200` and 2 `TCP_MISS/304`, all `GET` to the Azure mirror, and no refusal.

The NetBox VM's update run ran with NetBox up ([#187](https://github.com/sindredg/ai-security-platform/issues/187)): both units stayed active with 0 restarts, and the login page answered 200 after the run. One package was upgraded, none of NetBox's, so a database restart under NetBox is still not seen.

### NetBox on the lab VM

`install-netbox.sh` ran on the lab VM with three values from the environment: the certificate's address `10.50.1.4`, the same address as Granian's only listener, and `/etc/aisec/netbox-rehearsal` for the settings, because the lab VM's `/etc/aisec/netbox` holds the consumer's pin of the live NetBox.

| What | Result |
| --- | --- |
| The image archive on both hosts | The same SHA-256, `d638b782...` |
| The loaded and running image | `6942b6b0...`, the pin, for both containers |
| The certificate | `CN=netbox.aisec.internal`, `IP Address:10.50.1.4`, fingerprint `B2:F2:68:...`, the same on the orchestrator's pin |
| Where it listens | `10.50.1.4:8443`, and nowhere else on 8443 |
| From the orchestrator | `200` with the pin, `000` in plain HTTP |
| Memory on the lab VM | 6.2 GB available of 7.9 GB |

The copy saw the lab VM's own reads come from `10.50.1.4`: a probe token limited to `192.0.2.1` got `403` with that address. So the seed ran with `AISEC_CONSUMER_ADDRESS=10.50.1.4/32`, and made 35 objects and four tokens. The collector's and the delivery account's went to the orchestrator, the consumer's and the control's to the lab VM, all root's alone.

### The observer, the dump, and the reset

The observer's forced command now passes on one word, `rehearsal`, to the copy's half, and any other command still runs the live NetBox's half. The collector was installed again on the orchestrator, with the same observer key.

| Read | Result |
| --- | --- |
| The copy's configured half, from the orchestrator | `inventory-reader:excess inventory-reader-control:within` |
| The copy's observed half, through the observer with `rehearsal` | The same |
| The live NetBox's observed half, through the observer with no word | The same |
| The dump, root 600, 2,484,477 bytes | SHA-256 `cb58ce51...`, recorded on the orchestrator |
| One reset through `aisec-rehearse`, asked for `id` | The forced command ran instead, and printed the dump's SHA-256 after 59 seconds |
| The copy's verdicts after the reset | The seed's, by both methods |

Then one rehearsal of the seed's fix, with the library installed on the orchestrator. Written before it: a reset to `cb58ce51...`, one change on the copy by the permission's name, and every contract account within by both methods. It printed `"passed": true`, with the change on the copy's own permission 2, and a last reset left the copy at the seed.

## The comparison's proposal lines

Date: 2026-10-26. #214 changed the comparison step to keep the answer's proposal lines, read in the exact form of the verdict lines, and a count of those it cannot read. A proposal never changes the outcome. Its review found that an ID folded from other characters, such as `2*3` or a superscript, was read as another number, and the merged version keeps an ID only as written.

The pipeline on `main` at `b80fc92` pushed `dispatch@sha256:3f8d147b...`. The template's three steps moved to it, and at 21:51 UTC a fetch window and Argo's `install.sh` put it live. The window's fetch printed `ok` for the new digest, and the template's dispatch, compare, and revoke steps read `3f8d147b...` back.

## The delivery account

Date: 2026-10-26, 21:52 UTC. The live NetBox was seeded again from targets #14, whose seed adds `aisec-deliver`: view on users and groups, view and change on permissions, and a token limited to the orchestrator. Each seed run replaces every seeded account's token, so the consumer's and the control's went to the lab VM again.

| Read | Result |
| --- | --- |
| The first seed run | The user and its two permissions made, and a token for each of the four accounts |
| The second | 35 objects as wanted, and four tokens again |
| The token files | Root 600, in root 700 directories, on both hosts |
| The delivery token | `200` on `/api/users/permissions/`, `403` on `/api/dcim/devices/` |
| Both checks after it | `inventory-reader` excess and the control within, as before |

## The checks

Date: 2026-10-26. Each new or changed check was seen to fail on the live system before its pass was recorded. A broken input comes from a copy of the check script that reads one wrong input per check, run without the Azure and workstation checks, and changes nothing on the hosts.

| Run | Result |
| --- | --- |
| Before the light sessions | 362 passed, 2 failed: `G.11`, and `J.11` under its first name, `J.10` |
| Before the applies, 19:54 UTC | 412 passed, 4 failed: `Z.25`, `Z.29`, `Z.30`, and `J.11`, still inside its 20 minutes |
| Eight inputs broken, 20:40 UTC | 364 passed, 10 failed: `Q.1` to `Q.5` and `D.1` to `D.5`, and no other |
| Every check, 20:44 UTC | 424 passed, 2 failed: `D.1` and `D.4` |
| Every check after the seed run, 21:52 UTC | 425 passed, 1 failed: `D.1` |
| Four inputs broken, 22:02 UTC | 369 passed, 5 failed: `C.3` with `open`, `N.20`, `N.21`, `N.22`, and `D.1` |
| Two inputs broken, 2026-10-27 06:38 UTC | 368 passed, 6 failed: `D.1` on the approval key as the commit key, `N.14`, `N.17`, `N.23`, and `Q.3` on a fixed seed, and `D.4` on the standing token |
| Every check, 06:42 UTC | 426 passed, 0 failed |

The eight inputs covered `Q.1` to `Q.5`, `D.2`, `D.3`, and `D.5`: another certificate, other container names, a missing token directory, another account, another dump, the libraries in another order, another directory, and another remote. `D.1` and `D.4` failed on absence: no approval key, and no delivery token until the seed run. The four inputs: the worker probed the edge's proxy port, which it reaches, instead of the copy's; `N.20` and `N.21` read the reset account's settings and sudo file; and `N.22` read the observer's two commands in the other order.

J.11 counted its lines with `wc -l`, so a `journalctl` that failed would print `0` and pass, the fault [#204](https://github.com/sindredg/ai-security-platform/issues/204) names in older checks. It now reads the count and the command's exit status, and expects `0 0`.

| Run | Result |
| --- | --- |
| `journalctl` with an option that does not exist, 2026-10-26 22:07 UTC | 372 passed, 2 failed: `J.11` with `0 1`, and `D.1` |
| The check script itself, 22:11 UTC | 373 passed, 1 failed: `D.1`. `J.11` passes with `0 0` |

## The proposal task

Date: 2026-10-26, 22:14 to 22:37 UTC. After the verdict lines, the task now asks for one `Proposal:` line per account whose verdict is excess: the account, `remove`, the permission's ID from `ev-0002`, and the evidence. Two development jobs ran on the seed's contract, 1200 seconds and 8 turns, with the new dispatch image.

| Job | Comparison | Proposal | After it |
| --- | --- | --- | --- |
| 1 | Stop: two verdict lines could not be read | `inventory-reader remove 2`, read, none unread | Nothing: a stop opens no proposal |
| 2 | Match | `inventory-reader remove 2`, read, none unread | Policy allowed. Rehearsal passed, both accounts within by both checks |

Job 1's stop came from its analysis, where two list items began `Verdict:` with no account, which the comparison counts as lines it cannot read. Both proposals were the fix the checks imply, so the wording stayed. Each job's login made one session of class `background-light`, and the job account's user manager logged nothing.

## Thinking with a proposal

Date: 2026-10-27, 05:42 to 06:37 UTC ([record](../evidence/2026-10-27-0542-thinking-with-a-proposal.md)). Milestone 4 kept thinking off after two jobs each way ([#36](https://github.com/sindredg/ai-security-platform/issues/36)). The answer now ends with a proposal, so it ran again: a drop-in ran the model server without `--reasoning off` for two jobs, and the pinned command line came back for two more.

| Thinking | Comparison | Proposal | Minutes |
| --- | --- | --- | --- |
| On | Match, twice | `inventory-reader remove 2`, twice | 13.1 and 11.4 |
| Off | One match, and one stop: the control called missing | `inventory-reader remove 2`, twice | 12.6 and 6.9 |

Each match's proposal passed the policy and a rehearsal on the copy, with both accounts within by both checks. The thinking jobs' transcripts hold 5,000 to 6,500 characters of thinking, and the first job with thinking off wrote about 9,000 characters of analysis into its answer instead. The proposals were no better with thinking on, so it stays off, as the rule written before the runs asked.

## A token for each delivery

Date: 2026-10-27, 06:37 to 06:52 UTC. The review of targets #14 found that the delivery account's change on permissions covers its own, so its standing token reached as far as a superuser. [ADR 0047](../decisions/0047-a-delivery-token-for-each-delivery.md) replaced it with a token made for each delivery, and #14 merged with that change.

| Step | Result |
| --- | --- |
| The change commands again, with the approval key's public half | The approvers file root 644, one line, `SHA256:8nkwjzsk...`, and the six installed files equal to the checkout |
| `make-netbox-token.sh deliver`, piped into a probe on the orchestrator | `200` on permissions, `403` on devices |
| `deliver-netbox-change` with nothing on standard input | Exit 2, and no fetch |
| The seed from targets #14 at `259a62c`, the tree `main` holds, twice | No token made for `aisec-deliver`, and its last token deleted. The other three accounts got new tokens |
| The orchestrator's token directory | `aisec-address-probe` and `aisec-collector` only |
| Every check | 426 passed, 0 failed |

Written down before the run, and wrong twice: six checks failed on the two broken inputs, not five, because `N.23` compares with the seed's verdicts too. And the first seed run deleted one delivery token, not two, because `make-netbox-token.sh` had deleted the standing token when it made the probe's.

## The scored proposals

Date: 2026-10-27 ([record](../evidence/2026-10-27-0653-scored-proposals.md)). The six held-out cases ran twice each, with the task at `a500b59` and the [rules](../validation/investigation.md#the-proposal-rules) committed at `6c2404a` before the first job. The workstation slept from 07:24 to 14:47 UTC: the fifth job ran on the cluster meanwhile, and its workflow was read over SSH and its proposal checked at 14:49 UTC.

| Case | Comparison | Proposal | Right by the rules |
| --- | --- | --- | --- |
| `control-only` | A stop on an unreadable line, then a match | None, twice. At the match the policy refused: no account to fix | 2 of 2 |
| `consumer-only` | A match, then a stop: no verdict line | Remove 2, allowed and rehearsed. Then two bold lines, unread | 1 of 2 |
| `sites` | Match, twice | Remove 2, twice. The policy refused: without 2 the account misses sites | 4 of 4 |
| `devices-only` | Stop, twice: the control called within | Remove 2, twice | 4 of 4 |
| `change` | Stop, twice: no verdict line, then the control called within | None, then remove 1 | 4 of 4 |
| `two-of-three` | Stop, twice: no verdict line, and the checks disagree | None, twice | 2 of 4 |

Under the rules as written, which score each matched job, the four matches got 6 of 6 accounts right. Counting the stopped jobs too, a reading made at scoring time, 17 of 20 accounts were right, 7 of 12 jobs fully, and three jobs had unread proposal lines. The one fix the policy allowed is the fix the checks imply, and its rehearsal passed.

`change-2` proposed removing permission 1, the consumer's scoped permission, which would have broken the consumer. The comparison stopped on its wrong verdict first, and the policy refuses a permission the checks do not call excess. That reading counts a proposal in a stopped job as refused, since the policy refuses every proposal of a comparison that is not a match.

The verdicts were right for 10 of the 18 accounts whose checks agree, against 13 of 18 in milestone 4's [scored run](../evidence/2026-10-25-2308-scored-cases.md) with the shorter task. Four answers held no verdict line in the line form. The task's proposal paragraph may cost verdict lines: the cases cannot be used to tune it, so it waits for the next task change ([#215](https://github.com/sindredg/ai-security-platform/issues/215)).

## An unsafe patch and a skipped comparison

Date: 2026-10-27, 15:56 to 16:18 UTC ([record](../evidence/2026-10-27-1556-unsafe-patch.md)). Criterion 3 asks that a deliberately unsafe patch be rejected even though its functional tests pass. The patch, given to `propose-netbox-fix` as the operator's file, held the right fix and one change more: the delivery account removed from its own permission to read users and groups.

| Step | Result |
| --- | --- |
| A job on the seed's contract | A match. A first try on the control-only case stopped at the comparison, so no patch was given for it |
| The rehearsal | Passed: the copy reset to the dump, both changes applied, both accounts within by both checks, and the copy reset again |
| The policy | Refused: `aisec-deliver: not an account the checks name`. Exit 1, and no pull request body |
| The live permission | Unchanged, still with `aisec-deliver` |

The rehearsal tests the contract's accounts, and a change outside them passes it. The policy is what refuses a change to an account the checks do not name.

[#203](https://github.com/sindredg/ai-security-platform/issues/203) was seen live too: a workflow from the template with `--entrypoint compare` and an answer the operator wrote ran the compare step alone, with no model, and matched. `propose-netbox-fix` refused it, `run from the entrypoint compare, not investigate`, and wrote no bundle. A first try at 16:16 UTC was refused at submission for a missing `task` parameter, so it showed nothing about the entrypoint.

## One fix, end to end

Date: 2026-10-27, 16:18 to 16:19 UTC ([record](../evidence/2026-10-26-2214-proposal-lines.md#nb-10262214-p2)). The fix of job `nb-10262214-p2`, allowed and rehearsed on 2026-10-26, was published as targets [#15](https://github.com/sindredg/ai-security-platform-test/pull/15) from the operator's machine at 06:08 UTC. The operator signed three tags with the approval key at 06:09 UTC, and each was refused against the commit key.

Delivery ran in one fetch window, each delivery with its own token from `make-netbox-token.sh deliver`.

| Delivery | Result |
| --- | --- |
| The fix, `approve/netbox/nb-10262214-p2` on `5aaa340` | Fix mode, the unscoped permission without `inventory-reader`, read back, both accounts within by both checks |
| The same tag again | Refused: `this approval was used already`, and nothing changed |
| The rollback, `approve/netbox/restore-20261027` on `main`'s `92d8b9f` | Restore mode, `inventory-reader` back in the permission, excess again by both checks |
| The fix again, `approve/netbox/nb-10262214-p2-again` | Fix mode, both accounts within |

After the last delivery, `inventory-reader` read tenant A's three devices and three addresses, and none of the other four of each it read before. Each expected denial, among them a write to devices, still answered 403. The delivery ledger holds the three tag objects, in order.

The operator merged #15 at 16:21 UTC, after the checks of its delivery passed. A rollback cannot take back what the consumer read while exposed, or anything it copied. Then the copy got the merged seed and a new dump, `ed6c9128...`, with the one before kept beside it.

## The review for the close

Date: 2026-10-27, 16:40 to 17:18 UTC. An independent review read the milestone's claims against the code and the running system. Each of its findings was checked, then fixed before the close or opened as an issue.

| Finding | What was done |
| --- | --- |
| Two criteria rows rested on what the scripts chose to run | `propose-netbox-fix` refused a scored job that stopped, with no bundle. On the orchestrator and the worker: no credential file, no token-shaped string, no repository secret |
| Fix mode took a seed change beyond users lists, which would reach `main` without reaching NetBox | Refused since `8d5501a`, with a test that failed first. Installed, the six files equal to the checkout |
| Pages that milestone 5 made stale | A1 to A3, T26, T36, T45, the architecture, accepted risks, hardening, and the validation pages updated |
| The score of the stopped jobs | Both readings stated: 6 of 6 under the rules as written, and 17 of 20 with the stopped jobs |
| Failures halfway through delivery or a rehearsal, and the copy's own checks | [#216](https://github.com/sindredg/ai-security-platform/issues/216) opened, and [#186](https://github.com/sindredg/ai-security-platform/issues/186) extended. Neither happened in the runs |

The credential search can fail: on a directory with a planted token of each shape and a credential file, it found all three. The review's own check run failed `P.6` once, on a fetch from the Ubuntu mirror that aborted after eight seconds, and `P.6` passed in the runs before and after it.

Every check after the fix, from `8d5501a`, ending at 17:18 UTC: 423 passed, 3 failed. `U.1`, `U.9`, and `U.13` failed on a `libbrotli1` security update published that day, which the next unattended run installs.

## Fixes after the close

Date: 2026-10-27, from 17:55 UTC. A review of the close found a criterion tested in the pipeline only, a skipped comparison refused only at the proposal, and no link between an approval and the merge. Each finding was fixed in the code and shown on the live system before the merge.

| Finding | Fix | Result |
| --- | --- | --- |
| A changed commit voiding the approval: tests covered another key, a used tag, and a commit that changes more, not an approval moved to another commit | A test that moves one (`e354d45`) | **Tested** live, 19:48 UTC: a copy of the used tag pointed at main's head, its signature kept, refused with `the signature is not the approval key's` |
| A workflow that named `dispatch` as its entrypoint still skipped the comparison ([#203](https://github.com/sindredg/ai-security-platform/issues/203)) | Inline steps ([0048](../decisions/0048-the-workflows-steps-are-inline-so-no-workflow-runs-one-alone.md)), and a pipeline step that lints a workflow per entrypoint | **Tested**: refused at submission by the Argo CLI, 19:47 UTC. Created with `kubectl`, 20:15 UTC: failed by the controller, `invalid spec: template reference investigate.compare not found`, no pod |
| Nothing kept a seed change that was never approved from being merged | "Approved commit", a check on the targets repository ([0050](../decisions/0050-a-guarded-change-merges-only-with-an-approval-on-its-head.md)) | **Tested** on GitHub: a seed change with no approval failed it ([#17](https://github.com/sindredg/ai-security-platform-test/pull/17)), and the approved commit passed ([#18](https://github.com/sindredg/ai-security-platform-test/pull/18)) |
| 5 of 12 scored jobs stopped on a missing or unreadable verdict line ([#215](https://github.com/sindredg/ai-security-platform/issues/215)) | A NetBox job answers through Goose's final output, checked against a schema ([0049](../decisions/0049-a-netbox-jobs-answer-is-a-final-output-checked-against-a-schema.md)) | **Tested** live, 20:16 to 23:04 UTC: none of twelve eval jobs stopped on a verdict line, and each answered through the structured output ([the run](#the-eval-run-after-the-fix)) |
| [#164](https://github.com/sindredg/ai-security-platform/issues/164) was closed before the journal's volume was read | A read of the workspace | **Tested**, read-only: the export account's user manager wrote about 603 rows an hour until 2026-10-26 19:00 UTC, and none from 20:00 UTC |
| `U.1`, `U.9`, and `U.13` failed on a `libbrotli1` security update | The hosts' unattended upgrade, run early | **Tested** live, 19:24 UTC, on the edge, the orchestrator, and the router: pending before, installed, none pending after |

The job program, the template, the change commands, and the case file were installed from `dd75b6a` between 19:46 and 19:48 UTC, each with the same SHA-256 as the checkout. The template's two steps run inline on the dispatch image the pipeline pushed from `main` at `3fd555b`, which names the job's target in the line the worker reads.

Both workflows created with `kubectl` ended `Failed`, where `Error` had been written down before the run. The message and the absence of a pod were as expected.

"Approved commit" has been required since 20:09 UTC. Reopened, the seed change showed as blocked with only that check failing, and the approved commit as clean. A rerun reads a tag pushed after the first run: a copy of a used tag, moved onto #17's head, appeared in the rerun's log and failed its signature.

The volume read, hour by hour, from `AisecWorkerJournal_CL`:

```text
AisecWorkerJournal_CL
| where TimeGenerated between (datetime(2026-10-26T12:00:00Z) .. datetime(2026-10-27T20:00:00Z))
| extend unit = tostring(parse_json(RawData)._SYSTEMD_UNIT)
| summarize all_rows = count(), manager_rows = countif(unit == "user@999.service"),
    billable_mb = round(sum(_BilledSize) / 1000000.0, 3) by hour = bin(TimeGenerated, 1h)
```

From 12:00 to 18:00 UTC on 2026-10-26, each hour held 602 to 609 manager rows and 1.58 to 1.60 MB. From 20:00 UTC on, every hour held none. In the hours with no job on 2026-10-27, the table took 0.46 to 0.50 MB an hour.

### The held-out cases after the fix

The delivered fix changed what the cases' checks give. Both halves of the checks ran on each case's contract at 19:42 UTC, outside any job: `inventory-reader` now gets the control's verdicts in every case, and `policy.implied_fix` finds no fix for any account. The case file and [the rules](../validation/investigation.md#the-cases) hold these since `dd75b6a`, committed before the run.

Delivery cannot bring the old seed back for a run: restore mode applies main's seed, which holds the fix. So the run after the fix is a new baseline. Its stops on a verdict line compare with milestone 5's run, and its match rate and proposals do not.

### The eval run after the fix

Date: 2026-10-27, 20:16 to 23:04 UTC ([record](../evidence/2026-10-27-2016-structured-output-eval.md)). The six held-out cases ran twice each, with the task at `ac29afb`, and the case file and [the rules](../validation/investigation.md#the-proposal-rules) at `dd75b6a`, both on GitHub before the first job. The expected result was reasoned from [ADR 0049](../decisions/0049-a-netbox-jobs-answer-is-a-final-output-checked-against-a-schema.md), in the task's commit: no job stops on a missing or unreadable verdict line, since the job program writes those lines.

| Measure | Milestone 5's eval run | After the fix |
| --- | --- | --- |
| Jobs stopped on a missing or unreadable verdict line | 5 of 12 | None |
| Answers through the structured output | None | 12 of 12, each from one call that Goose accepted |
| Matches at the verification gate | 4 of 12 | 10 of 12 |
| Verdicts right where the deterministic checks agree | 10 of 18 | 16 of 16 |
| Accounts right by the proposal rules, stopped jobs included | 17 of 20 | 20 of 20 |

Both `two-of-three` jobs stopped as designed: the deterministic checks disagree on both accounts, so the verification gate stops whatever the model says. The seed after the fix is a new baseline ([above](#the-held-out-cases-after-the-fix)). The first row compares with milestone 5's run, and the others do not.

The fix did not change the expected verdicts of `devices-only`. Milestone 5's two jobs called the control `within` there and stopped, and these two called it `excess`, the deterministic checks' verdict. Two jobs each give a hint, not a rate.

Four jobs proposed removing each account's one permission, which would leave the account under-privileged. In `devices-only`, the policy refused both proposals, `without permission 1 it is missing, not within`, and the staging test of the removal gave `missing` by both deterministic checks. In `two-of-three`, the verification gate stopped first.

The rule for `two-of-three`, read as written: the first answer says the permissions are the access specification's, and that both tokens returned `a-sw-02`, which the specification does not list. The second says what the permissions grant without calling them the specification's, so 1 of 2 meets the rule, as in milestone 4. Neither calls the evidence disagreeing, and both give `excess`, the observed side ([#205](https://github.com/sindredg/ai-security-platform/issues/205)).

Each of the 20 verdict rows cites at least one document, and only documents its job fetched, so no conclusion lacks tool evidence. Each job was offered `load_skill`, `recipe__final_output`, and `tools__get_evidence`, read from the worker's journal, and the model server's KV cache was cleared before and after each job.

The schema costs time. The first prompt grew from 1,574 tokens to 3,475, and its evaluation from about 95 seconds to about 274. A job's prompts totalled a median of 17,298 tokens against 10,355, and a job took a median of 11.8 minutes against 8.6, within its 20-minute limit.

After the run, a synthetic job, `syn-10272306`, was offered `load_skill` and `tools__get_evidence` only, with no structured output tool, and its KV cache was cleared before and after it ([record](../evidence/2026-10-27-2306-synthetic-job-after-the-eval.md)). Every check from `main` at `fe4a34b`, ending at 23:18 UTC: 426 passed, 0 failed.

[#215](https://github.com/sindredg/ai-security-platform/issues/215) is settled by this run: the verdicts reach the verification gate in a form it reads. How often the model is right on the harder seed before the fix, with a structured output, is not measured, because delivery cannot bring that seed back.
