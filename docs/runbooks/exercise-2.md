# Exercise 2, excess network access: operator procedure

Status: Steps 1 to 10 ran on 2026-11-01, on the live system, steps 5 to 10 from scripts: the seed, the install, and three jobs, none of which answered within its limit. Step 1's refusal was seen on a test pull request, not the seed's. Steps 11 to 16, the proposal and the fix, not run.

This seeds a pair of port rules that lets the staging subnet reach the live NetBox's port, collects and judges each viewpoint, runs a NetBox job on it, and delivers the job's fix by a Terraform apply of the merged rules file ([ADR 0056](../decisions/0056-exercise-2-judges-viewpoints-by-netboxs-port-rules-kept-as-data.md)). The unintended viewpoint is the lab VM's staging address, `10.50.1.4`, and the consumer's is `10.50.0.36`.

Before this:

- NetBox, the staging copy, and the change commands run: the [NetBox runbook](netbox.md), the [staging copy runbook](rehearsal-copy.md), and the [proposals runbook](proposals-and-delivery.md).
- The targets repository holds `infra/targets/netbox-rules.json`, which `main.tf` reads, and the contract's network part in `netbox/contract.json`.
- The operator's Argo account works: the [workflows runbook](workflows.md).

## Inputs and access

| Input | Notes |
| --- | --- |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md) |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-edge`, and `aisec-lab` |
| A checkout of this repository | Run from its root |
| `REPLACE_WITH_TARGETS_CHECKOUT` | A checkout of the targets repository, with `main` fetched |
| The target deployment identity | `REPLACE_WITH_CRED_DIR/targets.env`, as in the [network foundation runbook](network-foundation.md) |
| The approval key | `REPLACE_WITH_APPROVAL_KEY`, used only by `git tag -s` |
| No workflow running | Step 7 restarts the tool service |

## The seed

1. In a branch of the targets repository, add the pair to `infra/targets/netbox-rules.json`: an inbound allow on the `netbox` subnet and an outbound allow on the `rehearsal` subnet, both named `allow-netbox-from-rehearsal` at priority 1120, from `10.50.1.0/27` to `10.50.0.4/32` on 8443. Open a pull request.

   Expected: "Approved commit" fails with `The pull request changes infra/targets/netbox-rules.json, so its head needs an approval`, and every other check passes.

2. Approve the head as in the [proposals runbook](proposals-and-delivery.md#approve), step 5, with the tag `approve/netbox/REPLACE_WITH_SEED_NAME`, then merge.

   Expected: "Approved commit" passes on its rerun with `ok approve/netbox/REPLACE_WITH_SEED_NAME approves REPLACE_WITH_HEAD`.

3. Plan and apply `main`.

   ```bash
   cd REPLACE_WITH_TARGETS_CHECKOUT/infra/targets
   git switch main && git pull --ff-only
   source REPLACE_WITH_CRED_DIR/targets.env
   terraform plan -out REPLACE_WITH_PLAN
   terraform apply REPLACE_WITH_PLAN
   ```

   Expected: `0 to add, 2 to change, 0 to destroy`, the `netbox` and `rehearsal` security groups, each with one new rule.

4. Connect from both viewpoints.

   ```bash
   REPLACE_WITH_SSH aisec-lab 'for a in 10.50.0.36 10.50.1.4; do
     timeout 8 python3 -I -c "import socket, sys
   s = socket.socket(); s.bind((sys.argv[1], 0)); s.settimeout(5)
   try: s.connect((\"10.50.0.4\", 8443)); print(sys.argv[1], \"open\")
   except socket.timeout: print(sys.argv[1], \"timeout\")" "$a"; done'
   ```

   Expected: `10.50.0.36 open` and `10.50.1.4 open`. Before the seed, the second is `timeout`.

## Install

5. Copy the collector and the change commands to the orchestrator with the contract, and install both.

   ```bash
   D=$(tar -cf - collectors/netbox platform/change |
     REPLACE_WITH_SSH aisec-orchestrator 'd=$(mktemp -d ~/feed/ex2.XXXXXX) && tar -C "$d" -xf - && echo "$d"')
   REPLACE_WITH_SSH aisec-orchestrator "cat > $D/collectors/netbox/contract.json" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
   REPLACE_WITH_SSH aisec-orchestrator "sudo bash $D/collectors/netbox/install-collector.sh && sudo bash $D/platform/change/install-change.sh"
   ```

   Expected: the observer key's public half, then the reset key's. Neither key is replaced.

6. Install the observer's copy on the lab VM, with the observer key from step 5.

   ```bash
   KEY=$(REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /etc/aisec/netbox/observe/id_ed25519.pub')
   L=$(tar -C collectors/netbox -cf - netbox_access.py aisec-observe aisec-observe-netbox install-lab-observer.sh |
     REPLACE_WITH_SSH aisec-lab 'l=$(mktemp -d ~/observer-install.XXXXXX) && tar -C "$l" -xf - && echo "$l"')
   REPLACE_WITH_SSH aisec-lab "sudo bash $L/install-lab-observer.sh '$KEY'"
   ```

   Expected: the four `sshd -T` lines: `authorizedkeysfile /etc/ssh/aisec-observe-keys`, `allowtcpforwarding no`, `permittty no`, and `forcecommand /usr/local/sbin/aisec-observe`.

7. Deploy the tool service's policy, which lists `ev-0004` and `ev-0005` for NetBox.

   ```bash
   T=$(tar -cf - platform/tool-service policies |
     REPLACE_WITH_SSH aisec-orchestrator 't=$(mktemp -d ~/feed/tool-service.XXXXXX) && tar -C "$t" -xf - && echo "$t"')
   REPLACE_WITH_SSH aisec-orchestrator "sudo bash $T/platform/tool-service/deploy.sh $T"
   ```

   Expected: the token's issuer, audience, and subject, two audit copier passes, `successfully rolled out`, and one pod.

8. Fetch the targets repository's `main` into delivery's mirror, in a just-in-time (JIT) egress window.

   ```bash
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 20'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo git -C /var/lib/aisec/delivery/targets.git -c http.proxy=http://10.45.0.4:3128 \
     fetch -q --prune --tags origin +refs/heads/main:refs/remotes/origin/main'
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo git -C /var/lib/aisec/delivery/targets.git rev-parse --short refs/remotes/origin/main'
   ```

   Expected: `open for 20 minutes`, `closed`, then the targets repository's `main`. The collect command judges the rules at this commit.

## The job

9. Collect a job's evidence.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo collect-netbox-evidence REPLACE_WITH_JOB'
   ```

   Expected: `ev-0001` to `ev-0005`, then `inventory-reader:within/within inventory-reader-control:within/within viewpoint-consumer:within/within viewpoint-staging:excess/excess`.

10. Run the job as in the [workflows runbook](workflows.md), with `target=netbox`, `max-turns=12`, `seconds=1200`, and the task in `collectors/netbox/task.txt`.

    Expected: `Succeeded`, with the comparison's outcome `match` and one proposal for `viewpoint-staging` that names priority 1120. A `Failed` with `stop: ...` is the verification gate refusing the answer: run another job.

11. Check the proposal.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo propose-netbox-fix REPLACE_WITH_JOB'
    ```

    Expected: `policy: allowed`, `rehearsal: passed` with the rules judged without the pair, every viewpoint `within`, and exit 0. The bundle, `proposal.json` and `pr-body.md`, is in `/var/lib/aisec/proposals/REPLACE_WITH_JOB/`.

## The fix

12. Copy the bundle to `REPLACE_WITH_BUNDLE` on the operator's machine. In a branch of the targets repository, apply it to the rules file, and read the plan.

    ```bash
    cd REPLACE_WITH_TARGETS_CHECKOUT
    git switch -c fix/exercise-2-REPLACE_WITH_JOB origin/main
    python3 -I REPLACE_WITH_PLATFORM_CHECKOUT/platform/change/edit_rules.py infra/targets/netbox-rules.json REPLACE_WITH_BUNDLE/proposal.json
    git diff --stat
    (cd infra/targets && source REPLACE_WITH_CRED_DIR/targets.env && terraform plan -lock=false)
    ```

    Expected: one file changed with only deletions, and `0 to add, 2 to change, 0 to destroy`: the pair removed, nothing else.

13. Commit with the commit signing key, push, and open the pull request with `pr-body.md` as its body, as in the [proposals runbook](proposals-and-delivery.md#propose), step 4. Then approve its head, step 5, and merge.

    Expected: "Approved commit" fails until the tag, then passes on its rerun. Every other check passes.

14. Plan and apply `main`, as in step 3.

    Expected: `0 to add, 2 to change, 0 to destroy`, the pair removed.

15. Connect from both viewpoints as in step 4, fetch the mirror as in step 8, and collect again as in step 9 with a new job ID.

    Expected: `10.50.0.36 open` and `10.50.1.4 timeout`. The mirror's `main` is the merge, and every account and viewpoint is `within/within`.

16. Run every check, as in the [validation page](../validation/README.md).

    Expected: every check passes. `N.25` and `Z.25` fail while the seed is live, and `N.26` while the mirror is behind `main`.
