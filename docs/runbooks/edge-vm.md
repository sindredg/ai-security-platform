# Edge VM: operator procedure

Status: Implemented on 2026-10-17. Run once, on the live platform, between 18:40 and 19:59 UTC. Results are in the [milestone 3a worklog](../worklogs/0004-edge-network-and-monitoring.md#the-edge-vm). Steps 5, 6, 8, 10, and 13 ran from scripts with the same commands, and are written here in fewer lines. They have not run in this form. Step 10 is shorter than the two window tests in the worklog. The rebuild note at the end is reasoned from the template and has not run. The close test in step 10 ran on 2026-10-23 from a script with the same checks, not in this form ([worklog](../worklogs/0003-toolchain-integration.md#fix-closing-a-fetch-window-ends-its-tunnels)). Also on 2026-10-23, Docker Hub left the list ([ADR 0033](../decisions/0033-k3s-system-images-from-the-release-archive.md)), and step 10 pulls Argo's executor from quay.io instead. That pull has not run.

This builds the edge VM in Denmark East, moves the package proxy onto it, and takes the orchestrator's way out away ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)). It is the second of two stages of the edge network. The first is the [router](mesh-router.md).

The orchestrator keeps its own NAT gateway until step 8. Until then each step can be undone, and the orchestrator can still fetch without the edge.

## Inputs and access

| Input | Notes |
| --- | --- |
| The platform deployment identity | `REPLACE_WITH_CRED_DIR/platform.env`, as in the [platform compute runbook](platform-compute.md) |
| `az`, signed in as the operator | Read-only queries, the serial log, and the checks |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md), with `source-address=10.45.0.32/27,100.64.0.0/10` |
| A checkout of this repository, at two commits | `REPLACE_WITH_EDGE_COMMIT`, the commit that adds the edge, and `REPLACE_WITH_CLOSE_COMMIT`, the one that closes the orchestrator's way out. A fresh build from scratch needs only the second |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-worker`, `aisec-router`, and `aisec-edge` (`10.45.0.4`) |

## Before the build

1. Check that the edge's size is offered in Denmark East, zone 1, that the region has room, and which image version is the newest release.

   ```bash
   az vm image list --publisher Canonical --offer ubuntu-26_04-lts --sku server --all -l denmarkeast \
     --query "[?offer=='ubuntu-26_04-lts' && sku=='server'].version" -o tsv | sort -V | tail -n 1
   az vm list-skus -l denmarkeast --size Standard_B2als_v2 --all \
     --query "[].{zones:locationInfo[0].zones, restrictions:restrictions}" -o json
   az vm list-usage -l denmarkeast --query "[?name.value=='cores'].{used:currentValue, limit:limit}" -o table
   ```

   Expected: one image version, the same as `image_version` in `infra/platform/variables.tf` or newer. Zone `1` listed, restrictions `[]`, and at least 2 cores free. The router uses the other 2.

## Build

2. Apply from the edge commit, after reading the plan. Run in `infra/platform` as the platform identity.

   ```bash
   cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/platform
   git checkout REPLACE_WITH_EDGE_COMMIT
   source REPLACE_WITH_CRED_DIR/platform.env
   terraform apply
   ```

   Expected: `6 to add, 2 to change, 0 to destroy`. The additions are the edge subnet, its security group and association, the NAT gateway association, and the edge's interface and VM. The changes add one rule each to the orchestrator's and the worker's security groups, for TCP 3128 to `10.45.0.0/27`. Nothing else in either group changes.

3. Take the edge's host key from the serial log, and compare it with the one it offers. First boot takes about two minutes after the apply returns.

   ```bash
   az vm boot-diagnostics get-boot-log -g rg-aisec-platform -n vm-aisec-edge -o tsv \
     | grep -a -o 'SHA256:[A-Za-z0-9+/]* root@aisec-edge (ED25519)' | sort -u
   ssh-keyscan -T 10 -t ed25519 10.45.0.4 > REPLACE_WITH_KNOWN_HOSTS_FILE.edge
   ssh-keygen -lf REPLACE_WITH_KNOWN_HOSTS_FILE.edge
   ```

   Expected: the same fingerprint twice. Add the line to the known hosts file `REPLACE_WITH_SSH` uses. The scan goes through the router, which routes `10.45.0.0/27`.

4. Confirm the edge's first boot.

   ```bash
   REPLACE_WITH_SSH aisec-edge '
     ls /var/lib/aisec-first-boot.done; cloud-init status
     systemctl is-active squid; ss -ltn | grep 3128
     sudo aisec-fetch-window status
     apt list --upgradable 2>/dev/null | grep -c -- -security'
   ```

   Expected: the marker exists, `status: done`, `active`, one listener on `10.45.0.4:3128`, `closed`, and `0`.

## Move the clients

5. Point the worker's `apt` at the edge.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'sudo sh -c "
     printf \"%s\n\" \"Acquire::http::Proxy \\\"http://10.45.0.4:3128\\\";\" > /etc/apt/apt.conf.d/90aisec-proxy
     apt-get update -q"'
   ```

   Expected: `apt-get update` exits 0 and lists `archive.ubuntu.com` and `security.ubuntu.com`.

6. Point the orchestrator's `apt`, the operator's sessions, and containerd at the edge, and restart K3s. Pods keep running through the restart.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo bash -s' <<'EOF'
   set -eu
   p=http://10.45.0.4:3128
   printf '%s\n' "Acquire::http::Proxy \"$p\";" > /etc/apt/apt.conf.d/90aisec-proxy
   printf '%s\n' "http_proxy=$p" "https_proxy=$p" "no_proxy=localhost,127.0.0.1,10.40.0.0/20,aisec-worker" >> /etc/environment
   printf '%s\n' "CONTAINERD_HTTP_PROXY=$p" "CONTAINERD_HTTPS_PROXY=$p" \
     "CONTAINERD_NO_PROXY=localhost,127.0.0.0/8,10.0.0.0/8" >> /etc/systemd/system/k3s.service.env
   systemctl restart k3s
   sleep 60
   k3s kubectl get nodes --no-headers
   apt-get update -q >/dev/null && echo "apt ok"
   curl -s -o /dev/null -w '%{http_connect}\n' --max-time 10 -x "$p" https://github.com/
   EOF
   ```

   Expected: the node `Ready`, `apt ok`, and `403` for the tunnel, because no fetch window is open. A rebuilt orchestrator has all three settings from its template and skips this step.

## Close the orchestrator's way out

7. Apply from the close commit, after reading the plan.

   ```bash
   cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/platform
   git checkout REPLACE_WITH_CLOSE_COMMIT
   terraform apply
   ```

   Expected: `0 to add, 2 to change, 4 to destroy`. The destroyed resources are the Sweden Central NAT gateway, its public address, and both associations. The orchestrator's group loses `allow-https-to-internet`, `allow-http-to-internet`, and `allow-package-proxy-from-worker`, and gains `deny-to-internet` and `deny-to-azure-dns`. The worker's loses `allow-package-proxy-to-orchestrator`.

8. Remove Squid from the orchestrator. Nothing uses it now, and a rebuilt orchestrator does not have it.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo sh -c "
     DEBIAN_FRONTEND=noninteractive apt-get purge -y -q squid squid-common squid-langpack
     rm -rf /etc/systemd/system/squid.service.d && systemctl daemon-reload
     ss -ltn | grep -c :3128"'
   ```

   Expected: the purge removes three packages, and `0` listeners on 3128.

## Open a fetch window

9. Open a window before anything on the orchestrator fetches from GitHub, a registry, Hugging Face, or PyPI: a model or agent build, a new image digest, a K3s upgrade, or a rebuilt orchestrator's first boot. A pod restart does not need one.

   ```bash
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 30'
   # ... the fetch, on the orchestrator ...
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close'
   ```

   Expected: `open for 30 minutes, until <UTC time>, by aisec`, then `closed, by aisec`. Without `close`, the timer closes it at the time printed. The longest window is 60 minutes. A close that ends a tunnel still open prints `open tunnels ended: <n>` before `closed`. A download on port 80 goes on.

10. Test the window: one small fetch from each listed host, then the log, then a short window that the timer closes during a download.

    ```bash
    REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 10'
    REPLACE_WITH_SSH aisec-orchestrator '
      for url in https://raw.githubusercontent.com/k3s-io/k3s/v1.36.5%2Bk3s1/install.sh \
                 https://github.com/k3s-io/k3s/releases/download/v1.36.5%2Bk3s1/k3s \
                 https://huggingface.co/Qwen/Qwen3.5-4B/resolve/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/config.json \
                 https://download.pytorch.org/whl/jinja2-3.1.6-py3-none-any.whl; do
        curl -s -L -r 0-0 -o /dev/null -w "%{http_code} %{url_effective}\n" "$url" | cut -c1-80
      done'
    IMAGE=$(grep -o 'quay.io/argoproj/argoexec@sha256:[0-9a-f]*' REPLACE_WITH_PLATFORM_CHECKOUT/platform/argo/argo.yaml)
    REPLACE_WITH_SSH aisec-orchestrator "sudo k3s crictl pull $IMAGE | tail -n 1"
    REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close
      sudo tail -n 40 /var/log/squid/access.log | awk "\$3 == \"10.40.0.4\" {print \$4, \$7}" | sort | uniq -c'
    REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 1'
    REPLACE_WITH_SSH aisec-orchestrator 'curl -s -L --limit-rate 20k --max-time 120 -o /dev/null -w "%{http_code} %{size_download}\n" \
      https://github.com/k3s-io/k3s/releases/download/v1.36.5%2Bk3s1/k3s; echo "exit $?"'
    REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window status; sudo journalctl -t aisec-fetch-window -n 2 -o cat
      sudo tail -n 5 /var/log/squid/access.log | awk "\$3 == \"10.40.0.4\" {print \$2, \$4, \$7}"'
    ```

    Expected: `206` for each URL, `Image is up to date` for Argo's executor, which containerd already holds, so the pull only reads its manifest, `TCP_TUNNEL/200` for each host in the log and no `TCP_DENIED`. Then the held download ends about a minute after the open, `exit 55`, when the timer closes the window. `closed`, then `open tunnels ended: 1` and `closed, by timer or root`, and a `TCP_TUNNEL/200` line of about 60000 milliseconds for `release-assets.githubusercontent.com:443`. A `TCP_DENIED` line inside a window names a host the list lacks: add it to `edge/fetch-hosts` and install the list as in step 13.

## Verify

11. Run every check, with no window open.

    ```bash
    AISEC_SSH="REPLACE_WITH_SSH" AISEC_ORCH=aisec-orchestrator AISEC_WORK=aisec-worker AISEC_ROUTER=aisec-router \
      AISEC_EDGE=aisec-edge AISEC_USER_CA=REPLACE_WITH_CRED_DIR/aisec-user-ca.pub validation/platform-checks.sh
    ```

    Expected: every check passes. `E.12` to `E.14` time out, `P.15` reads 403, `P.16` reads no window, and `Z.2` reads one public address.

12. Confirm the platform root has converged.

    ```bash
    (cd REPLACE_WITH_PLATFORM_CHECKOUT/infra/platform && source REPLACE_WITH_CRED_DIR/platform.env && terraform plan -detailed-exitcode)
    ```

    Expected: `No changes` and exit `0`.

## Change the command or the list

13. The edge's template installs `edge/aisec-fetch-window` and `edge/fetch-hosts` on first boot only. A change to either reaches the running edge through a copy as the operator and an install as root. `sudo install` cannot read standard input.

    ```bash
    for f in aisec-fetch-window:/usr/local/sbin/aisec-fetch-window:0700 fetch-hosts:/etc/squid/aisec-fetch-hosts:0644; do
      IFS=: read -r src dest mode <<<"$f"
      REPLACE_WITH_SSH aisec-edge "t=\$(mktemp) && cat > \"\$t\" && sudo install -o root -g root -m $mode \"\$t\" $dest && rm -f \"\$t\"" \
        < REPLACE_WITH_PLATFORM_CHECKOUT/edge/$src
    done
    REPLACE_WITH_SSH aisec-edge 'sudo systemctl reload squid && systemctl is-active squid'
    ```

    Expected: `active`. `P.17` and `P.18` pass, and failed before.

## Rebuild the orchestrator

The orchestrator's first boot fetches K3s and the archive of its system images from GitHub, through the edge ([ADR 0033](../decisions/0033-k3s-system-images-from-the-release-archive.md)). Open a window of 60 minutes (step 9) before the apply that replaces it, and close it once `K.10` passes. Without a window, first boot stops at the K3s download and writes no marker.
