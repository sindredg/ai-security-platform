# The staging copy on the lab VM: operator procedure

Status: Implemented on 2026-10-26. Run once, on the live system, 20:04 to 20:37 UTC, from four scripts with the same commands ([worklog](../worklogs/0006-remediation-pull-requests-and-delivery.md#the-rehearsal-copy)). The first install stopped at step 16 on a fault of its own output helper, and a second script ran steps 16 to 21.

Step 14 has since gained `AISEC_NETBOX_COPY=yes` ([ADR 0047](../decisions/0047-a-delivery-token-for-each-delivery.md)), and the undo and the steps after a rebuild were not run. Step 21's change was corrected on 2026-10-30, after the seed took the fix; the corrected step ran only inside the [interrupted staging test drill](containment-drills.md#a-staging-test-that-fails-after-its-apply), with the collector token aside.

This gives the lab VM a second interface in the `rehearsal` subnet, installs a second NetBox on it as the staging copy, seeds the copy, and gives the orchestrator a reset of it through one forced command ([ADR 0044](../decisions/0044-the-rehearsal-copy-is-a-second-netbox-on-the-lab-vm.md)). The copy is target side: a passed staging test is evidence, and the check after delivery is the proof.

Before this:

- The live NetBox holds the seed: the [NetBox runbook](netbox.md), steps 1 to 20.
- The collect command and the observer account are installed: the [evidence collection runbook](evidence-collection.md), steps 1 to 6.
- The orchestrator holds the NetBox image's archive at `/var/lib/aisec/target-images/netbox.tar`: the NetBox runbook, step 6.

## Inputs and access

| Input | Notes |
| --- | --- |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md) |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-worker`, `aisec-edge`, `aisec-netbox`, and `aisec-lab` |
| A checkout of this repository | Run from its root, for `platform/change/`, `collectors/netbox/`, and the checks |
| A checkout of the targets repository | `REPLACE_WITH_TARGETS_CHECKOUT`, for `infra/targets/` and `netbox/` |
| The targets root's and the platform root's credentials | As in the [network foundation runbook](network-foundation.md) |

## The interface

1. Plan the targets root, and read the plan before the apply.

   ```bash
   cd REPLACE_WITH_TARGETS_CHECKOUT/infra/targets
   source REPLACE_WITH_CRED_DIR/targets.env
   terraform plan -out=REPLACE_WITH_PLAN
   ```

   Expected: `Plan: 1 to add, 2 to change, 0 to destroy.` The lab VM is updated in place, with its second interface in `network_interface_ids`, and the `rehearsal` group gains `allow-netbox-from-orchestrator`. A plan that replaces the lab VM is a stop: a rebuilt lab VM loses the observer account, the consumer tokens, and its pinned host key.

2. Apply the plan.

   ```bash
   terraform apply REPLACE_WITH_PLAN
   ```

   Expected: `Apply complete! Resources: 1 added, 2 changed, 0 destroyed.` The lab VM stops and starts once, in about a minute.

3. Plan and apply the platform root the same way.

   Expected: one change, the orchestrator's group gains `allow-rehearsal-copy-to-targets` to `10.50.1.4/32` on 8443. Then `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`

4. Read the lab VM's interfaces, and try the copy's port from the orchestrator.

   ```bash
   REPLACE_WITH_SSH aisec-lab 'ip -br -4 addr; ip rule'
   REPLACE_WITH_SSH aisec-orchestrator 'timeout 5 bash -c "</dev/tcp/10.50.1.4/8443"; echo $?'
   ```

   Expected: `eth1` with `10.50.1.4/27`, and no rule for that address. The probe times out, exit `124`: the reply leaves through `eth0` with the copy's address, and Azure drops it.

## The routing

5. Write the netplan file the targets template writes at a first boot, with a guard that removes it after four minutes unless a new login confirms first. Then apply it.

   ```bash
   REPLACE_WITH_SSH aisec-lab 'sudo tee /etc/netplan/60-aisec-rehearsal.yaml >/dev/null' <<'NETPLAN'
   network:
     version: 2
     ethernets:
       eth1:
         routes:
           - to: 10.50.1.0/27
             scope: link
             table: 101
           - to: 0.0.0.0/0
             via: 10.50.1.1
             table: 101
         routing-policy:
           - from: 10.50.1.4
             table: 101
   NETPLAN
   REPLACE_WITH_SSH aisec-lab 'sudo chmod 600 /etc/netplan/60-aisec-rehearsal.yaml && sudo netplan generate'
   REPLACE_WITH_SSH aisec-lab "sudo systemd-run --quiet --unit=aisec-netplan-guard --on-active=240 /bin/sh -c '[ -e /run/aisec-netplan-ok ] || { rm -f /etc/netplan/60-aisec-rehearsal.yaml; netplan apply; }'"
   REPLACE_WITH_SSH aisec-lab 'sudo netplan apply'
   ```

   Expected: no output.

6. Confirm with a new login, then read the rule and try the port again.

   ```bash
   REPLACE_WITH_SSH aisec-lab 'sudo touch /run/aisec-netplan-ok && sudo systemctl stop aisec-netplan-guard.timer; ip rule; ip route show table 101'
   REPLACE_WITH_SSH aisec-orchestrator 'timeout 5 bash -c "</dev/tcp/10.50.1.4/8443"; echo $?'
   ```

   Expected: `from 10.50.1.4 lookup 101`, and table 101 with `10.50.1.0/27` and `default via 10.50.1.1`. The probe is refused at once, exit `1`: the reply comes back, and nothing listens yet.

## The packages

7. Give the lab VM NetBox's packages, and run its update.

   ```bash
   echo "podman postgresql-18 valkey-server" | REPLACE_WITH_SSH aisec-lab 'sudo tee /etc/aisec/target-packages >/dev/null'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo aisec-target-update-run lab'
   ```

   Expected: `start target=lab`, the three packages installed from the Azure mirror, PostgreSQL's new cluster `18/main`, then `end target=lab status=0`. Reboot when it prints `reboot_required=yes`, as in the [target VMs runbook](targets.md), step 12.

## NetBox on the lab VM

8. Copy NetBox's files and the image archive to the lab VM.

   ```bash
   tar -C REPLACE_WITH_TARGETS_CHECKOUT -cf - netbox | REPLACE_WITH_SSH aisec-lab 'mkdir -p ~/netbox-install && tar -C ~/netbox-install -xf -'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /var/lib/aisec/target-images/netbox.tar' | REPLACE_WITH_SSH aisec-lab 'cat > ~/netbox.tar'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo sha256sum /var/lib/aisec/target-images/netbox.tar'
   REPLACE_WITH_SSH aisec-lab 'sha256sum ~/netbox.tar'
   ```

   Expected: the same SHA-256 on both. The copy took about nine minutes.

9. Install the copy, with its address, its one listener, and its own settings directory.

   ```bash
   REPLACE_WITH_SSH aisec-lab 'sudo env AISEC_NETBOX_ADDRESS=10.50.1.4 AISEC_NETBOX_LISTEN=10.50.1.4 AISEC_NETBOX_CONF=/etc/aisec/netbox-rehearsal ~/netbox-install/netbox/install-netbox.sh ~/netbox.tar'
   ```

   Expected: `ok    image` with the pin, four `made  secret` lines, `made  TLS key and certificate`, PostgreSQL, Valkey, `units started`, a `waiting` line each minute while the first start migrates, then `login_page=200`. Both running images are the pin, and the certificate names `IP Address:10.50.1.4`.

10. Read where the copy listens, and the memory left.

    ```bash
    REPLACE_WITH_SSH aisec-lab 'ss -Hltn "sport = :8443"; free -m'
    ```

    Expected: `10.50.1.4:8443` only, and at least 1 GB available.

11. Pin the copy's certificate on the orchestrator, and reach the copy with it.

    ```bash
    REPLACE_WITH_SSH aisec-lab 'cat /etc/aisec/netbox-rehearsal/tls.crt' |
      REPLACE_WITH_SSH aisec-orchestrator 'sudo install -d -m 755 /etc/aisec/netbox-rehearsal && sudo tee /etc/aisec/netbox-rehearsal/tls.crt >/dev/null'
    REPLACE_WITH_SSH aisec-orchestrator "curl -s -o /dev/null -w '%{http_code}\n' --noproxy '*' --cacert /etc/aisec/netbox-rehearsal/tls.crt \
      --resolve netbox.aisec.internal:8443:10.50.1.4 https://netbox.aisec.internal:8443/login/"
    ```

    Expected: `200`.

## The seed

12. Read the address the copy sees the lab VM's own reads come from, with a probe token limited to an address no host has.

    ```bash
    REPLACE_WITH_SSH aisec-lab 'sudo bash -s' <<'PROBE'
    token=$(mktemp -p /run)
    ~/netbox-install/netbox/make-netbox-token.sh probe > "$token" 2>/dev/null
    curl -s --max-time 8 --cacert /etc/aisec/netbox-rehearsal/tls.crt \
      -H @<(printf "Authorization: Bearer %s\n" "$(cat "$token")") https://10.50.1.4:8443/api/status/
    rm -f "$token"
    PROBE
    ```

    Expected: a refusal that names `Source IP 10.50.1.4 is not permitted`. That address is `REPLACE_WITH_ADDRESS` below.

13. Make the seeding token, into a root-only file on the orchestrator.

    ```bash
    REPLACE_WITH_SSH aisec-lab 'sudo ~/netbox-install/netbox/make-netbox-token.sh seed 2>/dev/null' |
      REPLACE_WITH_SSH aisec-orchestrator "sudo sh -c 'umask 077; cat > /etc/aisec/netbox-rehearsal/seed-token'"
    ```

    Expected: no output, and `root 600 58` from `stat` on the file.

14. Seed the copy into a directory in memory, with the consumer's tokens limited to `REPLACE_WITH_ADDRESS`. `AISEC_NETBOX_COPY=yes` makes the delivery account's token, which only the copy keeps.

    ```bash
    tar -C REPLACE_WITH_TARGETS_CHECKOUT/netbox -cf - seed.py seed.json | REPLACE_WITH_SSH aisec-orchestrator 'mkdir -p ~/feed/rehearsal-seed && tar -C ~/feed/rehearsal-seed -xf -'
    RUN=$(REPLACE_WITH_SSH aisec-orchestrator 'sudo mktemp -d -p /run aisec-rehearsal-tokens.XXXXXX')
    REPLACE_WITH_SSH aisec-orchestrator "sudo env AISEC_NETBOX_URL=https://10.50.1.4:8443 AISEC_NETBOX_CERT=/etc/aisec/netbox-rehearsal/tls.crt \
      AISEC_SEED_TOKEN=/etc/aisec/netbox-rehearsal/seed-token AISEC_CONSUMER_ADDRESS=REPLACE_WITH_ADDRESS/32 AISEC_NETBOX_COPY=yes \
      python3 -I ~/feed/rehearsal-seed/seed.py ~/feed/rehearsal-seed/seed.json $RUN"
    ```

    Expected: 36 `made` lines, then a `made  token` line for each of the four seeded accounts.

15. Put each token on its host, then remove the run directory and the seeding token.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "sudo install -d -m 700 /etc/aisec/netbox-rehearsal/tokens && sudo install -m 600 $RUN/aisec-collector $RUN/aisec-deliver /etc/aisec/netbox-rehearsal/tokens/"
    REPLACE_WITH_SSH aisec-lab 'sudo install -d -m 700 /etc/aisec/netbox-rehearsal/tokens'
    for account in inventory-reader inventory-reader-control; do
      REPLACE_WITH_SSH aisec-orchestrator "sudo cat $RUN/$account" |
        REPLACE_WITH_SSH aisec-lab "sudo sh -c 'umask 077; cat > /etc/aisec/netbox-rehearsal/tokens/$account'"
    done
    REPLACE_WITH_SSH aisec-orchestrator "sudo rm -r $RUN /etc/aisec/netbox-rehearsal/seed-token"
    ```

    Expected: no output. `root 700` for both token directories, and `root 600` for each token.

## The collector and the observer

16. Install the collector on the orchestrator and the observer on the lab VM again, from this checkout: steps 1 and 3 of the [evidence collection runbook](evidence-collection.md), with the same observer key. Then read the copy's verdicts by both methods.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo env AISEC_NETBOX_URL=https://10.50.1.4:8443 AISEC_NETBOX_CERT=/etc/aisec/netbox-rehearsal/tls.crt \
      AISEC_NETBOX_TOKENS=/etc/aisec/netbox-rehearsal/tokens python3 -I /usr/local/lib/aisec/netbox_access.py configured --summary' \
      < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
    REPLACE_WITH_SSH aisec-orchestrator 'sudo ssh -F none -i /etc/aisec/netbox/observe/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes \
      -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/aisec/netbox/observe/known_hosts -T aisec-observe@10.50.0.36 rehearsal' \
      < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
    ```

    Expected: `inventory-reader:within inventory-reader-control:within` from the first, and a report with the same verdicts from the second. The seed gave `excess` for `inventory-reader` until the fix of 2026-10-27. The installer's last lines name `forcecommand /usr/local/sbin/aisec-observe`.

## The dump and the reset

17. Take the seed dump on the lab VM, and record its SHA-256 on the orchestrator.

    ```bash
    REPLACE_WITH_SSH aisec-lab "sudo install -d -m 700 /var/lib/aisec/rehearsal && sudo sh -c 'umask 077; runuser -u postgres -- pg_dump -Fc netbox > /var/lib/aisec/rehearsal/seed.dump'"
    SHA=$(REPLACE_WITH_SSH aisec-lab 'sudo sha256sum /var/lib/aisec/rehearsal/seed.dump' | cut -d " " -f 1)
    echo "$SHA" | REPLACE_WITH_SSH aisec-orchestrator "sudo install -d -m 700 /etc/aisec/netbox-rehearsal/reset && sudo sh -c 'umask 022; cat > /etc/aisec/netbox-rehearsal/reset/seed.sha256'"
    ```

    Expected: no output. The dump is root 600, about 2.5 MB.

18. Install the change commands on the orchestrator. The script makes the reset key once and prints its public half.

    ```bash
    tar -cf - platform/change collectors/netbox | REPLACE_WITH_SSH aisec-orchestrator 'mkdir -p ~/feed/change && tar -C ~/feed/change -xf -'
    KEY=$(REPLACE_WITH_SSH aisec-orchestrator 'sudo bash ~/feed/change/platform/change/install-change.sh')
    echo "$KEY"
    ```

    Expected: one line, `ssh-ed25519 REPLACE_WITH_KEY aisec-rehearsal-reset`.

19. Install the reset account on the lab VM with that key.

    ```bash
    tar -C platform/change -cf - aisec-rehearsal-reset install-rehearsal-reset.sh | REPLACE_WITH_SSH aisec-lab 'mkdir -p ~/reset && tar -C ~/reset -xf -'
    REPLACE_WITH_SSH aisec-lab "sudo bash ~/reset/install-rehearsal-reset.sh '$KEY'"
    ```

    Expected: `parsed OK`, then `forcecommand sudo -n /usr/local/sbin/aisec-rehearsal-reset`, `allowtcpforwarding no`, and `permittty no`.

20. Reset the copy once through the account, asking it for another command.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo ssh -F none -i /etc/aisec/netbox-rehearsal/reset/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes \
      -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/aisec/netbox/observe/known_hosts -T aisec-rehearse@10.50.0.36 id' </dev/null
    ```

    Expected: the forced command runs instead, and its last line is the SHA-256 step 17 recorded, after about a minute.

21. Run a staging test once with the installed library: a change that removes `inventory-reader` from its one permission.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "sudo python3 -I -c 'import json, sys
    sys.path.insert(0, \"/usr/local/lib/aisec\")
    import rehearse
    change = {\"account\": \"inventory-reader\", \"permission_id\": 0, \"permission\": \"inventory-reader: tenant-a inventory\"}
    print(json.dumps(rehearse.rehearse([change], json.load(open(\"/etc/aisec/netbox/contract.json\")))))'"
    ```

    Expected: `"passed": false`, the reset's SHA-256 twice, one change on the copy's own ID for `inventory-reader: tenant-a inventory`, and `inventory-reader` `missing` by both methods: the seed holds the fix of 2026-10-27, so the removal leaves the account short. The copy is reset again after the halves, whatever happened between the two resets. The verdicts are reasoned from the seed, not observed: the corrected step ran only inside the drill, where the halves did not complete.

## Checks

22. Run every check, with the targets checkout named.

    ```bash
    export AISEC_TARGETS=REPLACE_WITH_TARGETS_CHECKOUT
    validation/platform-checks.sh
    ```

    Expected: `Q.1` to `Q.5` pass, with `C.3`, `Z.25`, `Z.29`, and `Z.30` ([targets](../validation/targets.md#the-staging-copy)).

## Undo

Not run.

On the lab VM: `systemctl disable --now netbox netbox-worker`, remove the two units from `/etc/containers/systemd`, `runuser -u postgres -- dropdb netbox`, remove the six `netbox_*` Podman secrets, `/etc/aisec/netbox-rehearsal`, `/var/lib/aisec/rehearsal`, the netplan file, and the `aisec-rehearse` account with its key file, sudo line, and sshd drop-in. On the orchestrator: remove `/etc/aisec/netbox-rehearsal`. Then revert the two roots' changes and apply them.

## After a rebuild of the lab VM

Not run.

A rebuilt lab VM gets the netplan file and the packages from its first boot, but cloud-init writes the file after it has set up the network, so nothing applies it until a reboot. Run steps 5 to 21 again: step 5 writes the same file and applies it. Run them after the evidence collection runbook's steps 3 to 6 for the observer.
