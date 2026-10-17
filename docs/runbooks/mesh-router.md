# Mesh VPN router: operator procedure

Status: Implemented on 2026-10-17. Run once, on the live platform, between 13:40 and 14:35 UTC. Results are in the [milestone 3a worklog](../worklogs/0004-edge-network-and-monitoring.md#the-router). Steps 1, 5, 11, 12, and 13 were corrected after that run to the commands that ran, and step 17 was added for a failure it found. The `unattended-upgrade` line in the router's first boot was added after it, and has not run on a first boot.

This builds the router VM in Denmark East, moves the mesh VPN onto it, and takes the orchestrator off the mesh ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md)). It is the first of two stages of the edge network. The second, the edge VM with Squid and the platform's way out ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)), has [its own runbook](edge-vm.md).

The orchestrator and the router are both on the mesh until step 13. Until then, administration through the orchestrator keeps working, so each step can be undone.

## Inputs and access

| Input | Notes |
| --- | --- |
| The platform deployment identity | `REPLACE_WITH_CRED_DIR/platform.env`, as in the [platform compute runbook](platform-compute.md) |
| `az`, signed in as the operator | Read-only queries, the serial log, and the checks |
| Mesh VPN admin console, administrator | To edit the access policy, generate an auth key, approve routes, and remove a node |
| A device that holds a Tailnet Lock signing key | To sign the auth key |
| The operator's SSH certificate authority | `REPLACE_WITH_CA_KEY`. Step 4 signs a certificate for the change-over |
| A checkout of this repository at the commit to apply | `REPLACE_WITH_PLATFORM_CHECKOUT` |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options, as in the [SSH certificates runbook](ssh-certificates.md). Host aliases `aisec-orchestrator`, `aisec-worker`, and `aisec-router` |

## Before the build

1. Check that the router's size is offered in Denmark East, zone 1, that the region has room, and which image version is the newest release.

   ```bash
   az vm image list --publisher Canonical --offer ubuntu-26_04-lts --sku server --all -l denmarkeast \
     --query "[?offer=='ubuntu-26_04-lts' && sku=='server'].version" -o tsv | sort -V | tail -n 1
   az vm list-skus -l denmarkeast --resource-type virtualMachines \
     --query "[?name=='Standard_B2ats_v2'].{zones:locationInfo[0].zones, restrictions:restrictions}" -o json
   az vm list-usage -l denmarkeast \
     --query "[?name.value=='cores' || name.value=='standardBASv2Family'].{name:name.value, used:currentValue, limit:limit}" -o table
   ```

   Expected: one image version, the same as `image_version` in `infra/platform/variables.tf` or newer. Zone `1` listed, restrictions `[]`, and at least 2 cores free in each row.

   `--offer` and `--sku` match as prefixes, so without the filter the list also holds Canonical's daily builds (`ubuntu-26_04-lts-daily`) and other SKUs such as `server-gen1`. A version from those is refused at apply with `PlatformImageNotFound`, as on 2026-10-17.

2. In the admin console, add the router's tag and grants to the access policy. Keep the orchestrator's entries for now: they go in step 15.

   ```json
   {
       "tagOwners": {
           "tag:aisec-orchestrator": ["autogroup:admin"],
           "tag:aisec-router":       ["autogroup:admin"],
       },
       "grants": [
           {
               "src": ["autogroup:member"],
               "dst": ["tag:aisec-orchestrator"],
               "ip":  ["tcp:22", "tcp:6443"],
           },
           {
               "src": ["autogroup:member"],
               "dst": ["10.40.0.0/20", "10.50.0.0/20"],
               "ip":  ["tcp:22", "tcp:6443"],
           },
           {
               "src": ["autogroup:member"],
               "dst": ["tag:aisec-router", "10.45.0.0/27"],
               "ip":  ["tcp:22"],
           },
       ],
   }
   ```

   Expected: the console saves the policy. Nothing grants `tag:aisec-router` a destination.

3. Generate an auth key and sign it.

   | Setting | Value |
   | --- | --- |
   | Reusable | Off |
   | Ephemeral | Off |
   | Tags | `tag:aisec-router` |
   | Expiration | 1 day |

   On the signing device:

   ```bash
   tailscale lock sign REPLACE_WITH_AUTH_KEY
   ```

   Expected: a longer key. Keep only that one, outside the repository, for step 5. It ends up in the VM's custom data and in state, which is why it is single use.

4. Sign a certificate that works from both routing paths. Until step 13, sessions reach the worker either from the orchestrator or from the router.

   ```bash
   ssh-keygen -q -s REPLACE_WITH_CA_KEY -I "aisec-operator-$(date -u +%F)" -n aisec-operator \
     -z "$(date -u +%s)" -V -5m:+11h55m \
     -O clear -O permit-pty -O permit-port-forwarding \
     -O source-address=100.64.0.0/10,10.40.0.4/32,10.45.0.32/27 \
     REPLACE_WITH_OPERATOR_KEY.pub
   mv REPLACE_WITH_OPERATOR_KEY-cert.pub REPLACE_WITH_OPERATOR_KEY.aisec-cert.pub
   ssh-keygen -L -f REPLACE_WITH_OPERATOR_KEY.aisec-cert.pub | grep -A1 source-address
   ```

   Expected: `source-address 100.64.0.0/10,10.40.0.4/32,10.45.0.32/27`.

## Build

5. Apply with the signed key, after reading the plan. Run in `infra/platform` as the platform identity.

   ```bash
   cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/platform
   source REPLACE_WITH_CRED_DIR/platform.env
    TF_VAR_tailscale_auth_key='REPLACE_WITH_SIGNED_AUTH_KEY' terraform apply
   ```

   The line starts with a space, which keeps it out of the shell history with Ubuntu's default `HISTCONTROL`. `terraform apply` shows the plan and waits for `yes`, and writes no plan file that would hold the key. Read the plan before typing `yes`.

   Expected: `13 to add, 2 to change, 0 to destroy`. The additions are the edge network, the router subnet, its security group and association, the peerings from the edge to the platform and to the targets and from the platform to the edge, the NAT gateway with its address and two associations, and the router's interface and VM. The changes are the orchestrator and worker security groups: `allow-ssh-from-router` on each, and new descriptions on the orchestrator's two internet rules. The platform-to-targets peering moves to a new address in state and is not replaced.

   The edge-to-targets peering stays `Initiated` until the target root adds its half, with `edge_virtual_network_id` set ([network foundation](network-foundation.md), step 8).

6. Take the router's host key from the serial log. First boot takes about two minutes after the apply returns.

   ```bash
   az vm boot-diagnostics get-boot-log -g rg-aisec-platform -n vm-aisec-router -o tsv \
     | grep -a -o 'SHA256:[A-Za-z0-9+/]* root@aisec-router (ED25519)' | sort -u
   ```

   Expected: one fingerprint. In the admin console, `aisec-router` is listed with `tag:aisec-router`, signed, and with three routes waiting for approval.

7. Approve the router's three routes in the admin console. The orchestrator still advertises two of them, and stays the primary router for those.

   Expected: `10.40.0.0/20`, `10.45.0.0/27`, and `10.50.0.0/20` approved on `aisec-router`.

8. Pin the host key and confirm the router's first boot.

   ```bash
   ssh-keyscan -T 10 -t ed25519 REPLACE_WITH_ROUTER_MESH_ADDRESS > REPLACE_WITH_KNOWN_HOSTS_FILE.router
   ssh-keygen -lf REPLACE_WITH_KNOWN_HOSTS_FILE.router
   # Add the line to the known hosts file REPLACE_WITH_SSH uses, under the alias aisec-router.
   REPLACE_WITH_SSH aisec-router '
     ls /var/lib/aisec-first-boot.done; cloud-init status; ls /run/aisec
     systemctl is-active tailscaled aisec-mss-clamp
     sudo tailscale lock status | tail -n 1
     tr "\0" " " < /proc/$(pidof tailscaled)/cmdline; echo'
   ```

   Expected: the fingerprint from step 6. The marker exists, `status: done`, `/run/aisec` empty, both units `active`, `This node is accessible under Tailnet Lock`, and `--no-logs-no-support` on the agent's command line.

## Move the routes

9. Stop the orchestrator advertising its routes. The session that runs this goes through the orchestrator's own routes, so the change runs detached and the session drops.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo systemd-run --on-active=5 --unit=aisec-routes-off tailscale set --advertise-routes='
   ```

   Expected: within a minute, the console shows the router as the primary for `10.40.0.0/20` and `10.50.0.0/20`.

10. Log in through the router, and see that the worker and the orchestrator name it as the client.

    ```bash
    REPLACE_WITH_SSH aisec-worker 'echo "$SSH_CLIENT"'
    REPLACE_WITH_SSH aisec-orchestrator 'echo "$SSH_CLIENT"'
    ```

    Expected: `10.45.0.36` and a port, twice.

    To go back: `tailscale set --advertise-routes=10.40.0.0/20,10.50.0.0/20` on the orchestrator through the serial console, or through the router once it works.

11. Reach the Kubernetes API through an SSH tunnel to the orchestrator. Without a kubeconfig on the workstation, a request without credentials shows the path.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /var/lib/rancher/k3s/server/tls/server-ca.crt' > k3s-server-ca.crt
    REPLACE_WITH_SSH -f -N -o ExitOnForwardFailure=yes -L 16443:127.0.0.1:6443 aisec-orchestrator
    curl -s -o /dev/null -w 'tls_verify=%{ssl_verify_result} http=%{http_code}\n' --cacert k3s-server-ca.crt https://127.0.0.1:16443/version
    ss -ltnp | grep 16443   # then kill that ssh process by its ID
    ```

    Expected: `tls_verify=0 http=401`. TLS verifies against the cluster's certificate authority for `127.0.0.1`, and the API server refuses an anonymous request. With a kubeconfig, `kubectl --server https://127.0.0.1:16443 get nodes` shows the node `Ready`. That form has not been run.

12. Check that failed logins through the router no longer block the orchestrator's own sessions to the worker ([#87](https://github.com/sindredg/ai-security-platform/issues/87)). Run four logins that fail, then the feed key and the journal pull from the orchestrator.

    ```bash
    ssh-keygen -q -t ed25519 -N "" -f throwaway
    for _ in 1 2 3 4; do
      ssh -F /dev/null -o UserKnownHostsFile=REPLACE_WITH_KNOWN_HOSTS_FILE -o BatchMode=yes -o IdentitiesOnly=yes -i throwaway aisec@10.40.0.36 true
    done
    REPLACE_WITH_SSH aisec-orchestrator 'sudo -u aisec ssh -n -i /home/aisec/.ssh/aisec-feed -o BatchMode=yes aisec-feed@aisec-worker id >/dev/null 2>&1; echo "feed=$?"'
    sleep 25
    REPLACE_WITH_SSH aisec-worker 'sudo journalctl -u ssh --since -5min -o cat | grep -E "penal|Accepted"'
    ```

    Expected: four `Permission denied (publickey)`. `feed=2`, the feed command refusing `id`. The worker's log has a penalty for `10.45.0.36`, the feed key accepted from `10.40.0.4` inside it, and no penalty for `10.40.0.4`. The `sleep` waits out the penalty, which also holds the next operator login.

## Take the orchestrator off the mesh

13. Remove the agent from the orchestrator. The session reaches it through the router now, so logging the agent out does not drop it. The unit runs detached anyway, so a dropped session cannot stop it halfway.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo systemd-run --unit=aisec-mesh-off --wait --collect --property=Type=oneshot bash -c "
      set -e
      tailscale logout
      apt-mark unhold tailscale
      DEBIAN_FRONTEND=noninteractive apt-get purge -y -q tailscale
      rm -f /etc/apt/sources.list.d/tailscale.list /usr/share/keyrings/tailscale-archive-keyring.gpg
      systemctl disable --now aisec-mss-clamp.service
      nft delete table inet aisec_mss || true
      rm -f /etc/systemd/system/aisec-mss-clamp.service /etc/aisec/mss-clamp.nft /etc/sysctl.d/90-aisec-router.conf
      systemctl daemon-reload"'
    REPLACE_WITH_SSH aisec-orchestrator 'dpkg-query -W -f="\${Status}\n" tailscale; ip -br link show tailscale0'
    ```

    Expected: `systemd-run` exits 0. `dpkg-query` prints nothing that ends in `ok installed`, and `Device "tailscale0" does not exist`. K3s sets IP forwarding itself, so the removed sysctl file changes nothing it needs.

14. Remove `aisec-orchestrator` in the admin console if it is still listed.

    Expected: the device list shows `aisec-router` and the operator's devices, and no other platform node.

15. Replace the access policy with its final form.

    ```json
    {
        "tagOwners": {
            "tag:aisec-router": ["autogroup:admin"],
        },
        "grants": [
            {
                "src": ["autogroup:member"],
                "dst": ["tag:aisec-router", "10.40.0.0/20", "10.45.0.0/27", "10.50.0.0/20"],
                "ip":  ["tcp:22"],
            },
        ],
        "tests": [
            {
                "src":    "REPLACE_WITH_OPERATOR_LOGIN",
                "proto":  "tcp",
                "accept": ["tag:aisec-router:22"],
                "deny":   ["tag:aisec-router:80", "tag:aisec-router:6443"],
            },
            {
                "src":   "tag:aisec-router",
                "proto": "tcp",
                "deny":  [
                    "REPLACE_WITH_OPERATOR_LOGIN:22",
                    "REPLACE_WITH_OPERATOR_LOGIN:80",
                    "REPLACE_WITH_OPERATOR_LOGIN:443",
                    "REPLACE_WITH_OPERATOR_LOGIN:445",
                    "REPLACE_WITH_OPERATOR_LOGIN:3389",
                ],
            },
        ],
    }
    ```

    Replace every `REPLACE_WITH_OPERATOR_LOGIN` first. The console accepts the placeholder, and with it the tests check a user who does not exist, so they pass whatever the grants say. The login is the `LoginName` of the operator's user:

    ```bash
    REPLACE_WITH_SSH aisec-router 'tailscale status --json' | python3 -c 'import json,sys; print(sorted({u["LoginName"] for u in json.load(sys.stdin)["User"].values()}))'
    ```

    Expected: the console saves it. Then the same policy with one more grant, from `tag:aisec-router` to `autogroup:member` on `tcp:22`, is refused with `test(s) failed for user: tag:aisec-router`. Do not keep that copy.

    The tests name single ports, because the policy language takes no port range in a test. They catch a grant that names the router's tag. Each operator device also runs with `shields-up`, which refuses every incoming connection whatever the policy says. Check it on each device: `tailscale debug prefs` shows `"ShieldsUp": true`.

16. Sign the day's certificates without the orchestrator's address from now on. In the certificate command of step 4, the option becomes:

    ```bash
    -O source-address=10.45.0.32/27,100.64.0.0/10
    ```

    Expected: `ssh-keygen -L` shows that value. A certificate from step 4 still works until it expires.

## Verify

17. Apply the router's pending security updates. The image is days old, and the router's first daily upgrade runs up to a day after boot. A router built from the current template runs this at first boot, so the step finds nothing.

    ```bash
    REPLACE_WITH_SSH aisec-router 'sudo unattended-upgrade -v | grep -E "^(Packages that will be upgraded|All upgrades installed|No packages found)"; apt list --upgradable 2>/dev/null | grep -c -- -security'
    ```

    Expected: `All upgrades installed` or `No packages found`, then `0`. The mesh agent is held and stays at its version.

18. Run every check.

    ```bash
    AISEC_SSH="REPLACE_WITH_SSH" AISEC_ORCH=aisec-orchestrator AISEC_WORK=aisec-worker AISEC_ROUTER=aisec-router \
      AISEC_USER_CA=REPLACE_WITH_CRED_DIR/aisec-user-ca.pub validation/platform-checks.sh
    ```

    Expected: every check passes. `A.11` reads `0 0`. The router's section passes, including `R.4` with three routes, `R.5`, and `Z.17`. `M.2` times out.

19. Confirm that every root has converged.

    ```bash
    (cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/platform && source REPLACE_WITH_CRED_DIR/platform.env && terraform plan -detailed-exitcode)
    ```

    Expected: `No changes` and exit `0`.
