# NetBox on its VM: operator procedure

Status: Implemented on 2026-10-24. Run once, on the live system, 19:48 to 20:01 UTC, from a script with the same commands ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#netbox-on-its-vm)). The first run stopped at step 8: the install script waited five minutes for the first start, and NetBox took about six. The wait is 30 minutes now. Step 8 then ran a second time, which kept every secret and the key, and steps 9 to 12 ran after it. The checks ran on their own. The seed, steps 13 to 19, ran once on 2026-10-25, 06:30 to 07:07 UTC, from a script with the same commands, after steps 7 and 8 again for the setting of [ADR 0039](../decisions/0039-netbox-takes-a-clients-address-from-the-connection.md). It stopped three times before it ran to its end: the token script not executable, Granian on a dual-stack socket ([troubleshooting 17](../troubleshooting/17-netbox-sees-ipv4-clients-as-mapped-ipv6.md)), and NetBox's password rules ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-run)). Two commands differ from the script's. It ran the token script through `bash`, because the file was not executable in that checkout. Its `stat` in step 17 expanded the glob as the login account, which cannot read the directory, so the modes were read with the commands below after the run.

This installs NetBox and its background worker on the NetBox VM from the image pinned in the [targets repository](https://github.com/sindredg/ai-security-platform-test)'s `netbox/image.env`, with PostgreSQL and Valkey on the VM ([ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)). The VM makes its own secrets and its TLS key, and the orchestrator pins the certificate ([ADR 0038](../decisions/0038-netboxs-tls-key-made-on-the-netbox-vm.md)). NetBox takes a client's address from the connection only ([ADR 0039](../decisions/0039-netbox-takes-a-clients-address-from-the-connection.md)). Steps 13 to 19 seed exercise 1's inventory, accounts, and tokens, and put each token on its host ([ADR 0037](../decisions/0037-an-unscoped-copy-of-the-consumers-permission.md)).

The NetBox VM must exist and have had one update run, which installs Podman, PostgreSQL, and Valkey: the [target VMs runbook](targets.md), steps 1 to 12.

## Inputs and access

| Input | Notes |
| --- | --- |
| The platform and target deployment identities | `REPLACE_WITH_CRED_DIR/platform.env` and `targets.env`, for the rules |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md) |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-edge`, `aisec-netbox`, and `aisec-lab` |
| A checkout of this repository | Run from its root, for `platform/target-images` and the checks |
| A checkout of the targets repository | `REPLACE_WITH_TARGETS_CHECKOUT`, for `netbox/` and `infra/targets` |

## The rules

1. Plan and apply the platform root. It adds `allow-netbox-to-targets` to the orchestrator's group: TCP 8443 from `10.40.0.4/32` to `10.50.0.4/32`.

   ```bash
   cd infra/platform
   source REPLACE_WITH_CRED_DIR/platform.env
   terraform plan -out=netbox.tfplan
   terraform apply netbox.tfplan
   ```

   Expected: `0 to add, 1 to change, 0 to destroy`, one rule added and none removed. Then `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`

2. Plan and apply the targets root. It adds `allow-netbox-from-orchestrator` and `allow-netbox-from-consumer` to the NetBox group, and `allow-netbox-to-netbox` to the consumer group.

   ```bash
   cd REPLACE_WITH_TARGETS_CHECKOUT/infra/targets
   source REPLACE_WITH_CRED_DIR/targets.env
   terraform plan -out=netbox.tfplan
   terraform apply netbox.tfplan
   ```

   Expected: `0 to add, 2 to change, 0 to destroy`, three rules added and none removed. Then `0 added, 2 changed, 0 destroyed`.

## The image

3. Copy the fetch script and the pin to the orchestrator.

   ```bash
   tar -cf - platform/target-images | REPLACE_WITH_SSH aisec-orchestrator \
     'rm -rf ~/feed/target-images && mkdir -p ~/feed/target-images && tar -C ~/feed/target-images -xf -'
   REPLACE_WITH_SSH aisec-orchestrator 'cat > ~/feed/target-images/image.env' < REPLACE_WITH_TARGETS_CHECKOUT/netbox/image.env
   REPLACE_WITH_SSH aisec-orchestrator 'sha256sum ~/feed/target-images/image.env'
   sha256sum REPLACE_WITH_TARGETS_CHECKOUT/netbox/image.env
   ```

   Expected: the same SHA-256 twice.

4. Open a fetch window, and note the time for step 6.

   ```bash
   since=$(date +%s)
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 30'
   ```

   Expected: `open for 30 minutes, until ...`.

5. Pull, export, and check the image on the orchestrator. Then close the window.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/target-images/platform/target-images/fetch-netbox-image.sh ~/feed/target-images/image.env /var/lib/aisec/target-images/netbox.tar'
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close'
   ```

   Expected: `ok    pulled` with the index digest, `ok    archive: 18 layers, config sha256:...` with `NETBOX_IMAGE_ID`, and the archive's SHA-256. Then `closed`. The archive is about 262 MB. A digest that does not match stops the script and removes the archive.

6. Read the window's tunnels in Squid's log.

   ```bash
   REPLACE_WITH_SSH aisec-edge "sudo awk -v since=$since '\$1 >= since && \$3 == \"10.40.0.4\" {print \$4, \$6, \$7}' /var/log/squid/access.log | sort | uniq -c"
   ```

   Expected: `TCP_TUNNEL/200 CONNECT` to `ghcr.io:443` and `pkg-containers.githubusercontent.com:443` only, and no `TCP_DENIED`.

7. Copy NetBox's directory and the archive to the NetBox VM, through this session.

   ```bash
   tar -C REPLACE_WITH_TARGETS_CHECKOUT -cf - netbox | REPLACE_WITH_SSH aisec-netbox \
     'rm -rf ~/netbox-install && mkdir ~/netbox-install && tar -C ~/netbox-install -xf -'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /var/lib/aisec/target-images/netbox.tar' | REPLACE_WITH_SSH aisec-netbox 'cat > ~/netbox.tar'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo sha256sum /var/lib/aisec/target-images/netbox.tar'
   REPLACE_WITH_SSH aisec-netbox 'sha256sum ~/netbox.tar'
   ```

   Expected: the same SHA-256 on both. The copy took about three minutes. The VM checks the image itself in step 8, so the path does not need to be trusted.

## The install

8. Run the install script on the NetBox VM.

   ```bash
   REPLACE_WITH_SSH aisec-netbox 'sudo ~/netbox-install/netbox/install-netbox.sh ~/netbox.tar'
   ```

   Expected, on the first run: `ok    image` with `NETBOX_IMAGE_ID`, four `made  secret` lines, `made  TLS key and certificate`, PostgreSQL, Valkey, `units started`, then `login_page=200`. The units mount `client-address.py`, and the web unit `granian.py`, from `/etc/aisec/netbox`. The first start applies NetBox's migrations, about six minutes, with a `waiting` line each minute. Then both running images equal the ID, and the certificate's subject `CN=netbox.aisec.internal`, its end date, the names `DNS:netbox.aisec.internal` and `IP Address:10.50.0.4`, and its fingerprint. A second run prints `have` for the image, each secret, and the key, and the login page answers within a minute.

9. Copy the certificate to the orchestrator, which pins it.

   ```bash
   REPLACE_WITH_SSH aisec-netbox 'cat /etc/aisec/netbox/tls.crt' |
     REPLACE_WITH_SSH aisec-orchestrator 'sudo install -d -m 755 /etc/aisec/netbox && sudo tee /etc/aisec/netbox/tls.crt > /dev/null && sudo chmod 644 /etc/aisec/netbox/tls.crt'
   REPLACE_WITH_SSH aisec-netbox 'openssl x509 -in /etc/aisec/netbox/tls.crt -noout -fingerprint -sha256'
   REPLACE_WITH_SSH aisec-orchestrator 'openssl x509 -in /etc/aisec/netbox/tls.crt -noout -fingerprint -sha256'
   ```

   Expected: the same fingerprint on both, the one step 8 printed.

10. Reach NetBox from the orchestrator with the pin, and in plain HTTP.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'curl -s -o /dev/null -w "%{http_code}\n" --noproxy "*" --max-time 8 \
      --cacert /etc/aisec/netbox/tls.crt --resolve netbox.aisec.internal:8443:10.50.0.4 https://netbox.aisec.internal:8443/login/;
      curl -s -o /dev/null -w "%{http_code}\n" --noproxy "*" --max-time 8 http://10.50.0.4:8443/login/'
    ```

    Expected: `200`, then `000`.

11. Read what the units logged.

    ```bash
    REPLACE_WITH_SSH aisec-netbox 'sudo journalctl --no-pager -o cat -u netbox -u netbox-worker | tail -n 40; systemctl show -p NRestarts netbox netbox-worker'
    ```

    Expected: `Listening at: https://0.0.0.0:8443`, `loaded config '/etc/netbox/config/client-address.py'` from both units, two Granian workers started, `GET /login/ ... 200`, and no traceback. The worker restarts while the first start migrates the database, and not after.

12. Remove the archive's copy from the NetBox VM. The orchestrator keeps its copy for a rebuild.

    ```bash
    REPLACE_WITH_SSH aisec-netbox 'rm -f ~/netbox.tar'
    ```

    Expected: no output.

## The seed

13. Make the probe account's token on the NetBox VM, into a root-only file on the orchestrator. The token is read-only and limited to `192.0.2.1`, which no host has.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo install -d -m 700 /etc/aisec/netbox/tokens'
    REPLACE_WITH_SSH aisec-netbox 'sudo ~/netbox-install/netbox/make-netbox-token.sh probe' |
      REPLACE_WITH_SSH aisec-orchestrator "sudo sh -c 'umask 077; cat > /etc/aisec/netbox/tokens/aisec-address-probe'"
    REPLACE_WITH_SSH aisec-orchestrator "sudo stat -c '%U %a %s %n' /etc/aisec/netbox/tokens /etc/aisec/netbox/tokens/aisec-address-probe"
    ```

    Expected: Django's `FutureWarning` for `LOGIN_REQUIRED`, from netbox-docker's configuration, then `root 700` for the directory and `root 600 58` for the file. No command prints the token.

14. Send the probe's token from the orchestrator, with no header and with each header that names `192.0.2.1`.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo bash -s' <<'EOF'
    address() {
      out=$(curl -s --noproxy "*" --max-time 8 --cacert /etc/aisec/netbox/tls.crt -w " %{http_code}" "$@" \
        -H @<(printf "Authorization: Bearer %s\n" "$(cat /etc/aisec/netbox/tokens/aisec-address-probe)") \
        https://10.50.0.4:8443/api/status/)
      echo "${out##* }:$(printf "%s" "$out" | sed -n "s/.*Source IP \([0-9.]*\) is not permitted.*/\1/p")"
    }
    echo "none=$(address) x-forwarded-for=$(address -H "X-Forwarded-For: 192.0.2.1") x-real-ip=$(address -H "X-Real-IP: 192.0.2.1")"
    EOF
    ```

    Expected: `none=403:10.40.0.4 x-forwarded-for=403:10.40.0.4 x-real-ip=403:10.40.0.4`. A `200` means NetBox believed a header. `403:` with no address means NetBox saw the address in another form ([troubleshooting 17](../troubleshooting/17-netbox-sees-ipv4-clients-as-mapped-ipv6.md)). Either way, stop: no token's address limit holds.

15. Make the seeding token, for the `aisec-seed` superuser, into a root-only file on the orchestrator.

    ```bash
    REPLACE_WITH_SSH aisec-netbox 'sudo ~/netbox-install/netbox/make-netbox-token.sh seed' |
      REPLACE_WITH_SSH aisec-orchestrator "sudo sh -c 'umask 077; cat > /etc/aisec/netbox/seed-token'"
    REPLACE_WITH_SSH aisec-orchestrator 'sudo stat -c "%U %a %s %n" /etc/aisec/netbox/seed-token'
    ```

    Expected: `root 600 58`. The token may write, from `10.40.0.4` only, for one hour. Each run of the script deletes the account's earlier tokens.

16. Copy the seed to the orchestrator, and seed twice into a directory in memory.

    ```bash
    tar -C REPLACE_WITH_TARGETS_CHECKOUT/netbox -cf - seed.py seed.json | REPLACE_WITH_SSH aisec-orchestrator \
      'rm -rf ~/feed/netbox-seed && mkdir -p ~/feed/netbox-seed && tar -C ~/feed/netbox-seed -xf -'
    run=$(REPLACE_WITH_SSH aisec-orchestrator 'sudo mktemp -d -p /run aisec-netbox-tokens.XXXXXX')
    echo "$run"
    REPLACE_WITH_SSH aisec-orchestrator "sudo python3 -I ~/feed/netbox-seed/seed.py ~/feed/netbox-seed/seed.json $run"
    REPLACE_WITH_SSH aisec-orchestrator "sudo python3 -I ~/feed/netbox-seed/seed.py ~/feed/netbox-seed/seed.json $run"
    ```

    Expected: `/run/aisec-netbox-tokens.` and six characters. The first run prints 32 `made` lines for the objects, then `made  token for` each of `inventory-reader`, `inventory-reader-control`, and `aisec-collector`. The second prints 32 `have` lines and makes three new tokens, which replace the first run's. A line that names a difference stops the run: NetBox holds an object the seed did not make.

17. Put each token on its host, and the certificate on the lab VM. Then remove the run directory and the seeding token.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "sudo install -m 600 $run/aisec-collector /etc/aisec/netbox/tokens/aisec-collector"
    REPLACE_WITH_SSH aisec-lab 'sudo install -d -m 755 /etc/aisec/netbox && sudo install -d -m 700 /etc/aisec/netbox/tokens'
    for account in inventory-reader inventory-reader-control; do
      REPLACE_WITH_SSH aisec-orchestrator "sudo cat $run/$account" |
        REPLACE_WITH_SSH aisec-lab "sudo sh -c 'umask 077; cat > /etc/aisec/netbox/tokens/$account'"
    done
    REPLACE_WITH_SSH aisec-orchestrator 'cat /etc/aisec/netbox/tls.crt' |
      REPLACE_WITH_SSH aisec-lab 'sudo sh -c "umask 022; cat > /etc/aisec/netbox/tls.crt"'
    REPLACE_WITH_SSH aisec-orchestrator "sudo rm -r $run /etc/aisec/netbox/seed-token"
    REPLACE_WITH_SSH aisec-orchestrator 'sudo sh -c "stat -c \"%U %a %n\" /etc/aisec/netbox/tokens /etc/aisec/netbox/tokens/*"'
    REPLACE_WITH_SSH aisec-lab 'sudo sh -c "stat -c \"%U %a %n\" /etc/aisec/netbox/tokens /etc/aisec/netbox/tokens/* /etc/aisec/netbox/tls.crt"
      openssl x509 -in /etc/aisec/netbox/tls.crt -noout -fingerprint -sha256'
    ```

    Expected: on the orchestrator, `root 700` for the directory and `root 600` for `aisec-address-probe` and `aisec-collector`. On the lab VM, `root 700`, `root 600` for both tokens, `root 644` for the certificate, and the fingerprint of step 9.

18. Run both of the collector's methods in full, from this checkout, with the contract on standard input.

    ```bash
    code=$(cat collectors/netbox/netbox_access.py)
    REPLACE_WITH_SSH aisec-orchestrator "sudo python3 -I -c $(printf %q "$code") configured" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
    REPLACE_WITH_SSH aisec-lab "sudo python3 -I -c $(printf %q "$code") observed" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
    ```

    Expected: `configured` gives `inventory-reader` `excess`, for `view` on `dcim.device` and on `ipam.ipaddress` without a constraint, and `inventory-reader-control` `within`. `observed` gives `inventory-reader` `excess`, for the `b-` and `c-` devices and the `172.16.2.x` and `172.16.3.x` addresses, and `inventory-reader-control` `within`, with its three devices and three addresses. Every denial is `403` for both.

19. Remove NetBox's directory from the NetBox VM, and the seed from the orchestrator.

    ```bash
    REPLACE_WITH_SSH aisec-netbox 'rm -rf ~/netbox-install'
    REPLACE_WITH_SSH aisec-orchestrator 'rm -rf ~/feed/netbox-seed'
    ```

    Expected: no output.

## Checks

20. Run every check, with the targets checkout named.

    ```bash
    export AISEC_TARGETS=REPLACE_WITH_TARGETS_CHECKOUT
    validation/platform-checks.sh
    ```

    Expected: every check passes, `N.1` to `N.17`, `C.12`, and `Z.25` among them ([targets](../validation/targets.md#netbox)). Then plan both roots again with `-detailed-exitcode`. Expected: exit `0` twice.

## Undo

Not run. Rebuilding the NetBox VM from the [target VMs runbook](targets.md#rebuild) removes everything this installed. In place: stop `netbox` and `netbox-worker`, remove `/etc/containers/systemd/netbox*.container`, the five `netbox_*` Podman secrets, the image, `/etc/aisec/netbox`, `/etc/valkey/aisec-netbox.conf` and its `include` line, and the `netbox` role and database. Then remove the pin on the orchestrator, `/etc/aisec/netbox/tls.crt`, and the token directory `/etc/aisec/netbox/tokens`. On the lab VM, remove `/etc/aisec/netbox`. A rebuild removes NetBox's accounts and their tokens with its database. In place, without a rebuild: delete the seeded objects, the five accounts, and their tokens in NetBox.
