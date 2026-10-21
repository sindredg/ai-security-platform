# Agent runtime: operator procedure

Status: Implemented on 2026-10-12. Installed once. Every step below was run during that install. Results are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#slice-the-agent-runtime). Steps 2 to 4 and 7 changed on 2026-10-16 for the feed account ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)): the worker gets the scripts from the checkout and the staged archive in the feed account's directory. Steps 2 to 7 ran in that form on 2026-10-19, for Goose 1.55.0 ([worklog](../worklogs/0003-toolchain-integration.md#llamacpp-and-goose-on-the-worker)). Steps 8 to 12, for jobs that arrive over a socket ([ADR 0030](../decisions/0030-how-a-job-reaches-the-worker.md)), were written on 2026-10-19 and ran on 2026-10-20: the job and the cancel worked, and the model server refused the slot erase ([troubleshooting 12](../troubleshooting/12-slot-erase-needs-a-save-path.md)). The fix went on the same day, and steps 8 to 12 ran again in their current form, with step 10 naming `G.10` and step 11 waiting for the unit to end: a completed and a cancelled job each erased the slot, three malformed tasks were refused, and `G.10` passed.

Run these steps to put Goose on the AI worker and prove one headless run against the local model server: download and verify on the orchestrator, push, install, run, and measure. No cloud resource changes. Nothing is left running: the agent is a program that runs once per job, not a service.

## Inputs and access

| Input | Notes |
| --- | --- |
| The model server, running | The [model server runbook](model-server.md). Check `S.2` and `S.5` pass |
| SSH to both VMs over the mesh VPN | `REPLACE_WITH_SSH` below stands for the operator's `ssh` command with its options, for example `ssh -F <config>` |
| A checkout of this repository on the workstation | The scripts and the pin are in `worker/agent-runtime/` |

## Check the pin

1. Compare the pinned checksum with the digest the release lists.

   ```bash
   gh api repos/aaif-goose/goose/releases/tags/v1.55.0 \
     -q '.assets[] | select(.name == "goose-aarch64-unknown-linux-musl.tar.gz") | .digest'
   grep -v '^#' worker/agent-runtime/artifacts.tsv | cut -f1
   ```

   Expected: the same 64 characters twice, the first with `sha256:` in front. A newer release is a decision, not a step: change the pin in a pull request first.

## Download and push

2. Copy the scripts to the orchestrator, and the scripts and the pin list to the worker.

   ```bash
   tar -C worker/agent-runtime -cf - . |
     REPLACE_WITH_SSH aisec-orchestrator \
     'mkdir -p feed/agent-runtime/scripts feed/agent-runtime/stage && tar -C feed/agent-runtime/scripts -xf -'
   tar -C worker/agent-runtime -cf - . |
     REPLACE_WITH_SSH aisec-worker \
     'rm -rf feed/agent-runtime/scripts && mkdir -p feed/agent-runtime/scripts && tar -C feed/agent-runtime/scripts -xf -'
   ```

   Expected: no output. The worker's copy of the pin list comes from the checkout, not from the orchestrator ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)).

3. Download and verify, then push to the worker.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'cd feed/agent-runtime && scripts/fetch.sh stage && scripts/push.sh stage'
   ```

   Expected: `ok    goose/goose-aarch64-unknown-linux-musl.tar.gz`, then `49M	/home/aisec-feed/agent-runtime/stage`. A file that does not match its pin is removed and the script stops.

## Install

4. Install Goose and the fixture on the worker.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cd feed/agent-runtime && sudo scripts/install-agent.sh /home/aisec-feed/agent-runtime/stage'
   ```

   Expected: `the archive matches artifacts.tsv`, one checksum line for `goose`, then `the binary matches GOOSE_BINARY_SHA256`. The script checks the archive again, takes the one file out of it, checks that file against its own pin, and does not run it. A binary that does not match is removed and the script fails. On the next check run, `G.1` and `G.2` pass ([agent runtime checks](../validation/agent-runtime.md)).

## Run and measure

5. Run the fixture question three times.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cd feed/agent-runtime && sudo scripts/measure-agent.sh --runs 3'
   ```

   Expected, after two minutes:

   - three lines with `"ok": true` and `"tool_calls": 1`
   - `{'toolRequest': 1, 'text': 1}` as the parts of the agent's messages. A `thinking` entry means the model server runs without `--reasoning off`
   - `Finished with result: success` for each unit, with a memory peak near 56 MB
   - two `prompt eval time` lines per run from the model server
   - `unit: inactive` and `private tmp directories: 0` after each run
   - `3 of 3 runs correct`

   The first run after the model server starts takes about 60 seconds, and took 86 with Goose 1.55.0 and llama.cpp `b11669` on 2026-10-19. Later runs take 23 to 30, because the server still holds the start of the prompt. With thinking on, the figures were 97 and 56 to 73.

6. Confirm that a run cannot start while another exists, and that the session directory exists only during a run.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cd feed/agent-runtime &&
     (sudo scripts/run-agent.sh < /opt/aisec/agent-fixture/question.txt > /dev/null 2>&1 &); sleep 12
     sudo find /tmp /var/tmp -maxdepth 1 -name "systemd-private-*aisec-agent-job*" | wc -l
     sudo scripts/run-agent.sh < /opt/aisec/agent-fixture/question.txt; echo "rc=$?"
     while systemctl is-active -q aisec-agent-job; do sleep 3; done
     sudo find /tmp /var/tmp -maxdepth 1 -name "systemd-private-*aisec-agent-job*" | wc -l'
   ```

   Expected: `2`, then `Failed to start transient service unit: Unit aisec-agent-job.service was already loaded or has a fragment file.` and `rc=1`, then `0`.

## Clean up

7. Remove the staged archive from the worker. Keep it on the orchestrator for the next rebuild.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'sudo rm -rf /home/aisec-feed/agent-runtime/stage && df -h / | tail -1'
   ```

   Expected: about 5.0 GB used on the worker's disk.

## Jobs over the socket

How a dispatched job arrives on the worker: an account the dispatch key logs in to, a forced command that relays to a socket, and a socket that starts one sandboxed unit per job ([ADR 0030](../decisions/0030-how-a-job-reaches-the-worker.md)). These steps install it and send a job to the socket by hand, before any workflow exists. The dispatch key comes later, with the dispatch secret.

8. Install it. The scripts are on the worker from step 2.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cd feed/agent-runtime && sudo scripts/install-job.sh'
   ```

   Expected: `root aisec-job 660 /run/aisec-job/agent.sock`, then `active`. On the next check run, `G.6` to `G.9` pass, and `G.5` fails until the dispatch key is installed ([agent runtime checks](../validation/agent-runtime.md)).

9. Make a job token on the workstation and register a job for it, as the [tool service runbook](tool-service.md#round-trip) does. Only the digest goes to the orchestrator.

   ```bash
   TOKEN=$(openssl rand -hex 32)
   DIGEST=$(printf %s "$TOKEN" | sha256sum | cut -d' ' -f1)
   REG='sudo ~/feed/tool-service/platform/tool-service/register.sh'
   REPLACE_WITH_SSH aisec-orchestrator "$REG register hand-1 $DIGEST - 1200"
   ```

   Expected: `201 {"job": "hand-1"}`.

10. Send the fixture question to the socket as the job account, and read the result. The small client sends one line and keeps its side open until the result comes back, as the job runner does for a dispatch session.

    ```bash
    SEND='import socket, sys
    s = socket.socket(socket.AF_UNIX)
    s.connect("/run/aisec-job/agent.sock")
    s.sendall(sys.stdin.buffer.readline())
    print(s.makefile().readline(), end="")'
    jq -nc --arg token "$TOKEN" --arg task "$(cat worker/agent-runtime/fixture/question.txt)" \
      '{job: "hand-1", token: $token, task: $task, max_turns: 6, seconds: 600}' |
      REPLACE_WITH_SSH aisec-worker "sudo -u aisec-job python3 -I -c '$SEND'"
    ```

    Expected, after one to two minutes: one JSON line with `"status": "completed"`, `"tool_calls": 1`, `"tool_errors": 0`, an answer that names `tenancy.contact` and `circuits.circuit`, and a `transcript`: the instructions from `system.txt`, the question, the `get_evidence` call, the evidence, and the answer, with no `"type": "cut"` part. The tool service's audit file on the orchestrator has a `call allowed hand-1` line for `get_evidence`. This is the agent calling the tool service from the worker, which no run had done before. On the next check run, `G.10` passes: the job erased the model server's slot.

11. Cancel a job while it runs: send a second job, close the connection after 20 seconds, and look for what it left.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "$REG register hand-2 $(printf %s "$TOKEN" | rev | sha256sum | cut -d' ' -f1) - 1200"
    LEAVE='import socket, sys, time
    s = socket.socket(socket.AF_UNIX)
    s.connect("/run/aisec-job/agent.sock")
    s.sendall(sys.stdin.buffer.readline())
    time.sleep(20)
    s.shutdown(socket.SHUT_WR)
    print(repr(s.recv(65536)))'
    jq -nc --arg token "$(printf %s "$TOKEN" | rev)" --arg task "$(cat worker/agent-runtime/fixture/question.txt)" \
      '{job: "hand-2", token: $token, task: $task, max_turns: 6, seconds: 600}' |
      REPLACE_WITH_SSH aisec-worker "sudo -u aisec-job python3 -I -c '$LEAVE'"
    REPLACE_WITH_SSH aisec-worker 'for _ in $(seq 1 60); do
        [ "$(systemctl list-units --all --no-legend "aisec-agent-job@*" | wc -l)" = 0 ] && break
        sleep 2
      done
      systemctl list-units --all --no-legend "aisec-agent-job@*" | wc -l
      sudo find /tmp /var/tmp -maxdepth 1 -name "systemd-private-*aisec-agent-job@*" | wc -l
      journalctl --no-pager -o cat -u "aisec-agent-job@*" --since -3min | grep outcome'
    ```

    Expected: `b''`: a cancelled job writes nothing back. Then, within two minutes, `0` and `0`: no unit and no private directory left. Then a line with `"outcome": "cancelled"` and `"slot_erased": true`. The unit outlives the cancel by up to a minute: the server takes the cancel, and the erase after it, only when it has read the prompt batch it is on ([troubleshooting 12](../troubleshooting/12-slot-erase-needs-a-save-path.md)). The reversed token is a second token for the second job, so the two jobs never share one.

12. Revoke both jobs.

    ```bash
    REPLACE_WITH_SSH aisec-orchestrator "$REG revoke hand-1; $REG revoke hand-2"
    unset TOKEN DIGEST
    ```

    Expected: `200` twice.

## After a worker rebuild

A rebuilt worker is empty. Run the [model server runbook](model-server.md) first, then steps 2 to 7 here. Step 3 finds the file already staged and prints `have`.

## Changing the pin

Change `artifacts.tsv` and `pins.env` together, in a pull request. Read the new checksum from the release's asset digest. Read `GOOSE_BINARY_SHA256` from the archive itself, after its checksum matched, on the workstation:

```bash
echo "REPLACE_WITH_ARCHIVE_SHA256  goose-aarch64-unknown-linux-musl.tar.gz" | sha256sum --check
tar -xzf goose-aarch64-unknown-linux-musl.tar.gz -O ./goose | sha256sum
```

Expected: `OK`, then the binary's checksum. Then run this procedure from step 1. A new release can change the prompt Goose sends and the files it writes, so step 5's numbers are part of the review.
