# Platform compute: operator procedure

Status: Implemented on 2026-10-11. Built once. Every step was run during that build, and each rotation was run once. The worker rebuild was run once on 2026-10-11, and the orchestrator rebuild once on 2026-10-13. A rebuild of everything from scratch has not been run. Results are in the [milestone 2 worklog](../worklogs/0002-platform-compute.md). On 2026-10-16 the logins changed to SSH certificates and the feed key to an account of its own on the worker ([SSH certificates runbook](ssh-certificates.md)). Steps 12, 14, 19, 24, and 29 and the feed key and operator key rotations were rewritten for that and have not been run in that form.

Run these steps to build milestone 2: the public address policy, the NAT gateway, the orchestrator and AI worker VMs, the mesh VPN, and K3s. Never commit local values, plans, state, keys, or raw output.

## Inputs and access

| Input | Notes |
| --- | --- |
| Milestone 1, built | The [network foundation runbook](network-foundation.md), with `$CRED_DIR` holding `platform.env` and `targets.env` |
| `terraform` 1.16.6, first on `PATH` | The roots refuse any other version. A distribution package can be older |
| `az` 2.88 or later, `ssh`, `jq` | Applies, checks, and logins |
| A mesh VPN account with administrator access | To create a tag and an auth key, and to approve routes |
| The mesh VPN client on the workstation, signed in | The VMs have no other way in |
| An SSH key pair on the workstation, used for this project only | Azure requires its public half. The administrator account takes it only with a certificate |
| The SSH certificate authority, and a certificate for the key signed today | Steps 1 to 3 of the [SSH certificates runbook](ssh-certificates.md). `operator_user_ca_public_key` in `terraform.tfvars` |
| Quota for 4 vCPUs in the platform region | 2 in the `Basv2` family and 2 in the `Dpsv6` family |

The design is in the [architecture](../architecture.md). The egress design is [ADR 0009](../decisions/0009-one-egress-point-on-the-orchestrator-subnet.md), the access design [ADR 0007](../decisions/0007-mesh-vpn-for-administrative-access.md).

The NAT gateway and both VMs bill for as long as they exist.

The addresses below are the ones the configuration assigns: `10.40.0.4` for the orchestrator and `10.40.0.36` for the worker.

## Check the pins

1. Put the pinned Terraform first on `PATH`.

   ```bash
   export PATH="REPLACE_WITH_TERRAFORM_1.16.6_DIRECTORY:$PATH"
   terraform version
   ```

   Expected: `Terraform v1.16.6`. With another version, every command below stops with `Unsupported Terraform Core version`.

2. Confirm that the pinned image version exists in the release offer for both architectures. The filter has to be exact. See [troubleshooting 01](../troubleshooting/01-image-version-only-in-daily-offer.md).

   ```bash
   for sku in server server-arm64; do
     az vm image list -l swedencentral -p Canonical -f ubuntu-26_04-lts -s "$sku" --all \
       --query "[?offer=='ubuntu-26_04-lts' && sku=='$sku'].version | sort(@) | [-1]" -o tsv
   done
   grep -A3 'variable "image_version"' infra/platform/variables.tf | grep default
   ```

   Expected: the same version three times. If the offer has a newer one, change the default first.

3. Confirm the sizes are available and the quota has room. Run as the operator.

   ```bash
   az vm list-skus -l swedencentral --resource-type virtualMachines \
     --query "[?name=='Standard_B2as_v2' || name=='Standard_D2ps_v6'].{name:name, zones:join(',',locationInfo[0].zones), restrictions:length(restrictions)}" -o table
   az vm list-usage -l swedencentral \
     --query "[?contains(name.value,'cores') || contains(name.value,'Basv2') || contains(name.value,'Dpsv6')].{name:name.value, used:currentValue, limit:limit}" -o table
   ```

   Expected: both sizes with `0` restrictions, and at least 4 unused in `cores` and 2 unused in each family.

## Prepare the mesh VPN

4. In the mesh VPN admin console, create a tag for the orchestrator, owned by the administrators group. Then generate an auth key with these settings.

   | Setting | Value |
   | --- | --- |
   | Reusable | Off |
   | Ephemeral | Off |
   | Tags | The orchestrator tag |
   | Expiration | 1 day |

   Expected: one key, shown once. Generate it right before step 8. It ends up in the VM's custom data and in state, which is why it has to be single use.

   Node signing is on in this tailnet. A node that joins with a plain key is on the network but cannot reach any other node until it is signed. Sign the key on a signing device with `tailscale lock sign <auth-key>` and use the longer key it prints, or sign the node after it joins. The first build turned signing on after the orchestrator had joined, which signed it. The rebuild on 2026-10-13 joined with a signed key and needed nothing more. Signing a node after it joins has not been run.

5. Store the key outside the repository until the apply.

   ```bash
   install -m 600 /dev/null "$CRED_DIR/tailscale-auth-key"
   "${EDITOR:-nano}" "$CRED_DIR/tailscale-auth-key"
   ```

   Expected: one line, mode `600`.

6. Give Terraform the operator's public key.

   ```bash
   cd infra/platform
   # In terraform.tfvars, set operator_ssh_public_key to the one line of the .pub file.
   grep -c operator_ssh_public_key terraform.tfvars
   ```

   Expected: `1`. Git ignores the file.

## Apply

Plan, read the plan, then apply the saved plan. Do not apply a plan nobody read.

7. Assign the public address policy. Run in `infra/bootstrap` as the operator.

   ```bash
   cd ../bootstrap
   export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
   terraform plan -out=bootstrap.tfplan
   terraform apply bootstrap.tfplan
   ```

   Expected: 3 to add, all policy assignments. Two refuse a public address on a network interface, one per workload resource group. One refuses public IP resources on the target side.

8. Build the platform side. Run in `infra/platform` as the platform identity, with the auth key.

   ```bash
   cd ../platform
   source "$CRED_DIR/platform.env"
   export TF_VAR_tailscale_auth_key="$(cat "$CRED_DIR/tailscale-auth-key")"
   terraform init -backend-config=backend.hcl
   terraform plan -out=platform.tfplan
   terraform apply platform.tfplan
   rm -f platform.tfplan
   unset TF_VAR_tailscale_auth_key
   ```

   Expected: 8 to add, 2 to change. The additions are the NAT gateway, its address, two associations, two network interfaces, and two VMs. The changes are the orchestrator and worker security groups, including the two rules for the package proxy. The saved plan holds the auth key, so it is deleted.

   If the VMs fail and the rest succeeds, fix the cause and plan again. The next plan shows only the VMs.

9. Add the target-side denies. Run in `infra/targets` as the target identity.

   ```bash
   cd ../targets
   source "$CRED_DIR/targets.env"
   terraform init -backend-config=backend.hcl
   terraform plan -out=targets.tfplan
   terraform apply targets.tfplan
   ```

   Expected: 0 to add, 4 to change. Each target security group gains `deny-to-internet` and `deny-to-azure-dns`.

10. Confirm that every root has converged. The auth key variable is empty here on purpose: the VM ignores changes to its custom data after creation.

    ```bash
    (cd ../platform && source "$CRED_DIR/platform.env" && terraform plan -detailed-exitcode)
    (cd ../targets && source "$CRED_DIR/targets.env" && terraform plan -detailed-exitcode)
    (cd ../bootstrap && terraform plan -detailed-exitcode)
    ```

    Expected: `No changes` and exit `0` three times.

## Connect

11. In the mesh VPN admin console, find `aisec-orchestrator` and approve both routes it advertises. Then delete the spent key.

    ```bash
    rm "$CRED_DIR/tailscale-auth-key"
    for host in 10.40.0.4 10.40.0.36; do
      timeout 8 bash -c "echo > /dev/tcp/$host/22" && echo "$host reachable"
    done
    ```

    Expected: the node is listed with the orchestrator tag, and both addresses answer on port 22. First boot takes about a minute after the apply returns.

12. Take the host keys from the serial log, not from the first connection. Run as the operator.

    ```bash
    for vm in orchestrator worker; do
      az vm boot-diagnostics get-boot-log -g rg-aisec-platform -n "vm-aisec-$vm" -o tsv \
        | grep -a -o 'SHA256:[A-Za-z0-9+/]* root@aisec-[a-z]* (ED25519)' | sort -u
    done
    export KNOWN_HOSTS='REPLACE_WITH_KNOWN_HOSTS_FILE'
    ssh-keyscan -T 10 -t ed25519 10.40.0.4 10.40.0.36 > "$KNOWN_HOSTS"
    ssh-keygen -lf "$KNOWN_HOSTS"
    ```

    Expected: the two fingerprints from the scan equal the two from the serial log. If the scan of the worker prints a banner and no key, the segment size clamp is missing. See [troubleshooting 02](../troubleshooting/02-ssh-through-subnet-router-stalls.md).

    Every `ssh` below uses these options:

    ```bash
    SSH_OPTS="-o UserKnownHostsFile=$KNOWN_HOSTS -o StrictHostKeyChecking=yes -o CertificateFile=REPLACE_WITH_OPERATOR_KEY.aisec-cert.pub"
    ```

    The administrator account refuses the key without a certificate. A certificate signed more than 12 hours ago is refused too: sign a new one with step 3 of the [SSH certificates runbook](ssh-certificates.md).

13. Confirm the orchestrator's first boot.

    ```bash
    ssh $SSH_OPTS aisec@10.40.0.4 '
      ls /var/lib/aisec-first-boot.done; cloud-init status; ls /run/aisec
      systemctl is-active k3s tailscaled aisec-mss-clamp squid
      sudo tailscale status
      sudo k3s kubectl get nodes
      sudo k3s kubectl get pods -A
      sudo k3s secrets-encrypt status'
    ```

    Expected: the marker file exists, `status: done`, and `/run/aisec` is empty, so the auth key file is gone. Four services `active`. The node is `Ready`, three `kube-system` pods are `Running`, and encryption status is `Enabled`.

14. Let the orchestrator copy files to the worker. Its key pair was generated at first boot, so the private half never passed through Terraform. The worker's first boot made the feed account. This gives it the key ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)).

    ```bash
    FEED_KEY="$(ssh $SSH_OPTS aisec@10.40.0.4 'cat ~/.ssh/aisec-feed.pub')"
    ssh $SSH_OPTS aisec@10.40.0.36 \
      "sudo /usr/local/lib/aisec/install/install-feed-account.sh '$FEED_KEY'"
    WORKER_KEY="$(grep '^10.40.0.36 ' "$KNOWN_HOSTS" | sed 's/^10.40.0.36/aisec-worker,10.40.0.36/')"
    ssh $SSH_OPTS aisec@10.40.0.4 \
      "grep -qF aisec-worker ~/.ssh/known_hosts 2>/dev/null || echo '$WORKER_KEY' >> ~/.ssh/known_hosts
       ssh -n -i ~/.ssh/aisec-feed -o BatchMode=yes -o StrictHostKeyChecking=yes aisec-feed@aisec-worker id; echo \"exit \$?\""
    ```

    Expected: `refused: not a feed request` and `exit 2`. The key logs in, and the account runs nothing but the feed command.

## Check the milestone 2 gate

Most of what follows is also in `validation/platform-checks.sh`, which runs about a hundred checks in two minutes. See [validation](../validation/README.md). Run it after every change to a VM, after a restart, and after a rebuild.

15. Test the paths with traffic, read the effective rules, and test the policy. The commands and the results of the build are in the [worklog](../worklogs/0002-platform-compute.md#paths-tested-with-traffic).

    | Check | Expected |
    | --- | --- |
    | From the worker: any internet address, any target address, `168.63.129.16:53`, a public name lookup | Every one times out |
    | From the orchestrator: an internet address on 443, the worker on 22 | Both open |
    | From the orchestrator: the address it leaves from | Equal to the NAT gateway's public address |
    | Effective rules on both network interfaces | The configured rules, plus one IPv6 deny that the platform adds |
    | A template with a public address, validated in both workload resource groups | `RequestDisallowedByPolicy` |
    | `az vm restart` of the orchestrator | Node `Ready`, the services `active`, pods `Running`, the worker reachable again |

16. Run the Kubernetes benchmark on the orchestrator. Check the release against its checksum file first, and remove the tool afterwards.

    ```bash
    ssh $SSH_OPTS aisec@10.40.0.4 '
      set -e; d=$(mktemp -d); cd $d
      b=https://github.com/aquasecurity/kube-bench/releases/download/v0.16.0
      curl -fsSLO $b/kube-bench_0.16.0_linux_amd64.tar.gz
      curl -fsSLO $b/kube-bench_0.16.0_checksums.txt
      grep linux_amd64.tar.gz kube-bench_0.16.0_checksums.txt | sha256sum -c -
      tar xzf kube-bench_0.16.0_linux_amd64.tar.gz
      sudo ./kube-bench run --config-dir cfg --config cfg/config.yaml --benchmark k3s-cis-1.9
      cd /; sudo rm -rf $d'
    ```

    Expected: the checksum line ends in `OK`. Before steps 17 and 18, the summary is 63 pass, 3 fail, 50 warn, 14 info, and the fails are 1.1.20, 1.2.26, and 5.1.5. After them it is 65 pass and 1 fail. Check 1.2.26 stays failed: this cluster has no etcd.

    The first-boot script has applied steps 17 and 18 since 2026-10-12, so a build from the current template should show 65 pass and 1 fail on the first run. The count is reasoned, not observed. The orchestrator was rebuilt from that template on 2026-10-13 and the two settings were in place after first boot, read by checks `K.5` and `K.6`. kube-bench itself was not run on that build.

## Harden

17. Stop default service accounts from mounting a token. Answers check 5.1.5. First boot does this for the four namespaces K3s creates. Running it again changes nothing and prints the result.

    ```bash
    ssh $SSH_OPTS aisec@10.40.0.4 '
      for ns in $(sudo k3s kubectl get ns -o jsonpath="{.items[*].metadata.name}"); do
        sudo k3s kubectl patch serviceaccount default -n $ns -p "{\"automountServiceAccountToken\": false}"
      done
      sudo k3s kubectl get sa -A --field-selector metadata.name=default \
        -o custom-columns=NS:.metadata.namespace,AUTOMOUNT:.automountServiceAccountToken'
    ```

    Expected: `false` for every namespace. A namespace created later needs the same patch.

18. Tighten the certificate file permissions, restart K3s, and read them again. Answers check 1.1.20. First boot sets the mode. The restart here shows that K3s keeps it.

    ```bash
    ssh $SSH_OPTS aisec@10.40.0.4 '
      sudo sh -c "chmod 600 /var/lib/rancher/k3s/server/tls/*.crt"
      sudo systemctl restart k3s; sleep 45
      sudo sh -c "stat -c %a /var/lib/rancher/k3s/server/tls/*.crt | sort | uniq -c"
      sudo k3s kubectl get nodes'
    ```

    Expected: 13 files at `600` and the node `Ready`. Then run step 16 again.

19. Audit the operating system on both VMs. Lynis is not a CIS benchmark. It is what runs on this release today. Check the archive against the SHA-256 on the publisher's download page.

    ```bash
    ssh $SSH_OPTS aisec@10.40.0.4 '
      set -e; d=$(mktemp -d); cd $d
      curl -fsSLO https://downloads.cisofy.com/lynis/lynis-3.1.7.tar.gz
      echo "REPLACE_WITH_PUBLISHED_SHA256  lynis-3.1.7.tar.gz" | sha256sum -c -
      sudo tar xzf lynis-3.1.7.tar.gz --no-same-owner; cd lynis
      sudo ./lynis audit system --quiet --no-colors --logfile $d/lynis.log --report-file $d/lynis-report.dat
      sudo grep -E "^(hardening_index|lynis_tests_done)=|^warning" $d/lynis-report.dat
      cd /; sudo rm -rf $d'
    ```

    Expected: the checksum line ends in `OK`, then the test count, the hardening index, and any warnings. On this build the orchestrator scored 60 with two warnings, both about packages, before the hardening that cloud-init now applies, and 76 after it.

    Run the same on the worker, with the archive copied through the workstation: `ssh $SSH_OPTS aisec@10.40.0.4 'cat REPLACE_WITH_ARCHIVE' | ssh $SSH_OPTS aisec@10.40.0.36 'cat > /tmp/lynis-3.1.7.tar.gz'`, and the same checksum check before unpacking. Expected: the run stalls for about six minutes at the package update test, because the worker cannot reach a repository, and then finishes. On this build it scored 66 with no warnings before the hardening and 77 after. To skip the stall, put `skip-test=PKGS-7392` in a `custom.prf` file next to the `lynis` script.

20. Install pending security updates on the orchestrator.

    ```bash
    ssh $SSH_OPTS aisec@10.40.0.4 'sudo unattended-upgrade; apt list --upgradable 2>/dev/null; ls /var/run/reboot-required'
    ```

    Expected: nothing left from the `-security` suite, and no `reboot-required` file. If the file exists, restart the VM and repeat the restart check in step 15.

21. Check the worker's package path. Run on the worker.

    ```bash
    ssh $SSH_OPTS aisec@10.40.0.36 '
      P=http://10.40.0.4:3128
      c() { curl -s -o /dev/null -w "%{http_code}\n" --max-time 8 "$@"; }
      c -x $P http://archive.ubuntu.com/ubuntu/dists/resolute/InRelease
      c -x $P http://example.com/
      c -x $P -X POST -d x http://archive.ubuntu.com/ubuntu/
      curl -s -o /dev/null -w "%{http_connect}\n" --max-time 8 -x $P https://example.com/
      timeout 5 bash -c "</dev/tcp/10.40.0.4/6443" && echo OPEN || echo "no connection"
      sudo apt-get update && sudo unattended-upgrade
      apt list --upgradable 2>/dev/null | grep -c -- -security'
    ```

    Expected: `200`, then `403` three times, `no connection`, a package list refresh that fetches from the two Ubuntu hosts, and `0` packages left from the security suite. The design is [ADR 0011](../decisions/0011-package-proxy-for-the-worker.md).

## Rebuild the worker

Run once, on 2026-10-11, while the worker was empty. The commands are that run, condensed. A rebuild destroys everything on the worker: after milestone 3 that includes the model.

22. Replace the VM. Run in `infra/platform` as the platform identity. Read the plan before applying it.

    ```bash
    source "$CRED_DIR/platform.env"
    terraform plan -replace='azurerm_linux_virtual_machine.vm["worker"]' -out=platform.tfplan
    terraform apply platform.tfplan
    rm -f platform.tfplan
    ```

    Expected: `1 to add, 0 to change, 1 to destroy`, and the only resource is the worker VM. About two minutes. If the plan names anything else, stop.

23. Take the new host key from the serial log and replace the old one. Run as the operator. First boot takes about 80 seconds, and the fingerprint is not in the log before that.

    ```bash
    az vm boot-diagnostics get-boot-log -g rg-aisec-platform -n vm-aisec-worker -o tsv \
      | grep -a -o 'SHA256:[A-Za-z0-9+/]* root@aisec-[a-z]* (ED25519)' | sort -u
    grep -v '^10.40.0.36 ' "$KNOWN_HOSTS" > "$KNOWN_HOSTS.new"
    ssh-keyscan -T 10 -t ed25519 10.40.0.36 >> "$KNOWN_HOSTS.new"
    mv "$KNOWN_HOSTS.new" "$KNOWN_HOSTS"
    ssh-keygen -lf "$KNOWN_HOSTS"
    ssh $SSH_OPTS aisec@10.40.0.36 'cloud-init status'
    ```

    Expected: the worker's fingerprint from the scan equals the one from the serial log, and `status: done`.

24. Let the orchestrator copy files to the new worker. The orchestrator still holds the old host key, so remove it first.

    ```bash
    FEED_KEY="$(ssh $SSH_OPTS aisec@10.40.0.4 'cat ~/.ssh/aisec-feed.pub')"
    ssh $SSH_OPTS aisec@10.40.0.36 \
      "sudo /usr/local/lib/aisec/install/install-feed-account.sh '$FEED_KEY'"
    WORKER_KEY="$(grep '^10.40.0.36 ' "$KNOWN_HOSTS" | sed 's/^10.40.0.36/aisec-worker,10.40.0.36/')"
    ssh $SSH_OPTS aisec@10.40.0.4 \
      "ssh-keygen -q -R aisec-worker; ssh-keygen -q -R 10.40.0.36; rm -f ~/.ssh/known_hosts.old
       echo '$WORKER_KEY' >> ~/.ssh/known_hosts
       ssh -n -i ~/.ssh/aisec-feed -o BatchMode=yes -o StrictHostKeyChecking=yes aisec-feed@aisec-worker id; echo \"exit \$?\""
    ```

    Expected: `refused: not a feed request` and `exit 2`.

25. Run step 21 for the first update, then every check.

    ```bash
    validation/platform-checks.sh
    ```

    Expected: `0` packages left from the security suite, and every check passes. The environment the script needs is in [validation](../validation/README.md).

## Rebuild the orchestrator

Run once, on 2026-10-13. The commands are that run, condensed. Results are in the [worklog](../worklogs/0002-platform-compute.md#orchestrator-rebuild).

A rebuild destroys everything on the orchestrator:

| Lost | What brings it back |
| --- | --- |
| The cluster and everything deployed in it | First boot installs an empty K3s. Workloads have to be deployed again |
| The mesh VPN node identity | A new auth key, and the routes approved again |
| The feed key | First boot makes a new one. The worker has to trust it, step 29 |
| The orchestrator's `known_hosts` | Step 29 |
| The staged inputs under `~/feed`, about 9 GB | Step 31 |

The worker keeps running, but it has no outbound access and cannot be reached while the orchestrator is gone: the mesh routes and the package proxy both live there. Do this when no job is running.

26. Record a baseline and check the pins. Run `validation/platform-checks.sh`, then steps 1 and 2. Check the K3s and mesh VPN agent versions in `infra/platform/variables.tf` against the releases the publishers serve.

    Expected: every check passes, or the failures are known. A newer pin is a pull request first, not a step.

27. Generate a new auth key as in step 4 and sign it on a signing device. Plan with the key in the environment, and read the plan before going on. Run in `infra/platform` as the platform identity.

    ```bash
    source "$CRED_DIR/platform.env"
    export TF_VAR_tailscale_auth_key='REPLACE_WITH_SIGNED_AUTH_KEY'
    [ -n "$TF_VAR_tailscale_auth_key" ] && echo set
    terraform init -backend-config=backend.hcl
    terraform plan -replace='azurerm_linux_virtual_machine.vm["orchestrator"]' -out=platform.tfplan
    ```

    Expected: `set`, then `1 to add, 0 to change, 1 to destroy`, and the only resource is the orchestrator VM. If the plan names anything else, stop.

    The plan shows `custom_data` as `(sensitive value)`, so it cannot tell whether the key is in it. That is what the `set` line is for. A VM built with an empty key boots and never joins the mesh.

    The plan also shows a changed `admin_ssh_key` if the operator key was rotated since the last build. The key in the plan has to be the one the workstation logs in with.

28. Remove the old `aisec-orchestrator` node in the mesh VPN admin console, then apply. Access to both VMs is gone from here until the routes are approved.

    ```bash
    terraform apply platform.tfplan
    rm -f platform.tfplan
    unset TF_VAR_tailscale_auth_key
    ```

    Expected: `1 added, 0 changed, 1 destroyed`. Then approve both routes of the new node in the admin console, as in step 11. If the old node is still listed, the new one joins under a different name.

29. Take the new host key from the serial log, then give the new feed key to the worker's feed account. Run as the operator. First boot takes about 80 seconds.

    ```bash
    az vm boot-diagnostics get-boot-log -g rg-aisec-platform -n vm-aisec-orchestrator -o tsv \
      | grep -a -o 'SHA256:[A-Za-z0-9+/]* root@aisec-[a-z]* (ED25519)' | sort -u
    grep -v '^10.40.0.4 ' "$KNOWN_HOSTS" > "$KNOWN_HOSTS.new"
    ssh-keyscan -T 10 -t ed25519 10.40.0.4 >> "$KNOWN_HOSTS.new"
    mv "$KNOWN_HOSTS.new" "$KNOWN_HOSTS"
    ssh-keygen -lf "$KNOWN_HOSTS"

    FEED_KEY="$(ssh $SSH_OPTS aisec@10.40.0.4 'cat ~/.ssh/aisec-feed.pub')"
    ssh $SSH_OPTS aisec@10.40.0.36 "sudo /usr/local/lib/aisec/install/install-feed-account.sh '$FEED_KEY' &&
      sudo grep -c . /home/aisec-feed/.ssh/authorized_keys"
    WORKER_KEY="$(grep '^10.40.0.36 ' "$KNOWN_HOSTS" | sed 's/^10.40.0.36/aisec-worker,10.40.0.36/')"
    ssh $SSH_OPTS aisec@10.40.0.4 "echo '$WORKER_KEY' >> ~/.ssh/known_hosts &&
      ssh -n -i ~/.ssh/aisec-feed -o BatchMode=yes -o StrictHostKeyChecking=yes aisec-feed@aisec-worker id; echo \"exit \$?\""
    ```

    Expected: the orchestrator's fingerprint from the scan equals the one from the serial log. Then `1`, the new feed key, and `refused: not a feed request` with `exit 2`. The install replaces the file, so the old feed key, whose private half died with the old VM, is no longer trusted.

30. Confirm first boot and node signing, then install the pending updates on both VMs.

    ```bash
    ssh $SSH_OPTS aisec@10.40.0.4 '
      ls /var/lib/aisec-first-boot.done; cloud-init status; sudo ls /run/aisec
      sudo k3s kubectl get nodes
      sudo tailscale lock status | head -4'
    ```

    Expected: the marker file, `status: done`, an empty `/run/aisec`, the node `Ready`, and `This node is accessible under Tailnet Lock`. If the node is locked out, sign it from a signing device with `tailscale lock sign <node-key>`. That fallback has not been run.

    Then run step 20 on the orchestrator and the last two lines of step 21 on the worker.

    Expected: nothing left from the `-security` suite on either VM.

31. Stage the inputs again, then run every check.

    Run step 2 and step 3 of the [model server runbook](model-server.md), and step 2 and the download half of step 3 of the [agent runtime runbook](agent-runtime.md). Do not push: the worker still has its model and its agent runtime.

    ```bash
    ssh $SSH_OPTS aisec@10.40.0.4 'du -sh feed'
    validation/platform-checks.sh
    ```

    Expected: one `ok` line per file, about `9.0G`, and every check passes. `K.5` and `K.6` pass without steps 17 and 18, because first boot applies both.

## Rotate a credential

Each rotation was run once on 2026-10-11. The commands are that run, condensed, except the feed key and the operator key, rewritten on 2026-10-16 for certificates and the feed account and not run in that form. Each ends by proving that the old credential no longer works.

### Feed key

Make the new key on the orchestrator, install it on the worker as the operator, then prove that the old one is refused. The feed key cannot change its own key line: the file is root's ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)).

```bash
ssh $SSH_OPTS aisec@10.40.0.4 'cd ~/.ssh && ssh-keygen -q -t ed25519 -N "" -C aisec-feed -f aisec-feed.new'
NEW="$(ssh $SSH_OPTS aisec@10.40.0.4 'cat ~/.ssh/aisec-feed.new.pub')"
ssh $SSH_OPTS aisec@10.40.0.36 "sudo /usr/local/lib/aisec/install/install-feed-account.sh '$NEW'"
ssh $SSH_OPTS aisec@10.40.0.4 '
  cd ~/.ssh; S="ssh -n -o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes"
  $S -i aisec-feed.new aisec-feed@aisec-worker id; echo "new: exit $?"
  $S -i aisec-feed aisec-feed@aisec-worker id; echo "old: exit $?"
  mv aisec-feed.new aisec-feed; mv aisec-feed.new.pub aisec-feed.pub'
```

Expected: `new: exit 2`, the feed command refusing, then `Permission denied (publickey)` and `old: exit 255`. Every target that trusts the feed key needs the same swap.

### Cluster token

Run on the orchestrator as root. K3s restarts once. The backup is what makes a failed rotation recoverable, and it holds the old token and the datastore, so it is deleted at the end.

```bash
B=/root/k3s-token-rotation-backup; install -d -m 0700 $B
systemctl stop k3s
cp -a /var/lib/rancher/k3s/server/db /var/lib/rancher/k3s/server/token /var/lib/rancher/k3s/server/cred $B/
systemctl start k3s
umask 077; openssl rand -hex 32 > $B/new-token
k3s token rotate -t "$(cat /var/lib/rancher/k3s/server/token)" --new-token "$(cat $B/new-token)"
systemctl restart k3s
k3s kubectl get nodes
old=$(sed 's/.*:://' $B/token | cut -d: -f2); new=$(cat $B/new-token)
curl -sk -o /dev/null -w '%{http_code}\n' -u "server:$old" https://127.0.0.1:6443/v1-k3s/server-bootstrap
curl -sk -o /dev/null -w '%{http_code}\n' -u "server:$new" https://127.0.0.1:6443/v1-k3s/server-bootstrap
rm -rf $B
```

Expected: `Token rotated, restart k3s nodes with new token`, the node `Ready` after the restart, `401` for the old token, and anything other than `401` for the new one. The rotation rewrites `/var/lib/rancher/k3s/server/token` itself, so the restart needs no `--token`. A joined agent would need the new token before its next restart. None is joined yet.

### Operator SSH key

The VMs trust the certificate authority, not the key, so nothing changes on a VM. Make the new key, sign a certificate for it with step 3 of the [SSH certificates runbook](ssh-certificates.md), and stop signing for the old one. A certificate for the old key works until it expires, at most 12 hours. To end it sooner, revoke its serial with step 14 of that runbook.

```bash
ssh-keygen -q -t ed25519 -N "" -C aisec-operator -f "$CRED_DIR/operator_ed25519.new"
# Sign the new key as in step 3, then:
for host in 10.40.0.4 10.40.0.36; do
  ssh $SSH_OPTS -i "$CRED_DIR/operator_ed25519.new" -o CertificateFile="$CRED_DIR/operator_ed25519.new.aisec-cert.pub" \
    -o IdentitiesOnly=yes aisec@$host hostname
done
# In infra/platform/terraform.tfvars, set operator_ssh_public_key to the new public key.
(cd infra/platform && source "$CRED_DIR/platform.env" && terraform plan -detailed-exitcode)
```

Expected: each hostname with the new key. The plan reports `No changes` and exits `0`, because the VM ignores changes to the key.

The authority itself is replaced with step 15 of the [SSH certificates runbook](ssh-certificates.md).

### Mesh VPN node key

Needs a new single-use, tagged auth key from the admin console. The session drops while the orchestrator rejoins, so the command runs detached.

```bash
printf '%s' 'REPLACE_WITH_AUTH_KEY' | ssh $SSH_OPTS aisec@10.40.0.4 '
  sudo install -d -m 0700 /run/aisec
  sudo sh -c "umask 077; cat > /run/aisec/tailscale-auth-key"
  sudo sh -c "nohup sh -c \"sleep 2; tailscale up --force-reauth --auth-key=file:/run/aisec/tailscale-auth-key --hostname=aisec-orchestrator --advertise-routes=10.40.0.0/20,10.50.0.0/20 --accept-dns=false; rm -f /run/aisec/tailscale-auth-key\" >/dev/null 2>&1 &"'
ssh $SSH_OPTS aisec@10.40.0.4 'sudo tailscale status --json | grep -m1 PublicKey; sudo ls /run/aisec'
ssh $SSH_OPTS aisec@10.40.0.36 hostname
```

Expected: a different `nodekey:` value from before, an empty `/run/aisec`, and `aisec-worker`. On this build the node kept its address, its tag, and its approved routes. If the worker is unreachable, approve the routes again in the admin console.

## Not covered yet

- A CIS benchmark run for the operating system. No tool has a profile for this release yet. `sudo pro enable usg` on an attached machine says so.
- Updates for the targets. The package proxy serves the worker only.
- Signing a node after it has joined. The rebuild used a signed key. See step 4.
- A rebuild of both VMs at once, or of everything from an empty subscription.
- Removal. Destroying the VMs and the NAT gateway has not been run.
