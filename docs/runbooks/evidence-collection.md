# Evidence collection and the verification gate for a NetBox job: operator procedure

Status: Implemented on 2026-10-25. Run once, on the live system, 12:08 to 12:33 UTC, from two scripts with the same commands ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#evidence-per-job)). Steps 1 to 6 ran from the first script, and steps 7 to 15 from the second, with three more jobs before step 15 that show what the tool service (an MCP server) refuses. Steps 1 to 6 and 11 ran again at 14:29 to 14:31 UTC, after fixes from a review, and the checks after them ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#fixes-from-the-review)). The undo and the steps after a rebuild were not run. For the verification gate, steps 1, 10 to 13, 15, and 17 ran at 17:51 to 18:32 UTC, from a script with the same commands, and steps 7 and 8 for Argo's files and images only. The tool service did not change, so step 9 did not run. Steps 11 to 13 ran for four more NetBox jobs at 18:56 to 19:40 UTC while the task was tuned, and step 17 for one of them ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-comparison)). Step 14, step 16, and the undo for `netbox-verdicts` were not run. Steps 1 and 2 ran again at 21:48 UTC with the case file, step 17's last command for the two keys it had changed, and step 11 once for each held-out case ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-rollout)). The read of the reports in step 16 ran on 2026-10-25, against `nb-10251922-a2`'s directory. Steps 11 to 13 ran for the twelve jobs of the investigation's evaluation (eval), 2026-10-25 23:08 UTC to 2026-10-26 01:07 UTC, from a script with the same commands, with a case's name in step 11 and 1200 seconds in step 12 ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-scored-runs)).

This installs NetBox's collect command on the orchestrator and an observer account on the lab VM, deploys the tool service that stores evidence per job and the workflow template that names a job's target, then collects one job's evidence and runs the job on it ([ADR 0040](../decisions/0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)). The workflow then compares the job's verdict for each account with the deterministic checks', and stops on anything but a match ([ADR 0041](../decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md)). No cloud resource changes, and no network rule.

Before this:

- NetBox holds the seed, and `N.14` and `N.17` pass: the [NetBox runbook](netbox.md), steps 1 to 20.
- The update run has pinned the lab VM's host key on the orchestrator: the [target VMs runbook](targets.md).
- The tool service and Argo run: the [tool service runbook](tool-service.md) and the [workflows runbook](workflows.md).

## Inputs and access

| Input | Notes |
| --- | --- |
| A certificate signed today | As in the [SSH certificates runbook](ssh-certificates.md) |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options. Host aliases `aisec-orchestrator`, `aisec-edge`, and `aisec-lab` |
| A checkout of this repository | Run from its root, for `collectors/netbox/`, `platform/`, `policies/`, and the checks. The tool service's and the dispatch step's digests in it are the images to run. `collectors/netbox/task.txt` is the task a NetBox job is sent with |
| A checkout of the targets repository | `REPLACE_WITH_TARGETS_CHECKOUT`, for `netbox/contract.json` |
| Argo's command line and the operator's kubeconfig | As in the [workflows runbook](workflows.md#the-operators-token), step 9, with the tunnel to the API server up |
| A job ID | `REPLACE_WITH_JOB`, used once: the collection and the workflow's name. Lower-case letters, digits, and hyphens, at most 63, starting with a letter or a digit |

## The collect command

1. Copy the collector, the collect command, and the installer to the orchestrator, with the access specification, and install.

   ```bash
   tar -C collectors/netbox -cf - netbox_access.py collect_evidence.py cases.json install-collector.sh |
     REPLACE_WITH_SSH aisec-orchestrator 'rm -rf ~/collector-install && mkdir ~/collector-install && tar -C ~/collector-install -xf -'
   REPLACE_WITH_SSH aisec-orchestrator 'cat > ~/collector-install/contract.json' < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
   KEY=$(REPLACE_WITH_SSH aisec-orchestrator 'sudo bash ~/collector-install/install-collector.sh')
   echo "$KEY"
   ```

   Expected: one line, `ssh-ed25519 REPLACE_WITH_KEY aisec-netbox-observe`, the observer key's public half. The script makes the key once and never replaces it. It stops with `no pinned host key for the lab VM` when the update run has not pinned one.

2. Read what the script installed. The observer key's directory is root's alone, so each path is named, not matched by a glob in the login shell.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo stat -c "%U %a %n" /etc/aisec/netbox/observe /etc/aisec/netbox/observe/id_ed25519 \
     /etc/aisec/netbox/observe/known_hosts /usr/local/lib/aisec/netbox_access.py /usr/local/sbin/collect-netbox-evidence \
     /etc/aisec/netbox/contract.json /etc/aisec/netbox/cases.json /var/lib/aisec/evidence/netbox; sudo cut -c1-40 /etc/aisec/netbox/observe/known_hosts'
   ```

   Expected:

   ```text
   root 700 /etc/aisec/netbox/observe
   root 600 /etc/aisec/netbox/observe/id_ed25519
   root 644 /etc/aisec/netbox/observe/known_hosts
   root 644 /usr/local/lib/aisec/netbox_access.py
   root 755 /usr/local/sbin/collect-netbox-evidence
   root 644 /etc/aisec/netbox/contract.json
   root 644 /etc/aisec/netbox/cases.json
   root 700 /var/lib/aisec/evidence/netbox
   10.50.0.36 ssh-ed25519 AAAAC3NzaC1lZDI1N
   ```

## The observer account

3. Copy the collector and the installer to the lab VM, and install the account with the key from step 1.

   ```bash
   tar -C collectors/netbox -cf - netbox_access.py install-lab-observer.sh |
     REPLACE_WITH_SSH aisec-lab 'rm -rf ~/observer-install && mkdir ~/observer-install && tar -C ~/observer-install -xf -'
   REPLACE_WITH_SSH aisec-lab "sudo bash ~/observer-install/install-lab-observer.sh '$KEY'"
   ```

   Expected: `parsed OK` for the sudo rule, then four lines from `sshd -T` for the account, in any order:

   ```text
   permittty no
   allowtcpforwarding no
   forcecommand sudo -n /usr/local/sbin/aisec-observe-netbox
   authorizedkeysfile /etc/ssh/aisec-observe-keys
   ```

4. Read the account's files.

   ```bash
   REPLACE_WITH_SSH aisec-lab 'sudo stat -c "%U %a %n" /etc/ssh/aisec-observe-keys /etc/sudoers.d/91-aisec-observe \
     /usr/local/sbin/aisec-observe-netbox /usr/local/lib/aisec/netbox_access.py; sudo cut -d " " -f 1,2 /etc/ssh/aisec-observe-keys | cut -c1-60'
   ```

   Expected: `root 644`, `root 440`, `root 755`, `root 644` in that order, then `from="10.40.0.4",restrict ssh-ed25519`.

5. Run the observed half from the orchestrator, as the collect command does, and ask for another command.

   ```bash
   OBSERVE='ssh -F none -i /etc/aisec/netbox/observe/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/aisec/netbox/observe/known_hosts -o ConnectTimeout=8'
   REPLACE_WITH_SSH aisec-orchestrator "sudo $OBSERVE -T aisec-observe@10.50.0.36 id" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json |
     python3 -I -c 'import json, sys
   accounts = json.load(sys.stdin)["accounts"]
   print(" ".join(a + ":" + v["verdict"] for a, v in accounts.items()))'
   ```

   Expected: `inventory-reader:excess inventory-reader-control:within`. The forced command runs, not `id`, and reads the access specification on its standard input.

6. Ask the account for a terminal and for a forward.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator "sudo $OBSERVE -tt aisec-observe@10.50.0.36 true </dev/null 2>&1 | head -n 2"
   REPLACE_WITH_SSH aisec-orchestrator "sudo timeout 20 $OBSERVE -W 10.50.0.4:8443 aisec-observe@10.50.0.36 </dev/null 2>&1 | head -n 2"
   ```

   Expected: `PTY allocation request failed on channel 0`, then `channel 0: open failed: administratively prohibited: open failed` and `stdio forwarding failed`.

## The images and the template

7. Confirm that no workflow is running, then copy the tool service's and Argo's files to the orchestrator. The deploy restarts the tool service, which ends every job it holds.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration get workflows --no-headers'
   tar -cf - platform/tool-service policies/tool-service.json |
     REPLACE_WITH_SSH aisec-orchestrator 'rm -rf ~/feed/tool-service && mkdir -p ~/feed/tool-service && tar -C ~/feed/tool-service -xf -'
   tar -C platform/argo -cf - . |
     REPLACE_WITH_SSH aisec-orchestrator 'rm -rf feed/argo/scripts && mkdir -p feed/argo/scripts feed/argo/stage && tar -C feed/argo/scripts -xf -'
   ```

   Expected: no line with `Running`, then no output.

8. Pull both images in one just-in-time (JIT) egress window, and close it.

   ```bash
   IMAGE=$(grep -oE 'ghcr\.io/[^ ]+@sha256:[0-9a-f]{64}' platform/tool-service/tool-service.yaml)
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 20'
   REPLACE_WITH_SSH aisec-orchestrator 'cd feed/argo && scripts/fetch.sh stage'
   REPLACE_WITH_SSH aisec-orchestrator "sudo k3s crictl pull $IMAGE"
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close'
   ```

   Expected: `open for 20 minutes`, an `ok` line for the dispatch image with the digest `platform/argo/workflow-template.yaml` names and one for each of Argo's images, `Image is up to date for sha256:REPLACE_WITH_CONFIG_DIGEST`, then `closed`.

9. Deploy the tool service, then read NetBox's config map and the pod's mounts.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo ~/feed/tool-service/platform/tool-service/deploy.sh ~/feed/tool-service'
   REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl -n tool-services get configmap tool-service-evidence-netbox -o jsonpath='{.metadata.name} keys={.data}{\"\\n\"}'"
   REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl -n tool-services get pods -l app.kubernetes.io/name=tool-service \
     -o jsonpath='{range .items[0].spec.containers[0].volumeMounts[*]}{.name}:{.mountPath}:{.readOnly}{\"\\n\"}{end}{.items[0].status.containerStatuses[0].imageID}{\"\\n\"}'"
   ```

   Expected: the lines of the [tool service runbook](tool-service.md#deploy), step 4, with `configmap/tool-service-evidence-netbox created` the first time and no line for it after. Then `tool-service-evidence-netbox keys=`: the deploy makes the config map empty and never writes its keys, which are the collect command's. Then three mounts, each `true`, read-only:

   ```text
   aisec:/aisec:true
   evidence-synthetic:/evidence/synthetic:true
   evidence-netbox:/evidence/netbox:true
   ```

   And the digest `platform/tool-service/tool-service.yaml` names.

10. Install Argo's objects again, for the template, and read its images and parameters.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'cd feed/argo && sudo scripts/install.sh stage'
    REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl -n orchestration get workflowtemplate investigate \
      -o jsonpath='{range .spec.templates[*]}{.name} {.container.image}{\"\\n\"}{end}{range .spec.arguments.parameters[*]}{.name}={.value} {.enum}{\"\\n\"}{end}'"
    ```

    Expected: `configmap/netbox-verdicts created` the first time and no line for it after, `workflowtemplate.argoproj.io/investigate configured`, the other objects `unchanged`, except `configmap/argo-ui configured`, which every install prints, and `successfully rolled out`. The collect command adds each job's verdicts to that config map, and `install.sh` never applies over it. Then four templates: `investigate` with no image, which runs the next two as steps, then `dispatch`, `compare`, and `revoke`, each on the dispatch digest. Among the parameters, `target=synthetic ["synthetic","netbox"]`.

## A job

11. Collect the job's evidence.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo collect-netbox-evidence REPLACE_WITH_JOB'
    REPLACE_WITH_SSH aisec-orchestrator 'sudo ls -l /var/lib/aisec/evidence/netbox/REPLACE_WITH_JOB && sudo cat /var/lib/aisec/evidence/netbox/REPLACE_WITH_JOB/verdicts.json'
    REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration get configmap netbox-verdicts -o json' |
      python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"][sys.argv[1] + ".json"])' REPLACE_WITH_JOB
    ```

    For a held-out case of the eval set, add its name from `collectors/netbox/cases.json`: `sudo collect-netbox-evidence REPLACE_WITH_JOB REPLACE_WITH_CASE`. The first line of the output is then `REPLACE_WITH_JOB: case REPLACE_WITH_CASE`, and the verdicts are the case's expected ones ([ADR 0042](../decisions/0042-held-out-cases-and-the-baseline-without-the-agent.md)).

    Expected: `REPLACE_WITH_JOB: ev-0001 ev-0002 ev-0003, visible to the tool service after N s`, with `N` up to 180, then `inventory-reader:excess/excess inventory-reader-control:within/within`, the configured verdict before the slash and the observed one after, then `verdicts for the comparison in orchestration/netbox-verdicts`. Then six files, each `root 600`: `configured.json`, `ev-0001.json` to `ev-0003.json`, `observed.json`, and `verdicts.json`, and the verdicts in full. The command stops before it writes anything when either half's report does not name the access specification's accounts or names a read or a denial the specification does not, when a half sends more than a megabyte or takes more than two minutes, or when a document is larger than a tool result may be. The config map keeps the newest 20 jobs' keys, and the orchestrator keeps every job's directory. Last, the job's key in `netbox-verdicts`: the job's ID, the time of the collection, and each account's configured and observed verdicts, the same as in `verdicts.json`. `netbox-verdicts` keeps the newest 20 jobs as well.

12. Submit the job under the same name, with NetBox as its target, and wait for it.

    ```bash
    argo submit --from workflowtemplate/investigate --name REPLACE_WITH_JOB -p target=netbox \
      -p max-turns=8 -p seconds=900 -p task="$(cat collectors/netbox/task.txt)"
    argo wait REPLACE_WITH_JOB
    argo get REPLACE_WITH_JOB
    argo get REPLACE_WITH_JOB -o json | python3 -I -c 'import json, sys
    wf = json.load(sys.stdin)
    for node in wf["status"]["nodes"].values():
        for p in (node.get("outputs") or {}).get("parameters", []):
            if p["name"] == "result":
                result = json.loads(p["value"])
                result.pop("transcript", None)
                print(node["displayName"], json.dumps(result, indent=1))
            elif p["name"] == "comparison":
                print(node["displayName"], p["value"])'
    argo logs REPLACE_WITH_JOB
    ```

    For a job of the eval, give it `-p seconds=1200`, the longest a job may have, and collect it with the case's name in step 11 ([investigation](../validation/investigation.md#how-an-eval-job-runs)).

    The task names the three references: `ev-0001` the access specification (the task's contract), `ev-0002` the configured permissions, `ev-0003` the records and denials. It defines each verdict, and asks the output to end with one line per account, `Verdict:` with the account, its verdict, and its references. The worker refuses a task that starts with a slash or an exclamation mark, and one with template braces.

    Expected: the dispatch step `Succeeded`, with a result with `"status": "completed"`, `"tool_calls"` of 3 or more, `"tool_errors": 0`, `"slot_erased": true`, and its output. Then the verification gate, one of two:

    - **A match:** the workflow `Succeeded`. Every account's verdict line names the deterministic checks' value, and the two agree. The compare step's log ends with `match`.
    - **A stop:** the workflow `Failed`, with the compare step's message `stop: ` and each reason, such as `inventory-reader: the model says within, the checks say excess`. See [When a job stops](#when-a-job-stops).

    The comparison step's output and log have one row per account: the model's verdict and references, both deterministic checks' verdicts, and the outcome. Which of the two comes is the model's doing: the procedure is right either way. A workflow under another name than the collection's finds no evidence, each call refused with `nothing by that reference`, and stops at the verification gate with `no checks' verdicts for this job`.

    The step's output also keeps the model output's remediation proposal lines, read in the same exact form, and a count of those it could not read. They never change the outcome.

13. Read the job's audit lines.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "sudo grep -F '\"REPLACE_WITH_JOB\"' /var/log/aisec/tool-audit.jsonl" |
      python3 -I -c 'import json, sys
    for line in sys.stdin:
        a = json.loads(line)
        print(a["seq"], a["event"], a["decision"], a.get("tool"), a.get("reason"), a.get("result_bytes"))'
    ```

    Expected: `register allowed`, then one `call allowed get_evidence` line for each call with its `result_bytes`, then `revoke allowed`.

14. Collect the same ID again, with the config map's version read before and after.

    ```bash
    VERSION="sudo k3s kubectl -n tool-services get configmap tool-service-evidence-netbox -o jsonpath='{.metadata.resourceVersion}{\"\\n\"}'"
    REPLACE_WITH_SSH aisec-orchestrator "$VERSION"
    REPLACE_WITH_SSH aisec-orchestrator 'sudo collect-netbox-evidence REPLACE_WITH_JOB'; echo "exit $?"
    REPLACE_WITH_SSH aisec-orchestrator "$VERSION"
    ```

    Expected: `failed: REPLACE_WITH_JOB already collected` and `exit 1`, between the same version twice. The config map is not touched.

## Checks

15. Run every check, with the targets checkout named.

    ```bash
    AISEC_SSH="REPLACE_WITH_SSH" AISEC_ORCH=aisec-orchestrator AISEC_WORK=aisec-worker AISEC_EDGE=aisec-edge \
      AISEC_NETBOX=aisec-netbox AISEC_LAB=aisec-lab AISEC_TARGETS=REPLACE_WITH_TARGETS_CHECKOUT \
      AISEC_USER_CA=REPLACE_WITH_CRED_DIR/aisec-user-ca.pub validation/platform-checks.sh
    ```

    Expected: `N.18` to `N.23`, `T.2`, `T.14`, `W.9`, and `W.12` pass, and the last line says `0 failed`. `W.9` fails between a change to the template and step 10, and `T.2` between a new tool service digest and step 9.

## When a job stops

16. Read why it stopped, then the deterministic checks' reports for that job.

    ```bash
    argo get REPLACE_WITH_JOB
    REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /var/lib/aisec/evidence/netbox/REPLACE_WITH_JOB/{verdicts,configured,observed}.json'
    ```

    Expected: the compare step `Failed`, with its message `stop: ` and the reasons, or the dispatch step `Failed`, for a job that did not complete. Its message is then `main: Error (exit code 1)` only, and the reason is the last line of its log, `failed: ` and the reason. Then the deterministic checks' verdicts, and the reasons each gave for them, from this job's collection only. The dispatch step's log, from step 12, holds the agent's transcript: what the model asked for, what it read, and its output. A job stopped at its time limit has no transcript, and its result gives no call counts: the audit lines from step 13 hold its calls. Nothing runs after a stop. The next try is a new job ID, from step 11.

17. Stop a job on purpose, to see the verification gate stop on its input: collect a new job ID, change its key so that the two deterministic checks disagree on `inventory-reader`, then run step 12 on it.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo collect-netbox-evidence REPLACE_WITH_JOB'
    REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration get configmap netbox-verdicts -o json' |
      python3 -I -c 'import json, sys
    job = sys.argv[1]
    document = json.loads(json.load(sys.stdin)["data"][job + ".json"])
    document["accounts"]["inventory-reader"]["observed"] = "within"
    print(json.dumps({"data": {job + ".json": json.dumps(document, indent=2)}}))' REPLACE_WITH_JOB |
      REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration patch configmap netbox-verdicts --type merge --patch-file /dev/stdin'
    ```

    Expected: `configmap/netbox-verdicts patched`. After step 12, the workflow `Failed`, with the compare step's message `stop: inventory-reader: the checks disagree, configured excess, observed within`, whatever the model returns.

    Then take the changed key out, so that no later workflow under the same name reads verdicts nobody collected. A name is free again once its workflow is deleted, 24 hours after it ends.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl -n orchestration patch configmap netbox-verdicts --type json -p '[{\"op\": \"remove\", \"path\": \"/data/REPLACE_WITH_JOB.json\"}]'"
    ```

    Expected: `configmap/netbox-verdicts patched`. The job's directory on the orchestrator keeps the deterministic checks' real verdicts.

## Replace the observer key

Not run. Remove the key on the orchestrator, then run steps 1, 3, and 5 again. Step 1 makes a new key, and step 3 writes the lab VM's key file whole, so the old key no longer logs in.

```bash
REPLACE_WITH_SSH aisec-orchestrator 'sudo rm -f /etc/aisec/netbox/observe/id_ed25519 /etc/aisec/netbox/observe/id_ed25519.pub'
```

Expected: no output. In step 1, a public half other than the old one. In step 5, the same verdicts. Until step 1, `N.19` fails. Until step 3, `N.23` fails, and a collection stops at the observed half.

## Undo

Not run. On the lab VM, remove the account and its files, then reload SSH:

```bash
REPLACE_WITH_SSH aisec-lab 'sudo userdel -r aisec-observe; sudo rm -f /etc/ssh/aisec-observe-keys /etc/ssh/sshd_config.d/20-aisec-observe.conf \
  /etc/sudoers.d/91-aisec-observe /usr/local/sbin/aisec-observe-netbox; sudo rm -rf /usr/local/lib/aisec; sudo sshd -t && sudo systemctl reload ssh'
```

On the orchestrator, remove the key, the command, its copies of the collector and the access specification, and every job's directory:

```bash
REPLACE_WITH_SSH aisec-orchestrator 'sudo rm -rf /etc/aisec/netbox/observe /var/lib/aisec/evidence/netbox; \
  sudo rm -f /usr/local/sbin/collect-netbox-evidence /usr/local/lib/aisec/netbox_access.py /etc/aisec/netbox/contract.json'
```

`N.18` to `N.23` then fail until steps 1 to 6 run again. `N.14` and `N.17` send the checkout's collector and do not need these files.

The config map stays, with every job's keys: `deploy.sh` makes it once and never applies over it. Delete it only after a deploy of a manifest without NetBox's mount, because the pod does not start without its volume's config map. That is reasoned from the manifest, not observed.

```bash
REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n tool-services delete configmap tool-service-evidence-netbox'
```

`netbox-verdicts` stays too, with every job's verdicts: Argo's `install.sh` makes it once. The comparison step mounts it as optional, so deleting it does not stop a pod from starting: every NetBox job then stops at the verification gate, with `no checks' verdicts for this job`. A collection after the delete fails at `reading the ConfigMap netbox-verdicts`, after it has written the job's directory and the tool service's keys, so that job ID is spent. Argo's `install.sh` makes the config map again. That is reasoned from the template and the collect command, not observed.

```bash
REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration delete configmap netbox-verdicts'
```

## After a rebuild

| Rebuilt | Run again |
| --- | --- |
| The orchestrator | The tool service, workflows, and target VMs runbooks first, for the cluster and the update run's host key pins. Then steps 1 to 15. Step 1 makes a new key, and step 3 replaces the old one on the lab VM |
| The lab VM | The update run first, for a new host key pin, then steps 1 to 6. Step 1 keeps the key and pins the new host key |
