# Containment drills: operator procedure

Status: Implemented on 2026-10-28, when steps 1 to 4, 6, and 7 ran on the live system, and step 5 on 2026-10-29. Results are in the [milestone 6 worklog](../worklogs/0007-operational-and-containment-drills.md#slice-1-drills-without-an-apply).

Each drill breaks the finished workflow on purpose and reads what it left. The steps are independent and each is put back after it. Later slices add their drills here.

## Inputs and access

| Input | Notes |
| --- | --- |
| The platform with NetBox collected and deployed | The [evidence collection runbook](evidence-collection.md), steps 1 to 10 |
| SSH to the orchestrator, the worker, the router, and the NetBox VM | `REPLACE_WITH_SSH` below stands for the operator's `ssh` command with its options |
| The tunnel to the API server and Argo's command line | The [workflows runbook](workflows.md), inputs |
| The operator's sign-in to Azure, for the workspace | `REPLACE_WITH_WS` is the workspace's customer ID, from the [monitoring runbook](monitoring.md), step 6, with its `kql` function |
| A checkout of this repository on the workstation | `REPLACE_WITH_PLATFORM_CHECKOUT` |

## A job that times out

1. Collect a job's evidence, then submit it with a limit inside its first prompt.

   ```bash
   JOB=nb-REPLACE_WITH_STAMP-timeout
   REPLACE_WITH_SSH aisec-orchestrator "sudo collect-netbox-evidence $JOB"
   argo submit --from workflowtemplate/investigate --name "$JOB" -p target=netbox -p seconds=120 -p max-turns=8 \
     -p task="$(cat REPLACE_WITH_PLATFORM_CHECKOUT/collectors/netbox/task.txt)" --wait
   argo get "$JOB" | grep -E "Status|dispatch|revoke"
   REPLACE_WITH_SSH aisec-worker 'journalctl --no-pager -o cat -u "aisec-agent-job@*" --since -10min | grep outcome
     journalctl --no-pager -o cat -u aisec-llama-server --since -10min | grep -E "cancel|n_tokens = [0-9]+, progress|slot released" | tail -n 6'
   ```

   Expected: the workflow `Failed`, the dispatch step with `failed: the job ended timeout`, the exit handler `Succeeded`. The worker's line has `"outcome": "timeout"` and `"slot_erased": true`. The server's journal shows `n_tokens` growing by 512 per batch, the cancel, and the slot released within about 75 seconds of it.

## A terminated workflow

2. Submit a job, wait until the agent is working, and terminate the workflow. `argo terminate` skips the exit handler, so the dispatch step's own revoke is what ends the token.

   ```bash
   JOB=nb-REPLACE_WITH_STAMP-terminate
   REPLACE_WITH_SSH aisec-orchestrator "sudo collect-netbox-evidence $JOB"
   argo submit --from workflowtemplate/investigate --name "$JOB" -p target=netbox -p seconds=600 -p max-turns=8 \
     -p task="$(cat REPLACE_WITH_PLATFORM_CHECKOUT/collectors/netbox/task.txt)"
   sleep 60; argo terminate "$JOB"; sleep 20; argo get "$JOB" | grep -E "Status|Message|dispatch|revoke"
   argo logs "$JOB" | tail -n 3
   REPLACE_WITH_SSH aisec-orchestrator "sudo grep '\"job\": \"$JOB\"' /var/log/aisec/tool-audit.jsonl | tail -n 2"
   REPLACE_WITH_SSH aisec-worker 'journalctl --no-pager -o cat -u "aisec-agent-job@*" --since -5min | grep outcome'
   ```

   Expected: `Failed`, with the message `Stopped with strategy 'Terminate'`, the dispatch step exit code 143 and no `revoke` node. The step's last log line is `{"job": ..., "stopped": 15, "revoked": 200}`, and the audit file's last two lines for the job are `register` and `revoke`, the revoke by the dispatch caller. The worker's line has `"outcome": "cancelled"` and `"slot_erased": true`.

## Operator sessions to the targets

3. Read the rule, open one session to the NetBox VM, and find its row in the workspace. The row takes a few minutes.

   ```bash
   REPLACE_WITH_SSH aisec-router 'sudo nft list table inet aisec_sessions | grep -c aisec-target-ssh'
   REPLACE_WITH_SSH aisec-netbox true
   for _ in $(seq 1 20); do
     rows=$(kql "Syslog | where Computer == 'aisec-router' and SyslogMessage has 'aisec-target-ssh' and TimeGenerated > ago(15m) | project TimeGenerated, SyslogMessage")
     [ -n "$rows" ] && break; sleep 30
   done; echo "$rows"
   ```

   Expected: `1`, then one row within ten minutes whose message has `aisec-target-ssh`, `SRC=` the workstation's mesh address, `DST=10.50.0.4`, and `DPT=22`. The router's own `journalctl -k` has the same line at once.

## Stale and forged checks' verdicts

4. Write an item by hand with a `collected` two hours old, and submit a job for it. The dispatch step refuses it before the job runs.

   ```bash
   item() {  # item JOB COLLECTED VERDICT: a checks' verdicts item for both accounts, written as root
     python3 -I -c 'import json, sys
   job, collected, verdict = sys.argv[1:]
   accounts = {a: {"configured": verdict, "observed": verdict} for a in ("inventory-reader", "inventory-reader-control")}
   print(json.dumps({"data": {job + ".json": json.dumps({"job": job, "collected": collected, "accounts": accounts})}}))' "$@" |
       REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration patch configmap netbox-verdicts --type merge --patch-file /dev/stdin'
   }
   JOB=nb-REPLACE_WITH_STAMP-stale
   item "$JOB" "$(date -u -d '2 hours ago' +%FT%TZ)" excess
   argo submit --from workflowtemplate/investigate --name "$JOB" -p target=netbox -p seconds=120 -p max-turns=8 \
     -p task="$(cat REPLACE_WITH_PLATFORM_CHECKOUT/collectors/netbox/task.txt)" --wait
   argo logs "$JOB" | tail -n 1
   REPLACE_WITH_SSH aisec-orchestrator "sudo grep -c '\"job\": \"$JOB\"' /var/log/aisec/tool-audit.jsonl"
   ```

   Expected: `configmap/netbox-verdicts patched`, then `Failed` within a minute, the last log line `failed: the checks' verdicts are 72NN s old, and the dispatch step takes at most 3600`, and `0` audit lines: the job never registered.

5. Collect the job, so its evidence documents exist, then overwrite its item with a fresh time and a verdict the live seed contradicts, and submit it. The item is trusted, and the verification gate stops on the model's disagreement with it.

   ```bash
   JOB=nb-REPLACE_WITH_STAMP-forged
   REPLACE_WITH_SSH aisec-orchestrator "sudo collect-netbox-evidence $JOB"
   item "$JOB" "$(date -u +%FT%TZ)" within
   argo submit --from workflowtemplate/investigate --name "$JOB" -p target=netbox -p seconds=1200 -p max-turns=8 \
     -p task="$(cat REPLACE_WITH_PLATFORM_CHECKOUT/collectors/netbox/task.txt)" --wait
   argo get "$JOB" | grep -E "Status|Message|compare"
   ```

   Expected: the job runs on the live evidence and answers `excess` for `inventory-reader`, and the compare step fails with a stop naming the account and both verdicts. The item written by root was taken as the checks' word: `W.12` names who can write the config map, and nothing in the workflow tells a collected item from a written one.

## Resource use per investigation

6. Read each component's cumulative CPU time and peak memory on the orchestrator before step 5's job and after it, and the machine's `Perf` rows for the job's minutes. The difference over the job's seconds is each component's average CPU.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'for u in k3s azuremonitoragent aisec-audit-copy aisec-journal-pull; do
       systemctl show -p Id,CPUUsageNSec,MemoryPeak "$u.service" | tr "\n" " "; echo; done
     for d in /sys/fs/cgroup/kubepods.slice/*/*pod*.slice; do echo "${d##*/} $(grep usage_usec "$d/cpu.stat") $(cat "$d/memory.peak")"; done'
   kql "Perf | where Computer == 'aisec-orchestrator' and CounterName in ('% Processor Time', 'Available MBytes Memory') and TimeGenerated between (datetime(REPLACE_WITH_T0) .. datetime(REPLACE_WITH_T1)) | summarize avg(CounterValue), min(CounterValue), max(CounterValue) by CounterName"
   ```

   Expected: the dispatch pod's and the tool service's CPU over the job, the controller's, and the machine's processor time and free memory. A pod's cgroup goes with the pod, so the second reading comes while the compare step still runs, or from the `Perf` rows alone.

## Push protection

7. Push a commit holding a token-shaped string to a scratch branch, and read the refusal.

   ```bash
   cd REPLACE_WITH_PLATFORM_CHECKOUT && git switch -c drill/push-protection main
   printf 'token: %s\n' "REPLACE_WITH_A_MADE_UP_GITHUB_TOKEN" > drill.txt && git add drill.txt && git commit -q -m "test: push-protection drill"
   git push -u origin drill/push-protection; echo "exit $?"
   git switch main && git branch -D drill/push-protection
   ```

   Expected: the push refused with `GH013: Repository rule violations` and a `Push cannot contain secrets` block naming the token type, exit `1`, and no branch on the remote. If the push goes through, delete the remote branch, and the accepted risk stays with that result.
