# Target VMs: operator procedure

Status: Implemented on 2026-10-24. Built once, on the live system, 15:24 to 16:51 UTC, and rebuilt once, 17:39 to 18:12 UTC. Results are in the [milestone 4 worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-target-vms) and its [update run](../worklogs/0005-netbox-target-and-exercise-1.md#the-update-run) section. The key was made by hand on the first build, before the install script made it: step 2 has not run in this form. Steps 6 and 10 to 12 ran from a script with the same commands, step 12 with no reboot needed. Steps 5, 7, and 9 ran as separate read-only commands. Step 8 ran in its earlier form, without the `URIs` line, at 17:01 UTC. The first apply failed on an image version that `az vm image list` named and the region did not serve. Step 1 checks for that now, and has not run in this form.

This builds the NetBox VM and the lab VM from the [targets repository](https://github.com/sindredg/ai-security-platform-test), installs the orchestrator's update run, and runs it once on each ([ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)). NetBox itself and its data come later.

The target network must exist: the [network foundation runbook](network-foundation.md) builds it. So must the platform side of the targets' package port: the [edge runbook](edge-vm.md#the-targets-package-port), steps 14 to 17.

## Inputs and access

| Input | Notes |
| --- | --- |
| The target deployment identity | `REPLACE_WITH_CRED_DIR/targets.env`, as in the [network foundation runbook](network-foundation.md) |
| `az`, signed in as the operator | Read-only queries and the serial log |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md) |
| A checkout of the targets repository | `$TARGETS` below is its `infra/targets` directory, as an absolute path |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-edge`, `aisec-netbox` (`10.50.0.4`), and `aisec-lab` (`10.50.0.36`) |
| A checkout of this repository | Run from its root, for `platform/target-update` and the checks |

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

2. Copy the update run to the orchestrator, and install it. With no argument the install makes the update key, if there is none, and prints its public half.

   ```bash
   tar -cf - platform/target-update | REPLACE_WITH_SSH aisec-orchestrator \
     'rm -rf ~/feed/target-update && mkdir -p ~/feed/target-update && tar -C ~/feed/target-update -xf -'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/target-update/platform/target-update/install-target-update.sh' \
     > REPLACE_WITH_CRED_DIR/target-update.pub
   ssh-keygen -l -f REPLACE_WITH_CRED_DIR/target-update.pub
   REPLACE_WITH_SSH aisec-orchestrator 'sudo stat -c "%n %U %a" /etc/aisec/target-update /etc/aisec/target-update/id_ed25519 /usr/local/sbin/aisec-target-update-run'
   ```

   Expected: an ED25519 fingerprint with the comment `aisec-target-update`, then `root 700`, `root 600`, and `root 700`. On a rebuild of the targets alone, the key stays and the fingerprint is the old one.

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

5. Take each VM's host key from its serial log, and compare it with the one it offers through the router. The serial log has the key about two minutes after the apply returns.

   ```bash
   for vm in netbox lab; do
     az vm boot-diagnostics get-boot-log -g rg-aisec-targets -n vm-aisec-$vm -o tsv \
       | grep -a -o "SHA256:[A-Za-z0-9+/]* root@aisec-$vm (ED25519)" | sort -u
   done
   ssh-keyscan -T 10 -t ed25519 10.50.0.4 10.50.0.36 2>/dev/null | grep -v '^#' > REPLACE_WITH_KNOWN_HOSTS_FILE.targets
   ssh-keygen -lf REPLACE_WITH_KNOWN_HOSTS_FILE.targets
   ```

   Expected: each VM's fingerprint twice, once from its log and once from the scan. Add both lines to the known hosts file `REPLACE_WITH_SSH` uses.

6. Pin both host keys for the update run.

   ```bash
   key() { awk -v a="$1" '$1 == a {print $2, $3}' REPLACE_WITH_KNOWN_HOSTS_FILE.targets; }
   REPLACE_WITH_SSH aisec-orchestrator "sudo ~/feed/target-update/platform/target-update/install-target-update.sh '$(key 10.50.0.4)' '$(key 10.50.0.36)'"
   REPLACE_WITH_SSH aisec-orchestrator 'sudo cut -c1-40 /etc/aisec/target-update/known_hosts'
   ```

   Expected: the public key line from step 2 again, then one line for `10.50.0.4` and one for `10.50.0.36`.

## Confirm

7. Log in through the router, and read the address each target sees.

   ```bash
   for h in aisec-netbox aisec-lab; do REPLACE_WITH_SSH $h 'echo "${SSH_CLIENT%% *}"'; done
   ```

   Expected: `10.45.0.36` twice, the router's address. A refused login means the certificate, its `source-address`, or the known hosts file.

8. Confirm first boot on each VM.

   ```bash
   for h in aisec-netbox aisec-lab; do REPLACE_WITH_SSH $h 'sudo stat -c %U /var/lib/aisec-first-boot.done
     systemctl --failed --no-legend | wc -l
     sudo grep -c . /home/aisec/.ssh/authorized_keys
     sudo -l -U aisec-update | tail -n 1
     systemctl is-enabled apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service | tr "\n" " "; echo
     grep -h "^URIs" /etc/apt/sources.list.d/*.sources | sort -u
     sudo apt-get update -q 2>&1 | tail -n 1'; done
   ```

   Expected, for each VM: `root`, `0`, `0`, `(root) NOPASSWD: /usr/local/sbin/aisec-target-update ""`, `masked masked masked`, `URIs: http://azure.archive.ubuntu.com/ubuntu/`, and `W: Some index files failed to download. They have been ignored, or old ones used instead.`: nothing listens on `127.0.0.1:3129` between update runs, so apt fails at once. Another `URIs` line means first boot did not get the mirror ([troubleshooting 16](../troubleshooting/16-targets-apt-sources-fall-back-without-dns.md)).

9. Confirm the orchestrator reaches both VMs on 22.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'for t in 10.50.0.4 10.50.0.36; do
     timeout 5 bash -c "</dev/tcp/$t/22" && echo "$t open"; done'
   ```

   Expected: `10.50.0.4 open` and `10.50.0.36 open`.

## Update run

Run at provisioning, at the start of each exercise, before each milestone's checks, and when `U.14` or `U.15` fails ([ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)).

10. Run the update on each target, from the orchestrator.

    ```bash
    since=$(date +%s)
    REPLACE_WITH_SSH aisec-orchestrator 'sudo aisec-target-update-run netbox'
    REPLACE_WITH_SSH aisec-orchestrator 'sudo aisec-target-update-run lab'
    ```

    Expected, for each: `start target=...`, apt reading `http://azure.archive.ubuntu.com/ubuntu` with no `Err:` line, then `security_updates_pending=0`, `reboot_required=yes` or `no`, and `end target=... status=0`. On the first run the NetBox VM installs `podman`, `postgresql-18`, and `valkey-server`. An `Err:` line with `403` is a host the target port refuses.

11. Read the run in the orchestrator's journal and in Squid's log.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo journalctl -t aisec-target-update --since -30min --no-pager -o cat'
    REPLACE_WITH_SSH aisec-edge "sudo awk -v since=$since '\$1 >= since && \$3 == \"10.40.0.4\" {print \$4, \$6, \$7}' /var/log/squid/access.log |
      sed 's#\(http://[^/]*\)/[^ ]*#\1#' | sort | uniq -c"
    ```

    Expected: a start and an end line per target. In Squid's log, only `GET` to `http://azure.archive.ubuntu.com`, with `TCP_MISS/200` or `TCP_MISS/304`, and no `TCP_DENIED`. A check run in the same minutes adds its own refusals.

12. Reboot each target whose run printed `reboot_required=yes`, and wait for its login.

    ```bash
    REPLACE_WITH_SSH aisec-netbox 'sudo systemctl reboot'
    REPLACE_WITH_SSH aisec-netbox 'uptime -s; test -e /run/reboot-required && echo reboot-required || echo none'
    ```

    Expected: the login works again within three minutes, with a new boot time and `none`. The same for `aisec-lab`.

## Checks

13. Run every check, from this repository's checkout, with the targets checkout named.

    ```bash
    export AISEC_TARGETS=REPLACE_WITH_TARGETS_CHECKOUT
    validation/platform-checks.sh
    ```

    Expected: every check passes, `VN`, `VL`, `HN`, `HL`, `E.15` to `E.18`, `C.11`, `U.14`, `U.15`, `Z.27`, and `Z.28` among them ([targets](../validation/targets.md)). A `FAIL` on `VN.9` or `VL.9` with `AISEC_TARGETS not given` means the variable is missing.

14. Plan again.

    ```bash
    cd "$TARGETS"
    source REPLACE_WITH_CRED_DIR/targets.env
    terraform plan -detailed-exitcode
    ```

    Expected: `No changes. Your infrastructure matches the configuration.` and exit `0`.

## Rebuild

The VMs ignore changes to their custom data, so a changed first-boot template takes effect only on a new VM. Run on 2026-10-24 for both VMs at once.

1. Run `terraform apply` in `$TARGETS` with `-replace='azurerm_linux_virtual_machine.vm["netbox"]'`, `-replace='azurerm_linux_virtual_machine.vm["lab"]'`, or both, after reading the plan. Expected: one add and one destroy per VM, and nothing else.
2. Remove each rebuilt VM's line from the known hosts file. Then run steps 5 to 13.
