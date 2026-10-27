# Proposals, pull requests, and delivery: operator procedure

Status: Implemented on 2026-10-27. Run once, on the live system, from scripts with the same commands ([worklog](../worklogs/0006-remediation-pull-requests-and-delivery.md#one-fix-end-to-end)): step 1 on 2026-10-26 for the job, steps 2 to 5 at 06:08 to 06:09 UTC, and steps 6 to 11 at 16:18 to 16:24 UTC. The merge in step 9 was the operator's, and the undo was not run.

This takes a NetBox job whose comparison matched from its proposal to a delivered fix: the policy check and a rehearsal on the copy on the orchestrator host, a pull request from the operator's machine, an approval tag signed with the approval key, and delivery with a token made for it ([ADR 0043](../decisions/0043-proposals-are-remove-only-and-a-policy-check-decides.md) to [ADR 0047](../decisions/0047-a-delivery-token-for-each-delivery.md)). It ends with the rollback and with the copy brought to the merged seed.

Before this:

- The rehearsal copy runs on the lab VM, and the change commands are installed with the approvers file: the [rehearsal copy runbook](rehearsal-copy.md), steps 1 to 22.
- A NetBox job ran and matched: the [evidence collection runbook](evidence-collection.md), steps 11 and 12.
- The approval key exists on the operator's machine, with a passphrase, and its public half is `APPROVERS` in the targets repository.

## Inputs and access

| Input | Notes |
| --- | --- |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md) |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-edge`, and `aisec-netbox` |
| A checkout of this repository | Run from its root, for `platform/change/edit_seed.py` |
| A checkout of the targets repository | `REPLACE_WITH_TARGETS_CHECKOUT`, with `main` fetched |
| The approval key | `REPLACE_WITH_APPROVAL_KEY`, the private half, used only by `git tag -s` and never added to an agent |
| The job | `REPLACE_WITH_JOB`, a NetBox job whose comparison matched |

## Propose

1. Run the policy check and the rehearsal for the job.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo propose-netbox-fix REPLACE_WITH_JOB'
   ```

   Expected: `policy: allowed`, `rehearsal: passed`, each contract account `within/within`, and the bundle's path. A refused or failed proposal prints its reasons and exits 1, and its bundle has no `pr-body.md`. A job is proposed once.

## Publish, from the operator's machine

2. Copy the bundle.

   ```bash
   mkdir -p REPLACE_WITH_BUNDLE
   for f in proposal.json pr-body.md; do
     REPLACE_WITH_SSH aisec-orchestrator "sudo cat /var/lib/aisec/proposals/REPLACE_WITH_JOB/$f" > REPLACE_WITH_BUNDLE/$f
   done
   ```

   Expected: both files. `pr-body.md` exists only for an allowed fix that passed its rehearsal.

3. A worktree on a new branch from `main`'s head, and the seed edit.

   ```bash
   git -C REPLACE_WITH_TARGETS_CHECKOUT fetch -q origin
   git -C REPLACE_WITH_TARGETS_CHECKOUT worktree add -b fix/netbox-REPLACE_WITH_JOB REPLACE_WITH_WORKTREE origin/main
   python3 -I platform/change/edit_seed.py REPLACE_WITH_WORKTREE/netbox/seed.json REPLACE_WITH_BUNDLE/proposal.json
   git -C REPLACE_WITH_WORKTREE diff --numstat
   ```

   Expected: one line per change, `PERMISSION: without ACCOUNT`, then `1 1 netbox/seed.json`.

4. Commit with the commit signing key, push, and open the pull request with `pr-body.md` as its body.

   ```bash
   git -C REPLACE_WITH_WORKTREE commit -am "fix: remove the unscoped permission the job REPLACE_WITH_JOB found"
   git -C REPLACE_WITH_WORKTREE push origin fix/netbox-REPLACE_WITH_JOB
   python3 -I -c 'import json, sys; print(json.dumps({"title": sys.argv[1], "head": sys.argv[2], "base": "main", "body": open(sys.argv[3]).read()}))' \
     "fix: remove the unscoped permission the job REPLACE_WITH_JOB found" fix/netbox-REPLACE_WITH_JOB REPLACE_WITH_BUNDLE/pr-body.md |
     gh api -X POST repos/sindredg/ai-security-platform-test/pulls --input - --jq '"\(.number) \(.head.sha)"'
   ```

   Expected: the pull request's number and head, then its eight checks pass.

## Approve

5. Sign a tag on the pull request's head with the approval key, and push it.

   ```bash
   cd REPLACE_WITH_TARGETS_CHECKOUT
   git -c gpg.format=ssh -c user.signingkey=REPLACE_WITH_APPROVAL_KEY tag -s approve/netbox/REPLACE_WITH_JOB -m "target: netbox" REPLACE_WITH_HEAD
   git -c gpg.ssh.allowedSignersFile="$PWD/APPROVERS" verify-tag approve/netbox/REPLACE_WITH_JOB
   git push origin refs/tags/approve/netbox/REPLACE_WITH_JOB
   ```

   Expected: a passphrase prompt, then `Good "git" signature for aisec-approver`. Delivery accepts the tag once, within 24 hours of its signature.

## Deliver

6. Open a fetch window, so the orchestrator can fetch the targets repository.

   ```bash
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 20'
   ```

   Expected: `open for 20 minutes`.

7. Make a token for this delivery on the NetBox VM, and pipe it into the delivery.

   ```bash
   tar -C REPLACE_WITH_TARGETS_CHECKOUT -cf - netbox | REPLACE_WITH_SSH aisec-netbox 'mkdir -p ~/netbox-install && tar -C ~/netbox-install -xf -'
   REPLACE_WITH_SSH aisec-netbox 'sudo ~/netbox-install/netbox/make-netbox-token.sh deliver 2>/dev/null' |
     REPLACE_WITH_SSH aisec-orchestrator 'sudo deliver-netbox-change approve/netbox/REPLACE_WITH_JOB'
   ```

   Expected: `fix COMMIT, read back: True`, each changed permission with its users, each contract account `within/within`, then `passed`. The same tag again prints `refused: approve/netbox/REPLACE_WITH_JOB: this approval was used already`, and nothing changes. Without a token on standard input the command exits 2 before it fetches.

8. Close the window.

   ```bash
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close'
   ```

   Expected: `closed`.

9. Merge the pull request, only after step 7 printed `passed`. Then fetch `main` in the targets checkout, so the checks read the merged seed.

   Expected: `N.14` and `N.17` pass with both accounts within.

## Roll back

10. Sign a tag on `main`'s head, and deliver it as in steps 6 to 8. A rollback needs its own approval.

    Expected: `restore MAIN, read back: True`, the seed's assignments back, and the checks' verdicts as `main`'s seed gives them, then `passed`. A restore passes when it reads back: the seed's own weakness comes back with it.

## Bring the copy to the merged seed

11. After the merge, give the copy the merged seed, and take its dump again so that each reset restores it.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo python3 -I -c '\''import json, sys
    sys.path.insert(0, "/usr/local/lib/aisec")
    import netbox_change, rehearse
    seed = json.load(sys.stdin)
    print("reset", rehearse.reset())
    copy = netbox_change.client(rehearse.COPY_URL, str(rehearse.COPY / "tls.crt"), str(rehearse.COPY / "tokens" / "aisec-deliver"))
    wanted = netbox_change.seed_assignments(seed)
    changes = netbox_change.plan(netbox_change.live_assignments(copy, sorted(wanted)), wanted)
    netbox_change.apply(copy, changes)
    print("applied", [(c["permission"], c["users"]) for c in changes])'\''' < REPLACE_WITH_TARGETS_CHECKOUT/netbox/seed.json
    REPLACE_WITH_SSH aisec-lab "sudo sh -c 'umask 077; cp -p /var/lib/aisec/rehearsal/seed.dump /var/lib/aisec/rehearsal/seed-before-fix.dump && runuser -u postgres -- pg_dump -Fc netbox > /var/lib/aisec/rehearsal/seed.dump'"
    REPLACE_WITH_SSH aisec-lab 'sudo sha256sum /var/lib/aisec/rehearsal/seed.dump' | cut -d " " -f 1 |
      REPLACE_WITH_SSH aisec-orchestrator "sudo sh -c 'umask 022; cat > /etc/aisec/netbox-rehearsal/reset/seed.sha256'"
    ```

    Expected: the old dump's SHA-256 from the reset, then one change per permission the fix changed. A reset through the account then prints the new SHA-256, and `Q.3` and `Q.5` pass with the merged seed.

## Undo

Not run. A delivered fix is undone by the rollback above. To remove the commands: on the orchestrator, `/usr/local/sbin/propose-netbox-fix`, `/usr/local/sbin/deliver-netbox-change`, the libraries `install-change.sh` put in `/usr/local/lib/aisec`, `/var/lib/aisec/proposals`, `/var/lib/aisec/delivery`, and `/etc/aisec/delivery/approvers`.
