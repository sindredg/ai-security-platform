# SSH certificates and the feed account: operator procedure

Status: Implemented on 2026-10-16. Steps 1 and 3 to 13 were run that day on both live VMs, through scripts with the same commands, order, and expected results. The results are in the [milestone 3a worklog](../worklogs/0004-edge-network-and-monitoring.md#rollout-1). Step 2, the revocation in step 14, the replacement in step 15, and a first boot from the templates have not been run.

Run these steps once on VMs built before this change. They add two things that first boot now does by itself: the feed key's own account on the worker ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)), and an administrator account that accepts only a certificate from the operator's certificate authority ([ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md)). A rebuilt VM needs only steps 1 to 3 and the feed key step of the [platform compute runbook](platform-compute.md).

## Inputs and access

| Input | Notes |
| --- | --- |
| SSH to both VMs with the operator key | `REPLACE_WITH_SSH` below stands for the operator's `ssh` command with its options, for example `ssh -F <config>`. Steps 4 to 6 use the plain key. From step 9 the same command has to offer the certificate: add `CertificateFile REPLACE_WITH_OPERATOR_KEY.aisec-cert.pub` to the config |
| A checkout of this repository on the workstation, at the commit to apply | The files below come from `worker/feed/` and the two cloud-init templates |
| `ssh-keygen` from OpenSSH 8.2 or later, `python3` with PyYAML | Signing, and reading the drop-in out of a template |
| Somewhere to keep the certificate authority's private key | Apart from the daily login key. Where is the operator's choice |
| A second terminal | For the steps that ask for the passphrase |

## The certificate authority

1. Make the authority's key pair, with a passphrase.

   ```bash
   ssh-keygen -t ed25519 -C aisec-user-ca -f REPLACE_WITH_CA_KEY
   cp REPLACE_WITH_CA_KEY.pub REPLACE_WITH_CRED_DIR/aisec-user-ca.pub
   ```

   Expected: a passphrase prompt twice, then two files. Only the `.pub` file goes anywhere else.

2. Put the public half in `infra/platform/terraform.tfvars`, for the next rebuild.

   ```bash
   echo "operator_user_ca_public_key = \"$(cat REPLACE_WITH_CRED_DIR/aisec-user-ca.pub)\""
   ```

   Expected: one line to paste into the file. A plan shows no change to a running VM: the VMs ignore changes to custom data.

## Sign a certificate

3. Sign the login key for 12 hours. Run this at the start of each working day.

   ```bash
   ssh-keygen -s REPLACE_WITH_CA_KEY -I "aisec-operator-$(date -u +%F)" -n aisec-operator \
     -z "$(date -u +%s)" -V -5m:+11h55m \
     -O clear -O permit-pty -O permit-port-forwarding \
     -O source-address=100.64.0.0/10,10.40.0.4/32 \
     REPLACE_WITH_OPERATOR_KEY.pub
   mv REPLACE_WITH_OPERATOR_KEY-cert.pub REPLACE_WITH_OPERATOR_KEY.aisec-cert.pub
   ssh-keygen -L -f REPLACE_WITH_OPERATOR_KEY.aisec-cert.pub
   ```

   Expected: one passphrase prompt, then a certificate with the key ID of the day, a serial, `Valid: from` five minutes ago for 12 hours, principal `aisec-operator`, the `source-address` option, and only `permit-port-forwarding` and `permit-pty`. The serial is the time in seconds, so each certificate has its own and can be revoked alone.

   The start is five minutes back so that a workstation clock a little ahead is not refused. `10.40.0.4/32` is there until the router exists ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)). After that, the option is `source-address=10.45.0.32/27,100.64.0.0/10`.

   The certificate is kept beside the key under another name, so that `ssh` loads it only where the config says. Step 10 needs a login without it.

## The feed account on the worker

4. Copy the feed files to the worker and install them with the orchestrator's feed key.

   ```bash
   tar -C worker/feed -cf - . | REPLACE_WITH_SSH aisec-worker \
     'rm -rf ~/feed/feed-account && mkdir -p ~/feed/feed-account && tar -C ~/feed/feed-account -xf -'
   FEED_KEY=$(REPLACE_WITH_SSH aisec-orchestrator 'cat ~/.ssh/aisec-feed.pub')
   REPLACE_WITH_SSH aisec-worker "sudo ~/feed/feed-account/install-feed-account.sh '$FEED_KEY'"
   ```

   Expected: no output.

5. Use the feed key from the orchestrator.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator '
     F="ssh -i ~/.ssh/aisec-feed -o BatchMode=yes aisec-feed@aisec-worker"
     $F -n id; echo "exit $?"
     tar -cf - -T /dev/null | $F receive agent-runtime; echo "exit $?"
     $F -n size agent-runtime'
   ```

   Expected: `refused: not a feed request` and `exit 2`, then `exit 0`, then a size for `/home/aisec-feed/agent-runtime/stage`.

6. Take the feed key out of the administrator account on the worker.

   ```bash
   REPLACE_WITH_SSH aisec-worker "sed -i '/ aisec-feed\$/d' ~/.ssh/authorized_keys && grep -c . ~/.ssh/authorized_keys"
   REPLACE_WITH_SSH aisec-orchestrator 'ssh -n -i ~/.ssh/aisec-feed -o BatchMode=yes aisec@aisec-worker true; echo "exit $?"'
   ```

   Expected: `1`, the operator key. Then `Permission denied (publickey)` and `exit 255`.

## Certificates on each VM

Run steps 7 to 12 for the worker first, then for the orchestrator. If something goes wrong on the worker, the orchestrator is still reachable. `VM` is `worker` or `orchestrator`.

7. Write the authority's public key, the principal, an empty revocation list, and the template's SSH drop-in. Keep the old drop-in.

   ```bash
   VM=REPLACE_WITH_VM
   REPLACE_WITH_SSH aisec-$VM 'sudo tee /etc/ssh/aisec-user-ca.pub >/dev/null' < REPLACE_WITH_CRED_DIR/aisec-user-ca.pub
   python3 -I -c 'import sys, yaml
   s = open(sys.argv[1]).read().replace("${admin_username}", "aisec")
   print(next(f["content"] for f in yaml.safe_load(s)["write_files"]
              if f["path"] == "/etc/ssh/sshd_config.d/10-aisec.conf"), end="")' \
     infra/platform/cloud-init/$VM.yaml.tftpl |
     REPLACE_WITH_SSH aisec-$VM 'sudo tee /etc/ssh/sshd_config.d/10-aisec.conf.new >/dev/null'
   REPLACE_WITH_SSH aisec-$VM 'set -e
     sudo chmod 644 /etc/ssh/aisec-user-ca.pub
     echo aisec-operator | sudo tee /etc/ssh/aisec-principals >/dev/null
     sudo ssh-keygen -q -k -f /etc/ssh/aisec-revoked.krl
     sudo cp -p /etc/ssh/sshd_config.d/10-aisec.conf /root/10-aisec.conf.before
     sudo sshd -T -C user=nobody,host=check,addr=10.40.0.4 > /tmp/sshd-other.before
     sudo chmod 600 /etc/ssh/sshd_config.d/10-aisec.conf.new
     sudo mv /etc/ssh/sshd_config.d/10-aisec.conf.new /etc/ssh/sshd_config.d/10-aisec.conf
     sudo sshd -t && echo syntax-ok'
   ```

   Expected: `syntax-ok`. Nothing has changed for a login yet: sshd reads the files when it reloads.

8. Arm a timer that puts the old drop-in back in 15 minutes, then reload sshd.

   ```bash
   REPLACE_WITH_SSH aisec-$VM 'sudo systemd-run --quiet --unit aisec-sshd-revert --on-active=15min /bin/sh -c \
       "cp -p /root/10-aisec.conf.before /etc/ssh/sshd_config.d/10-aisec.conf && systemctl reload ssh"
     systemctl is-active aisec-sshd-revert.timer
     sudo systemctl reload ssh'
   ```

   Expected: `active`. If the next step fails, wait for the timer. The plain key is still in `authorized_keys` until step 12, so it logs in again once the old drop-in is back.

9. Log in with the certificate, on a new connection.

   ```bash
   REPLACE_WITH_SSH -o ControlPath=none aisec-$VM 'hostname
     sudo journalctl -u ssh --since -2min --no-pager -o cat | grep "Accepted publickey for aisec" | tail -n 1'
   ```

   Expected: `aisec-VM`, then `Accepted publickey for aisec from ... ED25519-CERT SHA256:... ID aisec-operator-<day> (serial <n>) CA ED25519 SHA256:...`. The log line names the certificate, which a plain key could not.

10. Try the logins that have to fail: the plain key without a certificate, and three test certificates signed as in step 3 with one thing wrong each.

    ```bash
    ssh-keygen -s REPLACE_WITH_CA_KEY -I test-expired -n aisec-operator -z "$(date -u +%s)" -V -2h:-1h \
      -O clear -O permit-pty -O source-address=100.64.0.0/10,10.40.0.4/32 \
      REPLACE_WITH_OPERATOR_KEY.pub && mv REPLACE_WITH_OPERATOR_KEY-cert.pub test-expired-cert.pub
    # The same for test-wrong-source-cert.pub with -O source-address=192.0.2.1/32,
    # and for test-wrong-principal-cert.pub with -n aisec.
    B="ssh -F /dev/null -o UserKnownHostsFile=REPLACE_WITH_KNOWN_HOSTS_FILE -o BatchMode=yes -o IdentitiesOnly=yes -i REPLACE_WITH_OPERATOR_KEY"
    $B aisec@REPLACE_WITH_VM_ADDRESS true; echo "exit $?"
    for t in expired wrong-source wrong-principal; do
      $B -o CertificateFile=test-$t-cert.pub aisec@REPLACE_WITH_VM_ADDRESS true; echo "exit $?"
    done
    ```

    Expected: `Permission denied (publickey)` and `exit 255` four times. The VM's journal says why for each certificate.

    sshd then refuses every connection from the same address for about 20 seconds ([troubleshooting 05](../troubleshooting/05-failed-logins-block-every-routed-session.md)). On the worker that address is `10.40.0.4` for every routed session, the feed and the journal pull included. Wait until `REPLACE_WITH_SSH aisec-$VM true` works before step 11.

11. Check that other accounts are unchanged, and try the forwarding rule.

    ```bash
    REPLACE_WITH_SSH aisec-$VM 'sudo sshd -T -C user=nobody,host=check,addr=10.40.0.4 | diff /tmp/sshd-other.before - && echo same; rm /tmp/sshd-other.before'
    REPLACE_WITH_SSH -o ControlPath=none -W 127.0.0.1:22 aisec-$VM </dev/null
    REPLACE_WITH_SSH -o ControlPath=none -W 127.0.0.1:6443 aisec-orchestrator </dev/null
    ```

    Expected: `same`. Then `channel 0: open failed: administratively prohibited`. On the orchestrator only, the forward to 6443 opens and closes with no message.

    `kubectl` then works through `REPLACE_WITH_SSH -N -L 6443:127.0.0.1:6443 aisec-orchestrator`, with the kubeconfig's server set to `https://127.0.0.1:6443`.

12. Stop the revert timer, and remove the key file that sshd now ignores, and the backup.

    ```bash
    REPLACE_WITH_SSH aisec-$VM 'sudo systemctl stop aisec-sshd-revert.timer
      sudo rm -f /home/aisec/.ssh/authorized_keys /root/10-aisec.conf.before
      systemctl is-active aisec-sshd-revert.timer'
    ```

    Expected: `inactive`.

## Check

13. Run every check, with the authority's public key for the comparison.

    ```bash
    AISEC_USER_CA=REPLACE_WITH_CRED_DIR/aisec-user-ca.pub validation/platform-checks.sh
    ```

    Expected: every check passes. `HO.17` to `HO.20` and `HW.17` to `HW.20` on the [host hardening page](../validation/host-hardening.md), `A.5` and `A.7` to `A.10` on [access](../validation/access.md), and `E.4`, `E.9` to `E.11` on [containment](../validation/containment.md).

## Revoke a certificate

14. Revoke a certificate before it expires. The list holds every revoked serial, so keep the list of serials with the authority's key and write the whole list each time.

    ```bash
    printf 'serial: %s\n' REPLACE_WITH_SERIALS > revoked.txt
    ssh-keygen -k -f aisec-revoked.krl -s REPLACE_WITH_CRED_DIR/aisec-user-ca.pub revoked.txt
    for VM in worker orchestrator; do
      REPLACE_WITH_SSH aisec-$VM 'sudo tee /etc/ssh/aisec-revoked.krl >/dev/null && sudo ssh-keygen -Q -l -f /etc/ssh/aisec-revoked.krl' < aisec-revoked.krl
    done
    ```

    Expected: one listing per VM with the serials. sshd reads the list at each login, so it needs no reload. A login with a revoked certificate is refused.

## Replace the certificate authority

15. Make a new authority as in step 1. On each VM, add its public key to `/etc/ssh/aisec-user-ca.pub` below the old one, sign a certificate with it, log in with it as in step 9, then remove the old line. Update `terraform.tfvars` as in step 2.

    Expected: a login with the new certificate at each VM, then `HO.18` and `HW.18` pass with `AISEC_USER_CA` set to the new key, and fail with the old one. Not yet run.

If the authority's key or its passphrase is lost, no new certificate can be signed and the administrator account is closed. The way back is Azure's run-command, which needs the Owner role: write a new `/etc/ssh/aisec-user-ca.pub` on each VM through it.
