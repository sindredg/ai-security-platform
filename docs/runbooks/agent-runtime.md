# Agent runtime: operator procedure

Status: Implemented on 2026-10-12. Installed once. Every step below was run during that install. Results are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#slice-the-agent-runtime). Steps 2 to 4 and 7 changed on 2026-10-16 for the feed account ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)): the worker gets the scripts from the checkout and the staged archive in the feed account's directory. Not yet run in that form.

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
   gh api repos/aaif-goose/goose/releases/tags/v1.54.0 \
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

   Expected: `the archive matches artifacts.tsv`, then one checksum line for `goose`, equal to `GOOSE_BINARY_SHA256` in `pins.env`. The script checks the archive again, takes the one file out of it, and does not run it. On the next check run, `G.1` and `G.2` pass ([agent runtime checks](../validation/agent-runtime.md)).

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

   The first run after the model server starts takes about 60 seconds. Later runs take 23 to 30, because the server still holds the start of the prompt. With thinking on, the figures were 97 and 56 to 73.

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

## After a worker rebuild

A rebuilt worker is empty. Run the [model server runbook](model-server.md) first, then steps 2 to 7 here. Step 3 finds the file already staged and prints `have`.

## Changing the pin

Change `artifacts.tsv` and `pins.env` together, in a pull request. Read the new checksum from the release's asset digest. Read `GOOSE_BINARY_SHA256` from the archive itself, after its checksum matched, on the workstation:

```bash
echo "REPLACE_WITH_ARCHIVE_SHA256  goose-aarch64-unknown-linux-musl.tar.gz" | sha256sum --check
tar -xzf goose-aarch64-unknown-linux-musl.tar.gz -O ./goose | sha256sum
```

Expected: `OK`, then the binary's checksum. Then run this procedure from step 1. A new release can change the prompt Goose sends and the files it writes, so step 5's numbers are part of the review.
