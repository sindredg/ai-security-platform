# Host audit: operator procedure

Status: Written on 2026-10-31, not run. The live run fills in this line.

The audit daemon and AIDE on the orchestrator and the worker ([ADR 0054](../decisions/0054-an-audit-daemon-and-aide-on-both-vms-with-their-records-off-the-machine.md)). Steps 1 to 8 install both on a built machine and show each catching something; steps 9 to 11 are what comes after: a new baseline, a rebuilt VM, and the removal. Results are in the [milestone 6 worklog](../worklogs/0007-operational-and-containment-drills.md#slice-8-the-host-audit).

## Inputs and access

| Input | Notes |
| --- | --- |
| SSH to the orchestrator and the worker | `REPLACE_WITH_SSH` stands for the operator's `ssh` command with its options; aliases `aisec-orchestrator` and `aisec-worker` |
| The platform deployment identity, for Terraform in `infra/platform` | The [platform compute runbook](platform-compute.md), inputs |
| The operator's sign-in to Azure | For the workspace and the alerts: `REPLACE_WITH_WS` and the `kql` function from the [monitoring runbook](monitoring.md), step 6 |
| A checkout of this repository on the workstation | For `platform/host-audit/`, the drill `validation/drills/host-audit.sh`, and the checks |
| The tunnel to the API server and Argo's command line, for step 6 | The [workflows runbook](workflows.md), inputs |
| No job running | The install and the first baseline read the whole scope |

## Install

1. Plan and apply the collection source and the three alert rules. Run in `infra/platform` as the platform identity, and read the plan before applying it.

   ```bash
   terraform plan -out REPLACE_WITH_PLAN
   terraform apply REPLACE_WITH_PLAN
   ```

   Expected: `Plan: 3 to add, 1 to change, 0 to destroy`: the rules `alert-aisec-audit-config-write`, `alert-aisec-aide-report`, and `alert-aisec-aide-check-missing`, and `dcr-aisec-system` with the `audit` source for `local6`. `aide-check-missing` fires within the hour: neither machine has sent a check line yet. It resolves after step 3.

2. Copy the drill to each VM and run it before the install. This is its fail side.

   ```bash
   for host in aisec-orchestrator aisec-worker; do
     REPLACE_WITH_SSH $host 'cat > host-audit.sh' < validation/drills/host-audit.sh
     REPLACE_WITH_SSH $host 'sudo bash host-audit.sh'
   done
   ```

   Expected: every probe `FAIL` on both VMs and `== 11 failed` twice. There is no daemon, no log, and no check command.

3. Copy `platform/host-audit` to each VM and run the install as root, with the VM's role.

   ```bash
   for host in orchestrator worker; do
     tar -C platform -cf - host-audit | REPLACE_WITH_SSH aisec-$host 'rm -rf host-audit && tar -xf -'
     REPLACE_WITH_SSH aisec-$host "sudo host-audit/install-host-audit.sh $host"
   done
   ```

   Expected, on each: the two package lines, `auditd 1:4.1.2-1build1` and `aide 0.19.2-3` as the archive served them on 2026-10-31; `enabled 1`, a `pid`, and `lost 0`; `rules loaded: 24` on the orchestrator and `27` on the worker; `syslog plugin: 1`; nothing from the configuration check; `baseline entries=N database=sha256:...`; and the timer's next run. The install's own writes under `/etc/audit`, `/etc/aisec`, `/usr/local/sbin`, and `/etc/systemd/system` are the first records with the key `aisec-config`, and fire `audit-config-write` within 15 minutes.

4. Copy the worker's baseline to the orchestrator, and compare.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'sudo cat /var/lib/aisec/aide/aide.db' |
     REPLACE_WITH_SSH aisec-orchestrator 'sudo sh -c "umask 077; cat > /var/lib/aisec/aide/worker-aide.db"'
   REPLACE_WITH_SSH aisec-worker 'sudo sha256sum /var/lib/aisec/aide/aide.db'
   REPLACE_WITH_SSH aisec-orchestrator 'sudo sha256sum /var/lib/aisec/aide/worker-aide.db'
   ```

   Expected: the same SHA-256 twice. `F.7` reads these two files.

5. Run the drill on each VM, and remove the copy.

   ```bash
   for host in aisec-orchestrator aisec-worker; do
     REPLACE_WITH_SSH $host 'sudo bash host-audit.sh; rm -f host-audit.sh'
   done
   ```

   Expected: every probe `PASS` and `== 0 failed` on both. The `write` probe's records fire `audit-config-write` again, and the `aide` probe's first check line, `added=1`, fires `aide-report`. The second check line, after the removal, reads `added=0 removed=0 changed=0`: the baseline was not rewritten.

6. Submit a synthetic job, and read what the worker recorded of it.

   ```bash
   STAMP=REPLACE_WITH_STAMP
   argo submit --from workflowtemplate/investigate --name "syn-$STAMP" -p target=synthetic -p seconds=600 -p max-turns=8 \
     -p task="$(cat REPLACE_WITH_PLATFORM_CHECKOUT/worker/agent-runtime/fixture/question.txt)" --wait
   REPLACE_WITH_SSH aisec-worker 'sudo ausearch --input-logs -k aisec-exec -ts recent -i | grep "^type=SYSCALL" |
     sed "s/.* \(auid=[^ ]*\) \(uid=[^ ]*\).* \(comm=[^ ]*\).*/\1 \2 \3/" | sort | uniq -c'
   ```

   Expected: `Succeeded`, and `SYSCALL` records with the key `aisec-exec` in two shapes: the job runner in the job account's session (`auid=aisec-job`), and the job's unit as a dynamic user (`python3` and `goose`, with a numeric `uid` in 61184 to 65519 and no login user ID). The names and their counts are read here for the first time.

7. Read the workspace and the alerts, about 15 minutes after step 5.

   ```bash
   kql "Syslog | where TimeGenerated > ago(2h) and Facility == 'local6' | summarize n = count() by Computer, ProcessName"
   kql "Syslog | where TimeGenerated > ago(2h) and ProcessName == 'aisec-aide' | project TimeGenerated, SyslogMessage | order by TimeGenerated asc"
   kql "AisecWorkerJournal_CL | where TimeGenerated > ago(2h) | extend line = parse_json(RawData)
        | where tostring(line.SYSLOG_FACILITY) == '22' | summarize n = count() by tostring(line.SYSLOG_IDENTIFIER)"
   SUB=$(az account show --query id -o tsv)
   az rest --method get \
     --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview&timeRange=1d" \
     --query "value[?contains(properties.essentials.alertRule, 'audit-config') || contains(properties.essentials.alertRule, 'aide')].[properties.essentials.alertRule, properties.essentials.monitorCondition, properties.essentials.startDateTime]" -o tsv
   ```

   Expected: `Syslog` rows from `aisec-orchestrator` on `local6` from the plugin and from `aisec-aide`, the orchestrator's four check and baseline lines among them; worker journal rows with facility `22` from the same two identifiers; `audit-config-write` and `aide-report` `Fired`, and `aide-check-missing` `Resolved`. The plugin's identifier is read here for the first time.

8. Run every check with the targets checkout named ([validation](../validation/README.md)).

   Expected: `F.1` to `F.7`, `O.14`, and `O.18` pass, and every other check with them.

## After an install step, or a package upgrade

9. Run the check, read the report against the step's files or the upgrade log, then write the new baseline. For the worker, copy it to the orchestrator as in step 4.

   ```bash
   HOST=REPLACE_WITH_HOST
   REPLACE_WITH_SSH $HOST 'sudo systemctl start aisec-aide-check.service
     sudo journalctl -u aisec-aide-check.service -t aisec-aide --since -10min -o cat --no-pager
     sudo tail -n 20 /var/log/unattended-upgrades/unattended-upgrades.log'
   REPLACE_WITH_SSH $HOST 'sudo aisec-aide-baseline && sudo systemctl start aisec-aide-check.service &&
     sudo journalctl -t aisec-aide --since -5min -o cat --no-pager'
   ```

   Expected: the report lists the step's files, or the files of the packages the log names, and nothing else. A file neither explains is a change nobody made: stop here, and start with the [incident response runbook](incident-response.md). Then `baseline entries=N database=sha256:...`, which fires `aide-report` once, and a check line `added=0 removed=0 changed=0`, after which `F.3` or `F.6` passes again.

## A rebuilt VM

10. First boot installs both and writes a baseline over what exists then. After the runbook steps that install the rest, the model server and the agent runtime on the worker, the copiers and the collection on the orchestrator, run step 3 for that VM again, so the rules load with every watched directory in place, then step 9, and for the worker step 4.

    Expected: as steps 3, 9, and 4.

## Remove

11. Stop the timer, remove the files and the packages, and revert the Terraform change of step 1.

    ```bash
    HOST=REPLACE_WITH_HOST
    REPLACE_WITH_SSH $HOST 'sudo systemctl disable --now aisec-aide-check.timer
      sudo rm -f /etc/systemd/system/aisec-aide-check.service /etc/systemd/system/aisec-aide-check.timer \
        /usr/local/sbin/aisec-aide-check /usr/local/sbin/aisec-aide-baseline /etc/aisec/aide.conf \
        /etc/audit/rules.d/50-aisec.rules /etc/audit/plugins.d/aisec-syslog.conf
      sudo rm -r /var/lib/aisec/aide
      sudo systemctl daemon-reload && sudo augenrules --load && sudo systemctl reload-or-restart auditd
      sudo DEBIAN_FRONTEND=noninteractive apt-get remove -y -q auditd aide'
    ```

    Expected: `F.1` to `F.7` fail on absence, and `O.14` and `O.18` until the revert is applied. Not run.
