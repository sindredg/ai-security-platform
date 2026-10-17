# Mesh VPN router: operator procedure

Status: Written on 2026-10-17, not run. The router is not built.

This builds the router VM in Denmark East, moves the mesh VPN onto it, and takes the orchestrator off the mesh ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md)). It is the first of two stages of the edge network. The second, the edge VM with Squid and the platform's way out ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)), has its own steps.

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

1. Check that the router's size is offered in Denmark East, zone 1, and that the region has room.

   ```bash
   az vm list-skus -l denmarkeast --resource-type virtualMachines \
     --query "[?name=='Standard_B2ats_v2'].{zones:locationInfo[0].zones, restrictions:restrictions}" -o json
   az vm list-usage -l denmarkeast \
     --query "[?name.value=='cores' || name.value=='standardBASv2Family'].{name:name.value, used:currentValue, limit:limit}" -o table
   ```

   Expected: zone `1` listed, restrictions `[]`, and at least 2 cores free in each row.

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

5. Plan with the signed key, read the plan, and apply it. Run in `infra/platform` as the platform identity.

   ```bash
   cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/platform
   source REPLACE_WITH_CRED_DIR/platform.env
   read -rs TF_VAR_tailscale_auth_key && export TF_VAR_tailscale_auth_key
   terraform plan -out=router.tfplan
   terraform apply router.tfplan
   rm router.tfplan
   unset TF_VAR_tailscale_auth_key
   ```

   Expected: `13 to add, 2 to change, 0 to destroy`. The additions are the edge network, the router subnet, its security group and association, the peerings from the edge to the platform and to the targets and from the platform to the edge, the NAT gateway with its address and two associations, and the router's interface and VM. The changes are the orchestrator and worker security groups: `allow-ssh-from-router` on each, and new descriptions on the orchestrator's two internet rules. The platform-to-targets peering moves to a new address in state and is not replaced. The saved plan holds the auth key, so it is deleted.

   The edge-to-targets peering stays `Initiated` until the target repository adds its half.

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

11. Reach the Kubernetes API through an SSH tunnel to the orchestrator.

    ```bash
    REPLACE_WITH_SSH -f -N -L 6443:127.0.0.1:6443 aisec-orchestrator
    kubectl --kubeconfig REPLACE_WITH_KUBECONFIG --server https://127.0.0.1:6443 get nodes
    ```

    Expected: the node `Ready`. The API server's certificate names `127.0.0.1`.

12. Check that failed logins through the router no longer block the orchestrator's own sessions to the worker ([#87](https://github.com/sindredg/ai-security-platform/issues/87)). Run four logins that fail, then the feed key and the journal pull from the orchestrator.

    ```bash
    for _ in 1 2 3 4; do
      ssh -o BatchMode=yes -o IdentitiesOnly=yes -i REPLACE_WITH_OPERATOR_KEY -o CertificateFile=none aisec@10.40.0.36 true
    done
    REPLACE_WITH_SSH aisec-orchestrator '
      sudo -u aisec ssh -n -i ~aisec/.ssh/aisec-feed -o BatchMode=yes aisec-feed@aisec-worker id; echo "feed=$?"
      sudo systemctl start aisec-journal-pull.service; systemctl show aisec-journal-pull.service -p Result'
    REPLACE_WITH_SSH aisec-worker 'sudo journalctl -u ssh --since -5min | grep -E "penalty|Accepted"'
    ```

    Expected: four refusals. `feed=2`, the feed command refusing `id`, and `Result=success`. The worker's log has a penalty for `10.45.0.36` and none for `10.40.0.4`.

## Take the orchestrator off the mesh

13. Remove the agent from the orchestrator. The session reaches it through the router now, so logging the agent out does not drop it. The unit runs detached anyway, so a dropped session cannot stop it halfway.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo systemd-run --unit=aisec-mesh-off bash -c "
      tailscale logout
      apt-mark unhold tailscale
      DEBIAN_FRONTEND=noninteractive apt-get purge -y -q tailscale
      rm -f /etc/apt/sources.list.d/tailscale.list /usr/share/keyrings/tailscale-archive-keyring.gpg
      systemctl disable --now aisec-mss-clamp.service
      nft delete table inet aisec_mss
      rm -f /etc/systemd/system/aisec-mss-clamp.service /etc/aisec/mss-clamp.nft /etc/sysctl.d/90-aisec-router.conf
      systemctl daemon-reload"'
    REPLACE_WITH_SSH aisec-orchestrator 'systemctl show aisec-mesh-off -p Result; dpkg-query -W tailscale; ip -br link show tailscale0'
    ```

    Expected: `Result=success`, `no packages found matching tailscale`, and `Device "tailscale0" does not exist`. K3s sets IP forwarding itself, so the removed sysctl file changes nothing it needs.

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

    Expected: the console saves it. A copy with a grant from `tag:aisec-router` to `autogroup:member` is refused with a failed test. Try that once, and do not save it.

    The tests name single ports, because the policy language takes no port range in a test. They catch a grant that names the router's tag. Each operator device also runs with `shields-up`, which refuses every incoming connection whatever the policy says. Check it on each device: `tailscale debug prefs` shows `"ShieldsUp": true`.

16. Sign the day's certificates without the orchestrator's address from now on. In the certificate command of step 4, the option becomes:

    ```bash
    -O source-address=10.45.0.32/27,100.64.0.0/10
    ```

    Expected: `ssh-keygen -L` shows that value. A certificate from step 4 still works until it expires.

## Verify

17. Run every check.

    ```bash
    AISEC_SSH="REPLACE_WITH_SSH" AISEC_ORCH=aisec-orchestrator AISEC_WORK=aisec-worker AISEC_ROUTER=aisec-router \
      AISEC_USER_CA=REPLACE_WITH_CRED_DIR/aisec-user-ca.pub validation/platform-checks.sh
    ```

    Expected: every check passes. `A.11` reads `0 0`. The router's section passes, including `R.4` with three routes, `R.5`, and `Z.17`. `M.2` times out.

18. Confirm that every root has converged.

    ```bash
    (cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/platform && source REPLACE_WITH_CRED_DIR/platform.env && terraform plan -detailed-exitcode)
    ```

    Expected: `No changes` and exit `0`.
