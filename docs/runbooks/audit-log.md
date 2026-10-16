# Audit log and journal copies: operator procedure

Status: Implemented on 2026-10-16. Steps 1 to 10 were run that day on the live VMs, from commit `4218b0a`, and the results are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#rollout-of-the-log-copies). The archive steps have not been run. A first boot from the current templates, which runs the same installs, has not been run either.

Run these steps to copy the tool service's audit lines into an append-only file on the orchestrator, deploy the tool service so that its lines are numbered, and pull the worker's journal into a second append-only file. The design is [ADR 0019](../decisions/0019-how-the-audit-lines-and-the-worker-journal-are-copied.md). Storage and who can change it are on the [audit log page](../security/audit-log.md).

## Inputs and access

| Input | Notes |
| --- | --- |
| The tool service, deployed | The [tool service runbook](tool-service.md) |
| SSH to both VMs over the mesh VPN | `REPLACE_WITH_SSH` below stands for the operator's `ssh` command with its options, for example `ssh -F <config>` |
| The worker's pinned host key | In the operator's own `known_hosts` file, from the [platform compute runbook](platform-compute.md). Not read from the network |
| A checkout of this repository on the workstation, clean, at the commit to install | The files are in `platform/logs/`, `platform/tool-service/`, and `worker/log-export/` |
| No job active | The deploy in step 5 replaces the tool service pod |

## The audit copier

1. Copy the files to the orchestrator. Run from the repository root.

   ```bash
   tar -cf - platform policies | REPLACE_WITH_SSH aisec-orchestrator \
     'rm -rf ~/feed/tool-service && mkdir -p ~/feed/tool-service && tar -C ~/feed/tool-service -xf -'
   ```

   Expected: no output.

2. Install the copier.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/tool-service/platform/logs/install-audit-copy.sh'
   ```

   Expected: `apt` installs `acl`, and systemd creates the link for `aisec-audit-copy.service`.

3. Read what the install made.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'F=/var/log/aisec/tool-audit.jsonl
     sudo stat -c "%U %G %a" $F; sudo lsattr $F; sudo getfacl -p /var/log/pods | grep aisec
     systemctl is-active aisec-audit-copy'
   ```

   Expected: `root aisec-audit-copy 620`, an `a` in the attributes, `default:group:aisec-audit-copy:r-x`, and `active`.

4. Compare the copy with the pod's log.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo wc -l /var/log/aisec/tool-audit.jsonl
     sudo sh -c "wc -l /var/log/pods/tool-services_*/tool-service/0.log"'
   ```

   Expected: the same count in both, on an orchestrator whose pod has not rotated its log.

5. Deploy the tool service from the copied manifest. It waits for two copier passes before it replaces the pod.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/tool-service/platform/tool-service/deploy.sh ~/feed/tool-service'
   ```

   Expected: `deployment "tool-service" successfully rolled out`, and the new pod with the digest the manifest names.

6. Check that the new pod's log is read. Make one call without a token from the worker, then read the file's last line.

   ```bash
   REPLACE_WITH_SSH aisec-worker "curl -s -o /dev/null -w 'HTTP %{http_code}\n' --max-time 10 \
     --cacert /etc/aisec/tool-service.crt -X POST -d '{}' https://tool-service.aisec.internal:30443/mcp"
   sleep 4
   REPLACE_WITH_SSH aisec-orchestrator 'sudo tail -n 1 /var/log/aisec/tool-audit.jsonl
     sudo sh -c "getfacl -p /var/log/pods/tool-services_*/tool-service/0.log" | grep aisec'
   ```

   Expected: `HTTP 401`, a line with `"seq":` and `"reason":"no token, or a malformed one"`, and `group:aisec-audit-copy:r-x` on the new pod's log.

## The journal pull

7. Copy the files to both VMs.

   ```bash
   tar -cf - platform policies | REPLACE_WITH_SSH aisec-orchestrator \
     'rm -rf ~/feed/tool-service && mkdir -p ~/feed/tool-service && tar -C ~/feed/tool-service -xf -'
   tar -cf - worker/log-export | REPLACE_WITH_SSH aisec-worker \
     'rm -rf ~/feed/log-export && mkdir -p ~/feed/log-export && tar -C ~/feed/log-export -xf -'
   ```

   Expected: no output.

8. Install the puller on the orchestrator, with the worker's host key from the pinned file. It prints the export key's public half.

   ```bash
   HOST_KEY=$(ssh-keygen -F REPLACE_WITH_WORKER_ADDRESS -f REPLACE_WITH_KNOWN_HOSTS_FILE | grep -v '^#' \
     | awk '$2 == "ssh-ed25519" {print $2, $3; exit}')
   EXPORT_KEY=$(REPLACE_WITH_SSH aisec-orchestrator \
     "sudo ~/feed/tool-service/platform/logs/install-journal-pull.sh '$HOST_KEY'" | tail -n 1)
   echo "$EXPORT_KEY"
   ```

   Expected: systemd creates the link for `aisec-journal-pull.timer`, then one line starting with `ssh-ed25519` and ending with `aisec-journal-pull`.

9. Install the export account on the worker, trusting that key.

   ```bash
   REPLACE_WITH_SSH aisec-worker "sudo ~/feed/log-export/worker/log-export/install-log-export.sh '$EXPORT_KEY'"
   ```

   Expected: no output.

10. Run one pull now, then every check.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo systemctl start aisec-journal-pull.service
      sudo journalctl -u aisec-journal-pull -n 3 --no-pager -o cat; sudo wc -l /var/log/aisec/worker-journal.jsonl'
    validation/platform-checks.sh
    ```

    Expected: `copied N lines` and a line count. Every check passes, including `L.1` to `L.7`, `J.1` to `J.9`, and `T.2`. `U.1` or `U.5` can fail if security updates are pending.

## Archive before a rebuild

A rebuild of the orchestrator deletes both files. Copy them off first.

11. Copy both files to the workstation.

    ```bash
    for f in tool-audit worker-journal; do
      REPLACE_WITH_SSH aisec-orchestrator "sudo cat /var/log/aisec/$f.jsonl" > "REPLACE_WITH_ARCHIVE_DIR/$f-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
    done
    ```

    Expected: two files in the archive folder, with the same line counts as `sudo wc -l` reports on the orchestrator.

12. Record the archive's SHA-256 next to it.

    ```bash
    sha256sum REPLACE_WITH_ARCHIVE_DIR/*.jsonl > REPLACE_WITH_ARCHIVE_DIR/SHA256SUMS
    ```

    Expected: one line per file.
