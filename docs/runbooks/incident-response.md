# Incident response: operator procedure

Status: Implemented on 2026-10-30, when steps 1 to 6, 8, 11, 12, 15, and 16 ran on the live system from 23:08 UTC, and steps 9, 10, 13, 17 to 19, and 21 in a second run from 23:22 UTC, after two command faults in the first: steps 9 and 13 moved nothing, and step 17 got no answer, both corrected below. The read commands of steps 3 (the step's log lines and the denied count) and 15 (the journal line) were changed after the run and have not run as written.

Steps 7, 14, and 20 are each a rebuild, written against the rebuild sections of other runbooks, and run only in the rebuild the [roadmap](../roadmap.md#6-operational-and-containment-drills) lists last. Results are in the [milestone 6 worklog](../worklogs/0007-operational-and-containment-drills.md#slice-7-the-incident-response-runbook).

Three cases, in the same order each: detect, contain, verify, rotate or restore, undo what the drill changed, replace, record. The containment and rotation steps are reversible and are followed by the read that shows each took, and by its undo. The replacement steps destroy a VM.

## Inputs and access

| Input | Notes |
| --- | --- |
| The platform with NetBox collected and deployed | The [evidence collection runbook](evidence-collection.md), steps 1 to 10 |
| SSH to every VM | `REPLACE_WITH_SSH` stands for the operator's `ssh` command with its options; aliases `aisec-orchestrator`, `aisec-worker`, `aisec-edge`, `aisec-netbox`, `aisec-lab` |
| The tunnel to the API server and Argo's command line | The [workflows runbook](workflows.md), inputs |
| A checkout of this repository | `REPLACE_WITH_PLATFORM_CHECKOUT`, for the drills, the collector, and the checks |
| A checkout of the targets repository | `REPLACE_WITH_TARGETS_CHECKOUT`, for `netbox/seed.json`, `netbox/seed.py`, `netbox/contract.json`, and `netbox/make-netbox-token.sh` |
| The scripts on the hosts | `platform/argo`, `worker/agent-runtime`, `platform/tool-service`, and the targets' `netbox/`, where the [workflows](workflows.md) (step 3), [agent runtime](agent-runtime.md) (step 2), [containment drills](containment-drills.md) (step 8), and [NetBox](netbox.md) (step 7) runbooks put them |

## What a compromised machine holds

The [credential inventory](../security/credentials.md) says what each machine keeps. That decides what each case rotates.

| Compromised | Holds | Rotated or replaced |
| --- | --- | --- |
| The worker | Its host key, the public half of the dispatch key, the tool service's certificate, the model, a running job's token in its unit's private `/tmp` | The job's token, revoked. The dispatch key pair. The host key, with the VM |
| The NetBox VM | NetBox's secrets, its TLS key, the accounts' tokens as hashes, the update account's key line | The platform's and the consumers' tokens. The TLS key, with the VM, and its certificate's pin on the orchestrator and the lab VM |
| The collector's token | One read-only token, limited to the orchestrator's address | The token, by the seed run, which replaces the consumers' tokens too |

## A compromised worker

The worker runs the agent and the model, and the design assumes it is compromised ([AI worker](../components/ai-worker.md)). What it can reach is a live job's token, the tool service's port, the model server, and the package proxy on the edge. Containment cuts each of those, in that order.

1. Submit a NetBox job and let its agent start, as the job a compromised worker would be running. Then read what shows it: the unit instance, the job program's line, the job account's login from the orchestrator, and the audit log's lines for the job.

   The signals in the workspace are the `tool-refusal-burst`, `denied-flow-to-internet`, and `ssh-login-failed` alert rules ([monitoring](../components/monitoring.md#alert-rules)).

   ```bash
   STAMP=REPLACE_WITH_STAMP; JOB=nb-$STAMP-stopped
   REPLACE_WITH_SSH aisec-orchestrator "sudo collect-netbox-evidence $JOB"
   argo submit --from workflowtemplate/investigate --name "$JOB" -p target=netbox -p seconds=1200 -p max-turns=8 \
     -p task="$(cat REPLACE_WITH_PLATFORM_CHECKOUT/collectors/netbox/task.txt)"
   sleep 100
   REPLACE_WITH_SSH aisec-worker 'systemctl list-units --no-legend "aisec-agent-job@*"
     journalctl --no-pager -o short-iso -u "aisec-agent-job@*" --since -5min | grep -F "\"erase\": \"before\"" | cut -c1-19
     journalctl --no-pager -o short-iso -u ssh --since -5min | grep -F "Accepted publickey for aisec-job" | tail -n 1 | cut -c1-110'
   REPLACE_WITH_SSH aisec-orchestrator "sudo grep -F '$JOB' /var/log/aisec/tool-audit.jsonl" | cut -c1-120
   ```

   Expected: the collection prints `within` for both accounts. One instance `loaded active running`, the time of the job program's `before` line, the SSH daemon's `Accepted publickey for aisec-job from 10.40.0.4` line, which the `ssh-login-accepted` alert rule counts, and the audit's `register` line for the job, with `call` lines if the agent has read a document.

2. Contain, in three moves: revoke the job's registration from the orchestrator, so the token refuses before anything else moves; stop the job socket, the job's unit, and the model server on the worker; deny the worker at Squid, with a backup of the configuration first.

   ```bash
   REG='sudo ~/feed/tool-service/platform/tool-service/register.sh'
   REPLACE_WITH_SSH aisec-orchestrator "$REG revoke $JOB"
   REPLACE_WITH_SSH aisec-worker 'sudo systemctl stop aisec-agent-job.socket "aisec-agent-job@*" aisec-llama-server
     systemctl is-active aisec-agent-job.socket aisec-llama-server; systemctl list-units --all --no-legend "aisec-agent-job@*" | wc -l'
   REPLACE_WITH_SSH aisec-edge 'sudo cp --update=none /etc/squid/squid.conf /etc/squid/squid.conf.before-incident
     sudo sed -i "0,/^http_access /s//acl incident_worker src 10.40.0.36\/32\nhttp_access deny incident_worker\nhttp_access /" /etc/squid/squid.conf
     sudo squid -k parse 2>&1 | grep -c -i -E "error|fatal"; sudo systemctl reload squid; grep -n incident_worker /etc/squid/squid.conf'
   ```

   Expected: `200 {"job": "nb-REPLACE_WITH_STAMP-stopped"}`. On the worker `inactive` twice and `0` instances. On the edge `0` parse errors, then the two lines at the top of the access rules, before `http_access deny !worker !orchestrator`.

3. Verify the containment: the workflow, the audit log, the worker's journal, the proxy from the worker, and the model server's port.

   ```bash
   argo wait "$JOB"; argo get "$JOB" | grep -E "Status|Message|dispatch|revoke"
   argo logs "$JOB" | grep -E "refused:|failed:"
   REPLACE_WITH_SSH aisec-orchestrator "sudo grep -F '$JOB' /var/log/aisec/tool-audit.jsonl | tail -n 3" | cut -c1-160
   REPLACE_WITH_SSH aisec-worker 'journalctl --no-pager -o cat -u "aisec-agent-job@*" --since -10min | grep -E "outcome|Stopping|Deactivated|Consumed" | cut -c1-120
     for h in archive.ubuntu.com security.ubuntu.com; do curl -s -o /dev/null -w "%{http_code} " -x http://10.45.0.4:3128 "http://$h/ubuntu/dists/resolute/InRelease"; done; echo
     curl -s --max-time 3 http://127.0.0.1:8080/health; echo "exit $?"'
   REPLACE_WITH_SSH aisec-edge 'sudo awk -v since="$(date -d -10min +%s)" "\$1 >= since && / 10.40.0.36 TCP_DENIED\/403 /" /var/log/squid/access.log | wc -l'
   ```

   Expected: `Failed`, the dispatch step `Failed` and the exit handler's `revoke` node `Succeeded`; the step's log holds the job runner's `refused: the job ended without a result, or another job is running`, carried over SSH, and its own `failed: the session ended without a result`. The audit's last lines for the job are the `revoke` allowed for the operator's registration pod and the exit handler's `revoke`, also allowed, since the tool service keeps a revoked registration for an hour ([containment drills](containment-drills.md), step 23).

   On the worker, no `outcome` line: the unit was stopped, so the job program never wrote one, and systemd's `Stopping`, `Deactivated`, and `Consumed` lines stand instead. Then `403 403` from the proxy, a health read that fails with exit `7`, and `2` denied lines for the worker's address in the last ten minutes on the edge. `G.7`, `S.2`, `P.6`, and `P.7` read these same values and fail in this state: reasoned from the checks' probes, since the checks ran only after every undo.

4. Rotate the dispatch key: a new pair in the secret on the orchestrator, and its public half on the worker. The worker holds only the public half, so the pair is rotated because a compromised worker learns which key may log in, not because it can use the key.

   In an incident, step 7 comes first and this step installs the new half on the new worker; here it rotates on the running worker, which also starts the job socket again. The install reinstalls the job runner, the job program, and the units from the worker's `feed/agent-runtime/scripts`, so that copy has to be this checkout's first ([agent runtime runbook](agent-runtime.md), step 2).

   ```bash
   HOST_KEY=$(REPLACE_WITH_SSH aisec-worker 'cut -d " " -f 1,2 /etc/ssh/ssh_host_ed25519_key.pub')
   secret() { REPLACE_WITH_SSH aisec-orchestrator 'sudo k3s kubectl -n orchestration get secret dispatch-ssh -o jsonpath="{.data.id_ed25519}" | sha256sum | cut -c1-16'; }
   secret
   PUB=$(REPLACE_WITH_SSH aisec-orchestrator "cd feed/argo && sudo scripts/make-dispatch-key.sh '$HOST_KEY'")
   REPLACE_WITH_SSH aisec-worker "cd feed/agent-runtime && sudo scripts/install-job.sh '$PUB'"
   secret
   ssh-keygen -lf <(echo "$PUB"); REPLACE_WITH_SSH aisec-worker 'sudo ssh-keygen -lf /home/aisec-job/.ssh/authorized_keys'
   ```

   Expected: a 16-character digest of the old secret, then `root aisec-job 660 /run/aisec-job/agent.sock` and `active`, then another digest, and the same fingerprint for the new public half and the worker's key line. `G.5` and `W.10` pass with the new pair.

5. Undo the containment: start the model server and wait for it, and put Squid's configuration back.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'sudo systemctl start aisec-llama-server
     for _ in $(seq 1 30); do curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:8080/health | grep -q 200 && break; sleep 5; done
     systemctl is-active aisec-llama-server; curl -s --max-time 3 http://127.0.0.1:8080/health'
   REPLACE_WITH_SSH aisec-edge 'sudo mv /etc/squid/squid.conf.before-incident /etc/squid/squid.conf && sudo squid -k parse 2>&1 | grep -c -i -E "error|fatal"
     sudo systemctl reload squid; grep -c incident_worker /etc/squid/squid.conf'
   REPLACE_WITH_SSH aisec-worker 'for h in archive.ubuntu.com security.ubuntu.com; do curl -s -o /dev/null -w "%{http_code} " -x http://10.45.0.4:3128 "http://$h/ubuntu/dists/resolute/InRelease"; done; echo'
   ```

   Expected: `active` and `{"status":"ok"}` within about a minute, `0` parse errors and `0` lines with `incident_worker`, then `200 200`.

6. Verify with a job that the new key dispatches: a synthetic job, which needs no collection.

   ```bash
   argo submit --from workflowtemplate/investigate --name "syn-$STAMP" -p target=synthetic -p seconds=600 -p max-turns=8 \
     -p task="$(cat REPLACE_WITH_PLATFORM_CHECKOUT/worker/agent-runtime/fixture/question.txt)" --wait
   argo get "syn-$STAMP" | grep -E "Status|dispatch|revoke"
   ```

   Expected: `Succeeded`, with the dispatch step and the exit handler's revoke `Succeeded`.

7. Replace, not run: a rebuild of the worker destroys the model, and the [roadmap](../roadmap.md#6-operational-and-containment-drills) lists the rebuild last. In order, the [platform compute runbook](platform-compute.md#rebuild-the-worker), steps 22 to 25, which replace the VM and its host key; the [model server runbook](model-server.md), steps 4 to 6, and the [agent runtime runbook](agent-runtime.md), steps 2 to 4 and 8, from the staged files the orchestrator keeps; then step 4 above with the new host key.

   The audit log and the worker's journal copy on the orchestrator keep what the compromised worker did ([audit log](../security/audit-log.md)).

## A compromised target

A compromised NetBox VM can answer the collector with what it likes ([T23](../security/threat-model.md), [T24](../security/threat-model.md)). The verification gate stops a job whose two deterministic checks disagree, or whose model disagrees with them, and the router logs each operator session to the target ([containment drills](containment-drills.md), steps 3 to 5). Containment stops the platform from reading the target at all, and the comparison below reads what changed.

8. Detect: compare the live NetBox with the seed, from the orchestrator, with the collector's token. The drill reads every group of objects in the seed through the group's endpoint and compares each object, in the fields the seed names for it, and the token's own access with the seed.

   A field the seed does not name, such as an account's superuser flag or a permission's groups, is not compared ([#235](https://github.com/sindredg/ai-security-platform/issues/235)).

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'cat > ~/netbox_against_the_seed.py' < REPLACE_WITH_PLATFORM_CHECKOUT/validation/drills/netbox_against_the_seed.py
   REPLACE_WITH_SSH aisec-orchestrator 'cat > ~/seed.json' < REPLACE_WITH_TARGETS_CHECKOUT/netbox/seed.json
   REPLACE_WITH_SSH aisec-orchestrator 'sudo python3 -I ~/netbox_against_the_seed.py ~/seed.json; echo "exit $?"'
   ```

   Expected: the five groups the collector's permission does not grant, tenants to device roles, `not readable with this token, as the seed grants`; devices `seed 8 netbox 8 same`, addresses `7 7 same`, users `4 6 same, beside aisec-address-probe, aisec-seed`, permissions `6 6 same`; `== 4 groups compared, 0 differences`, `exit 0`.

9. Contain: move the platform's tokens for the target into a root-only directory on the orchestrator and on the lab VM, so that no collection, staging test, or check reads the target until they are back. Run no update run to the target meanwhile.

   ```bash
   hold() { REPLACE_WITH_SSH "$1" 'sudo sh -c "install -d -m 700 /etc/aisec/netbox/held && mv /etc/aisec/netbox/tokens/* /etc/aisec/netbox/held/
     ls /etc/aisec/netbox/tokens | wc -l; ls /etc/aisec/netbox/held"'; }
   hold aisec-orchestrator; hold aisec-lab
   ```

   Expected: on the orchestrator `0`, then `aisec-address-probe` and `aisec-collector`; on the lab VM `0`, then `inventory-reader` and `inventory-reader-control`. The directory is root's alone, so the move runs in root's shell: the operator's shell cannot expand a pattern inside it. A move that fails leaves the empty holding directory behind, which `rmdir` removes.

10. Verify that nothing reads the target: the collect command for a new job, and each deterministic check's half as `N.14` and `N.17` run them.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "sudo collect-netbox-evidence nb-$STAMP-held; echo \"exit \$?\""
    REPLACE_WITH_SSH aisec-orchestrator "sudo k3s kubectl -n orchestration get configmap netbox-verdicts -o json" | grep -c "nb-$STAMP-held"
    code=$(cat REPLACE_WITH_PLATFORM_CHECKOUT/collectors/netbox/netbox_access.py)
    REPLACE_WITH_SSH aisec-orchestrator "sudo python3 -I -c $(printf %q "$code") configured --summary" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json; echo "exit $?"
    REPLACE_WITH_SSH aisec-lab "sudo python3 -I -c $(printf %q "$code") observed --summary" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json; echo "exit $?"
    ```

    Expected: `failed: configured: exit 1:` with `FileNotFoundError` naming `aisec-collector`, exit `1`, and `0` items for the job: a failed collection writes nothing. Each half ends in the same error for its token, with exit `1`. `N.13` to `N.17` read these files and these halves, and fail in this state: reasoned from the checks' probes, since the checks ran only after every undo.

11. Compare against a target that differs. The live NetBox is left alone, and the staging copy stands in for a target someone changed, since it has a dump to restore from: apply one change there through the installed change library, as a staging test does, and compare the copy with the seed using the copy's own tokens.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo python3 -I -c "import sys; sys.path.insert(0, \"/usr/local/lib/aisec\"); import netbox_change as c
    copy = \"/etc/aisec/netbox-rehearsal\"; name = \"inventory-reader: tenant-a inventory\"
    netbox = c.client(\"https://10.50.1.4:8443\", copy + \"/tls.crt\", copy + \"/tokens/aisec-deliver\")
    c.apply(netbox, c.plan(c.live_assignments(netbox, [name]), {name: []}))
    print(c.live_assignments(netbox, [name]))"
      sudo python3 -I ~/netbox_against_the_seed.py ~/seed.json --url https://10.50.1.4:8443 --cert /etc/aisec/netbox-rehearsal/tls.crt \
        --token /etc/aisec/netbox-rehearsal/tokens/aisec-collector | grep -v "not readable"; echo "exit ${PIPESTATUS[0]}"'
    ```

    Expected: the permission with `'users': []`. Then permissions `seed 6 netbox 6 differs: inventory-reader: tenant-a inventory differs in users`, the other three groups `same`, `== 4 groups compared, 1 differences`, and `exit 1`. The copy's users group reads as the live one's: the seed's four, beside the seeding and probe accounts its own install made.

12. Restore the copy from its dump through the reset account ([staging copy runbook](rehearsal-copy.md), step 20), and compare again.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'sudo ssh -F none -i /etc/aisec/netbox-rehearsal/reset/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes \
      -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/aisec/netbox/observe/known_hosts -T aisec-rehearse@10.50.0.36 id </dev/null | tail -n 1
      sudo cat /etc/aisec/netbox-rehearsal/reset/seed.sha256
      sudo python3 -I ~/netbox_against_the_seed.py ~/seed.json --url https://10.50.1.4:8443 --cert /etc/aisec/netbox-rehearsal/tls.crt \
        --token /etc/aisec/netbox-rehearsal/tokens/aisec-collector | tail -n 1; echo "exit ${PIPESTATUS[0]}"'
    ```

    Expected: the dump's SHA-256 twice, the same, after about a minute; then `== 4 groups compared, 0 differences` and `exit 0`. The live NetBox has no dump: its restore is step 14.

13. Put the tokens back on both hosts, and read both halves again.

    ```bash
    unhold() { REPLACE_WITH_SSH "$1" 'sudo sh -c "mv /etc/aisec/netbox/held/* /etc/aisec/netbox/tokens/ && rmdir /etc/aisec/netbox/held
      stat -c \"%U %a %n\" /etc/aisec/netbox/tokens /etc/aisec/netbox/tokens/*"'; }
    unhold aisec-orchestrator; unhold aisec-lab
    REPLACE_WITH_SSH aisec-orchestrator "sudo python3 -I -c $(printf %q "$code") configured --summary" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
    REPLACE_WITH_SSH aisec-lab "sudo python3 -I -c $(printf %q "$code") observed --summary" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
    ```

    Expected: `root 700` for each directory and `root 600` for each token, and `inventory-reader:within inventory-reader-control:within` twice.

14. Replace, not run: the [target VMs runbook](targets.md#rebuild) replaces the NetBox VM, then the [NetBox runbook](netbox.md), steps 5 to 20, install NetBox from the image the orchestrator keeps, make its TLS key, and seed it, which makes new tokens for every account. The new certificate's pin goes to the orchestrator and the lab VM in that runbook's steps 9 and 17.

    The compromised VM's own logs are lost with it, since the targets ship no logs ([lab against production](../security/lab-vs-production.md#detection-and-response)).

## A leaked credential

The collector's token is the credential this case takes: the platform's own token for the target, read-only, limited to the orchestrator's address ([credentials](../security/credentials.md)). A token that leaves the orchestrator is used from another address first, and NetBox refuses it there ([ADR 0039](../decisions/0039-netbox-takes-a-clients-address-from-the-connection.md)).

15. Detect: use the token from the lab VM's address, then read NetBox's journal on its VM. The token passes through the operator's terminal into the lab VM's `curl` on its standard input, and step 18 replaces it.

    ```bash
    OLD=$(REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /etc/aisec/netbox/tokens/aisec-collector')
    printf 'Authorization: Bearer %s\n' "$OLD" |
      REPLACE_WITH_SSH aisec-lab 'curl -s --max-time 8 --cacert /etc/aisec/netbox/tls.crt -w " %{http_code}\n" -H @- https://10.50.0.4:8443/api/status/'
    REPLACE_WITH_SSH aisec-netbox 'sudo journalctl --no-pager -o cat -u netbox --since -2min | grep -F "10.50.0.36 - \"GET /api/status/" | tail -n 1'
    ```

    Expected: `{"detail":"Source IP 10.50.0.36 is not permitted to authenticate using this token."} 403`, as `N.12` reads for the probe's token from the orchestrator. Then the web server's request line in NetBox's journal, `10.50.0.36 - "GET /api/status/ HTTP/2" 403` with its time: the address and the status are logged on the target, and the reason came in the answer.

16. Contain: delete the account's tokens on NetBox with the seeding token, which the NetBox VM makes ([NetBox runbook](netbox.md), step 15).

    ```bash
    REPLACE_WITH_SSH aisec-netbox 'sudo ~/netbox-install/netbox/make-netbox-token.sh seed' |
      REPLACE_WITH_SSH aisec-orchestrator "sudo sh -c 'umask 077; cat > /etc/aisec/netbox/seed-token'"
    REPLACE_WITH_SSH aisec-orchestrator 'cat > ~/revoke_netbox_tokens.py' < REPLACE_WITH_PLATFORM_CHECKOUT/validation/drills/revoke_netbox_tokens.py
    REPLACE_WITH_SSH aisec-orchestrator 'sudo python3 -I ~/revoke_netbox_tokens.py aisec-collector; echo "exit $?"'
    ```

    Expected: `deleted token N of aisec-collector: 204` once, `== 1 tokens of aisec-collector deleted`, `exit 0`.

17. Verify: the token on the orchestrator is refused, and the configured half reads nothing with it.

    ```bash
    printf 'Authorization: Bearer %s\n' "$OLD" |
      REPLACE_WITH_SSH aisec-orchestrator 'curl -s --noproxy "*" --max-time 8 --cacert /etc/aisec/netbox/tls.crt -w " %{http_code}\n" -H @- https://10.50.0.4:8443/api/status/'
    REPLACE_WITH_SSH aisec-orchestrator "sudo python3 -I -c $(printf %q "$code") configured" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json | grep -E '"verdict"|"why"' | sort -u
    ```

    Expected: `{"detail":"Invalid v2 token"} 403`; the orchestrator's shell names Squid as its proxy, which `--noproxy` leaves out. The configured half gives `"verdict": "missing"` for both accounts with the reason `users: 403 {'detail': 'Invalid v2 token'}`: a dead collector token reads as every account lacking everything, and `N.14` fails on it. A collection in this state would write `missing` against the observed half's `within`, and the verification gate would stop the job on the disagreement: reasoned from the collect command and the comparison step, not run.

18. Rotate: the seed run, which deletes each seeded account's tokens and makes new ones, then the tokens to their hosts ([NetBox runbook](netbox.md), steps 16 and 17).

    ```bash
    tar -C REPLACE_WITH_TARGETS_CHECKOUT/netbox -cf - seed.py seed.json | REPLACE_WITH_SSH aisec-orchestrator \
      'rm -rf ~/feed/netbox-seed && mkdir -p ~/feed/netbox-seed && tar -C ~/feed/netbox-seed -xf -'
    run=$(REPLACE_WITH_SSH aisec-orchestrator 'sudo mktemp -d -p /run aisec-netbox-tokens.XXXXXX')
    REPLACE_WITH_SSH aisec-orchestrator "sudo python3 -I ~/feed/netbox-seed/seed.py ~/feed/netbox-seed/seed.json $run" | grep -v "^have "
    REPLACE_WITH_SSH aisec-orchestrator "sudo install -m 600 $run/aisec-collector /etc/aisec/netbox/tokens/aisec-collector"
    for account in inventory-reader inventory-reader-control; do
      REPLACE_WITH_SSH aisec-orchestrator "sudo cat $run/$account" |
        REPLACE_WITH_SSH aisec-lab "sudo sh -c 'umask 077; cat > /etc/aisec/netbox/tokens/$account'"
    done
    REPLACE_WITH_SSH aisec-orchestrator "sudo rm -r $run /etc/aisec/netbox/seed-token ~/feed/netbox-seed ~/revoke_netbox_tokens.py"
    ```

    Expected: three `made  token for` lines, and `made  no token for aisec-deliver, 0 deleted: the copy only`. Every object is a `have` line, left out here.

19. Verify: both halves with the new tokens, and the old token once more.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "sudo python3 -I -c $(printf %q "$code") configured --summary" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
    REPLACE_WITH_SSH aisec-lab "sudo python3 -I -c $(printf %q "$code") observed --summary" < REPLACE_WITH_TARGETS_CHECKOUT/netbox/contract.json
    printf 'Authorization: Bearer %s\n' "$OLD" |
      REPLACE_WITH_SSH aisec-orchestrator 'curl -s --noproxy "*" --max-time 8 --cacert /etc/aisec/netbox/tls.crt -w " %{http_code}\n" -H @- https://10.50.0.4:8443/api/status/'
    unset OLD
    ```

    Expected: `inventory-reader:within inventory-reader-control:within` twice, and `{"detail":"Invalid v2 token"} 403`.

20. Replace: nothing, since the token was the credential and step 18 made a new one. If the leak came from the orchestrator, which holds every credential that matters, the case is the orchestrator's rebuild ([platform compute runbook](platform-compute.md#rebuild-the-orchestrator)) and a rotation of everything it holds ([credentials](../security/credentials.md)), not run.

## Record

21. Run every check with the targets checkout named ([validation](../validation/README.md)). Then save the stopped job's and the synthetic job's workflows and the audit lines, and build their records ([test evidence runbook](test-evidence.md)).

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator 'rm -f ~/netbox_against_the_seed.py ~/seed.json'
    ```

    Expected: every check passes, `G.5` and `W.10` with the new dispatch key, `N.14` and `N.17` with the new tokens. The stopped job's record has the dispatch step `Failed` and the two `revoke` lines.
