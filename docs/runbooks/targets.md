# Target VMs: operator procedure

Status: Implemented on 2026-10-24. Run once, on the live system, 15:24 to 16:51 UTC. Results are in the [milestone 4 worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-target-vms). Step 2 ran from a script with the same commands, and steps 6 and 8 as separate read-only commands. They have not run in this form. Step 7 ran in this form at 17:01 UTC. The first apply failed on an image version that `az vm image list` named and the region did not serve. Step 1 checks for that now, and has not run in this form.

This builds the NetBox VM and the lab VM from the [targets repository](https://github.com/sindredg/ai-security-platform-test), and makes the orchestrator's key for update runs ([ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)). NetBox itself, its data, and the update run come later.

The target network must exist: the [network foundation runbook](network-foundation.md) builds it. So must the platform side of the targets' package port: the [edge runbook](edge-vm.md#the-targets-package-port), steps 14 to 17.

## Inputs and access

| Input | Notes |
| --- | --- |
| The target deployment identity | `REPLACE_WITH_CRED_DIR/targets.env`, as in the [network foundation runbook](network-foundation.md) |
| `az`, signed in as the operator | Read-only queries and the serial log |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md) |
| A checkout of the targets repository | `$TARGETS` below is its `infra/targets` directory, as an absolute path |
| A checkout of this repository | For the checks |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-netbox` (`10.50.0.4`), and `aisec-lab` (`10.50.0.36`) |

## Before the build

1. Check that the size is offered in Poland Central, zone 3, that the region has room, and which image version the region serves.

   ```bash
   az vm list-skus -l polandcentral --size Standard_B2as_v2 --all \
     --query "[].{zones:locationInfo[0].zones, restrictions:restrictions}" -o json
   az vm list-usage -l polandcentral --query "[?name.value=='cores'].{used:currentValue, limit:limit}" -o table
   az vm image list --publisher Canonical --offer ubuntu-26_04-lts --sku server --all -l polandcentral \
     --query "[?offer=='ubuntu-26_04-lts' && sku=='server'].version" -o tsv | sort -V | tail -n 3
   az vm image show -l polandcentral --urn Canonical:ubuntu-26_04-lts:server:REPLACE_WITH_VERSION --query name -o tsv
   ```

   Expected: zone `3` listed with no restriction for it, and 4 cores free. `list-skus` is slow, minutes. Run `image show` for the newest listed version, then the next, until one prints its name. That one, or `image_version` in `$TARGETS/variables.tf` if it is newer, is the version to use. A version `image show` does not find fails the apply with `PlatformImageNotFound`.

## The update key

2. Make the key on the orchestrator, and copy its public half to the workstation.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'set -e
     d=/etc/aisec/target-update
     sudo install -d -o root -g root -m 0700 "$d"
     sudo ssh-keygen -q -t ed25519 -N "" -C aisec-target-update -f "$d/id_ed25519"
     sudo stat -c "%n %U %G %a" "$d" "$d/id_ed25519" "$d/id_ed25519.pub"
     sudo ssh-keygen -l -f "$d/id_ed25519.pub"'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /etc/aisec/target-update/id_ed25519.pub' > REPLACE_WITH_CRED_DIR/target-update.pub
   ssh-keygen -l -f REPLACE_WITH_CRED_DIR/target-update.pub
   ```

   Expected: `root root 700` for the directory, `600` for the private half, `644` for the public half, and the same ED25519 fingerprint with the comment `aisec-target-update` twice. On a rebuild of the targets alone, the key stays: skip this step.

## Build

3. Fill in the variables. Copy `$TARGETS/terraform.tfvars.example` to `terraform.tfvars`, which Git ignores, and replace each placeholder as its comment says. `update_public_key` is the line from step 2. Set `image_version` if step 1 found a newer one.

   Expected: no `REPLACE_WITH` left in `terraform.tfvars`.

4. Apply, after reading the plan.

   ```bash
   cd "$TARGETS"
   source REPLACE_WITH_CRED_DIR/targets.env
   terraform apply
   ```

   Expected: `4 to add, 0 to change, 0 to destroy`: `nic-aisec-netbox`, `nic-aisec-lab`, `vm-aisec-netbox`, and `vm-aisec-lab`. Nothing in the network changes. Then `Apply complete! Resources: 4 added, 0 changed, 0 destroyed.`

5. Take each VM's host key from its serial log, and compare it with the one it offers through the router. First boot takes about a minute after the apply returns.

   ```bash
   for vm in netbox lab; do
     az vm boot-diagnostics get-boot-log -g rg-aisec-targets -n vm-aisec-$vm -o tsv \
       | grep -a -o "SHA256:[A-Za-z0-9+/]* root@aisec-$vm (ED25519)" | sort -u
   done
   ssh-keyscan -T 10 -t ed25519 10.50.0.4 10.50.0.36 > REPLACE_WITH_KNOWN_HOSTS_FILE.targets
   ssh-keygen -lf REPLACE_WITH_KNOWN_HOSTS_FILE.targets
   ```

   Expected: each VM's fingerprint twice, once from its log and once from the scan. Add both lines to the known hosts file `REPLACE_WITH_SSH` uses.

## Confirm

6. Log in through the router, and read the address each target sees.

   ```bash
   for h in aisec-netbox aisec-lab; do REPLACE_WITH_SSH $h 'echo "${SSH_CLIENT%% *}"'; done
   ```

   Expected: `10.45.0.36` twice, the router's address. A refused login means the certificate, its `source-address`, or the known hosts file.

7. Confirm first boot on each VM.

   ```bash
   for h in aisec-netbox aisec-lab; do REPLACE_WITH_SSH $h 'sudo stat -c %U /var/lib/aisec-first-boot.done
     systemctl --failed --no-legend | wc -l
     sudo grep -c . /home/aisec/.ssh/authorized_keys
     sudo -l -U aisec-update | tail -n 1
     systemctl is-enabled apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service | tr "\n" " "; echo
     sudo apt-get update -q 2>&1 | tail -n 1'; done
   ```

   Expected, for each VM: `root`, `0`, `0`, `(root) NOPASSWD: /usr/local/sbin/aisec-target-update ""`, `masked masked masked`, and `W: Some index files failed to download. They have been ignored, or old ones used instead.`: nothing listens on `127.0.0.1:3129` between update runs, so apt fails at once.

8. Confirm the orchestrator reaches both VMs on 22.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'for t in 10.50.0.4 10.50.0.36; do
     timeout 5 bash -c "</dev/tcp/$t/22" && echo "$t open"; done'
   ```

   Expected: `10.50.0.4 open` and `10.50.0.36 open`.

9. Run every check, from this repository's checkout, with the targets checkout named.

   ```bash
   export AISEC_TARGETS=REPLACE_WITH_TARGETS_CHECKOUT
   validation/platform-checks.sh
   ```

   Expected: every check passes, `VN`, `VL`, `HN`, `HL`, `E.15`, `E.16`, `C.11`, `Z.27`, and `Z.28` among them ([targets](../validation/targets.md)). A `FAIL` on `VN.9` or `VL.9` with `AISEC_TARGETS not given` means the variable is missing.

10. Plan again.

    ```bash
    cd "$TARGETS"
    source REPLACE_WITH_CRED_DIR/targets.env
    terraform plan -detailed-exitcode
    ```

    Expected: `No changes. Your infrastructure matches the configuration.` and exit `0`.

## Rebuild

The VMs ignore changes to their custom data, so a changed first-boot template takes effect only on a new VM. Not run.

1. Run `terraform apply -replace='azurerm_linux_virtual_machine.vm["netbox"]'` in `$TARGETS`, or the same for `lab`, after reading the plan. Expected: `1 to add, 0 to change, 1 to destroy`.
2. Remove the VM's old line from the known hosts file, then run steps 5 to 9 for it.
