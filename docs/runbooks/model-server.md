# Model server: operator procedure

Status: Implemented on 2026-10-11. Built once. Steps 1 to 8 were run during that build. A second build from the same pins has not been run. The cleanup after a failed build and the `libgomp1` version line were added to the build script afterwards and have not been run on the worker. The unit was changed and installed again once, on 2026-10-12, to turn thinking off. Results are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md). Steps 4, 5, and 10 changed on 2026-10-16 for the feed account ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)): the scripts go to the worker from the checkout, the staged files to the feed account, and the build refuses a staged file that `artifacts.tsv` does not name. The converter's source archive got its own pin, checked by step 3 and the build. Steps 2 to 10 ran in that form on 2026-10-19, for the move to llama.cpp v0.7.0 as a pin change on a running worker, with the two extra steps under [Changing a pin](#changing-a-pin) ([worklog](../worklogs/0003-toolchain-integration.md#llamacpp-and-goose-on-the-worker)). On 2026-10-19 the model became a pin of its own, with its files in `models/`, and `measure.py` became a set of five cases, for a [comparison of models](#build-another-model). Steps 3 to 9 have not run in that form. Step 3 names the fetch window since the same day: the orchestrator has needed one since milestone 3a.

Run these steps to put llama.cpp and the starting model on the AI worker: download and verify on the orchestrator, push, build the model file on the worker, start the server, and measure it. No cloud resource changes.

## Inputs and access

| Input | Notes |
| --- | --- |
| Milestone 2, built | The [platform compute runbook](platform-compute.md). Both VMs up, the feed key in place, the package proxy working |
| SSH to both VMs over the mesh VPN | `REPLACE_WITH_SSH` below stands for the operator's `ssh` command with its options, for example `ssh -F <config>` |
| 10 GB of free disk on the orchestrator | The staged inputs stay there for the next rebuild |
| 22 GB of free disk on the worker | Only during the build. The finished install takes 2.9 GB |
| A checkout of this repository on the workstation | The scripts and pins are in `worker/model-server/` |

The design is in [ADR 0015](../decisions/0015-build-the-model-file-on-the-worker.md). Every file the build downloads is listed with its checksum: llama.cpp and the converter's packages in `worker/model-server/artifacts.tsv`, and the model's files in `worker/model-server/models/MODEL_NAME.tsv`. `MODEL_NAME` in `pins.env` names the model the server runs. The commands below use it.

The download leaves through the NAT gateway and is billed per GB.

## Check the pins

1. Confirm that the pins still name what the publishers serve. Run on the workstation.

   ```bash
   curl -sS https://huggingface.co/api/models/Qwen/Qwen3.5-4B | jq -r .sha
   gh api 'repos/ggml-org/llama.cpp/releases?per_page=100' \
     -q '[.[] | select(.prerelease == false)][0] | .tag_name'
   gh api repos/ggml-org/llama.cpp/releases/tags/b11669 \
     -q '.assets[] | select(.name == "llama-b11669-bin-ubuntu-arm64.tar.gz") | .digest'
   grep -h -E '/config.json|ubuntu-arm64' worker/model-server/artifacts.tsv worker/model-server/models/Qwen3.5-4B.tsv | cut -f1,2
   ```

   Expected: the revision in the model list's URLs, `v0.7.0` as the newest stable release, and the build's digest equal to the checksum on the `llama/` line. A stable release carries no binaries: its tag points at the commit of a numbered build, whose release has them. A newer revision or build is a decision, not a step: change the pins in a pull request first.

## Download and verify on the orchestrator

2. Copy the scripts to the orchestrator.

   ```bash
   tar -C worker/model-server -cf - . |
     REPLACE_WITH_SSH aisec-orchestrator \
     'mkdir -p feed/model-server/scripts feed/model-server/stage && tar -C feed/model-server/scripts -xf -'
   ```

   Expected: no output.

3. Open a fetch window on the edge, download every input and check it, then close the window. The orchestrator reaches the publishers only while a window is open ([edge runbook](edge-vm.md)).

   ```bash
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window open 20'
   REPLACE_WITH_SSH aisec-orchestrator 'cd feed/model-server && scripts/fetch.sh stage'
   REPLACE_WITH_SSH aisec-edge 'sudo aisec-fetch-window close'
   ```

   Expected: `open for 20 minutes, until <UTC time>, by aisec`. Then one `ok` line per file, 29 from `artifacts.tsv` and 9 for the model, then `ok    converter-src.tar (commit 620d2225cc436ab0b001e3200e590e3b286ef9ab)`. A file already staged with the right checksum prints `have` instead. About 9 GB, three minutes here. A `checksum mismatch` line stops the run and deletes the file. Do not go on. Last, `closed, by aisec`.

   A stage from before 2026-10-19 holds the model under `qwen/`. Rename it first, or its files download again: `REPLACE_WITH_SSH aisec-orchestrator 'mv feed/model-server/stage/qwen feed/model-server/stage/Qwen3.5-4B'`.

   The orchestrator only hashes these files. It never unpacks, imports, or loads one.

## Push to the worker

4. Copy the scripts and the pin list from the checkout to the worker, then the staged files from the orchestrator with the feed key.

   ```bash
   tar -C worker/model-server -cf - . |
     REPLACE_WITH_SSH aisec-worker \
     'rm -rf feed/model-server/scripts && mkdir -p feed/model-server/scripts && tar -C feed/model-server/scripts -xf -'
   REPLACE_WITH_SSH aisec-orchestrator 'cd feed/model-server && scripts/push.sh stage'
   ```

   Expected: no output from the first command. Then `9.0G	/home/aisec-feed/model-server/stage`, after about two minutes. The feed key can only unpack into that directory ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)). `push.sh` sends only the files the lists name for this model, so a stage on the orchestrator that holds other models sends none of theirs.

## Build the model file on the worker

5. Run the build as root. It takes about eight minutes, so start it detached and read the log.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cd feed/model-server &&
     sudo sh -c "nohup setsid scripts/build-model.sh /home/aisec-feed/model-server/stage > build.log 2>&1 < /dev/null &"'
   REPLACE_WITH_SSH aisec-worker 'tail -n 5 feed/model-server/build.log'
   ```

   Expected, in order in the log:

   - `all files match artifacts.tsv, models/Qwen3.5-4B.tsv, and pins.env, and nothing else is staged`
   - `libgomp1` and the installed version
   - `version: 0.7.0-dev (build 11669, commit 620d2225c)`
   - `Model successfully exported to /var/lib/aisec-model-build/Qwen3.5-4B-F16.gguf`
   - `llama_model_quantize_impl: quant size  =  2644.04 MiB (5.13 BPW)`
   - a last line with the checksum and `Qwen3.5-4B-Q4_K_M.gguf`

   The script installs `libgomp1` through the package proxy if it is missing and prints its version. It converts in a sandboxed unit named `aisec-model-build`, and removes the build account and directory when it ends, also when it fails.

   The first line proves that the staged files are the ones the repository pins, and that nothing else is staged. The lists it checks against came from the checkout in step 4, not from the orchestrator: `artifacts.tsv` and the model's list for the downloads, and `CONVERTER_SRC_SHA256` in `pins.env` for the converter's source, which the orchestrator packs from the pinned commit. A file they do not name stops the build with `not in artifacts.tsv or models/Qwen3.5-4B.tsv:` and the file's path.

6. Read the result.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cat /opt/aisec/models/SHA256SUMS; ls /var/lib/aisec-model-build; id aisec-build'
   ```

   Expected: one checksum line per model built on this worker, then `No such file or directory` and `no such user`. A build replaces the line for its own file and keeps the others. The build with `b11669` produced `85e5f901e58b042ddd5c82bf4c6c942c18367b23d5e28e061108ecae5c685af7`, and the first build, with `b11429`, `e9aee5c7...`. Whether a second build from the same pins gives the same value is untested. Record what it gives.

## Start the server

7. Install the unit and start it.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cd feed/model-server && sudo scripts/install-server.sh'
   ```

   Expected: `Active: active (running)`, and a command line from `/opt/aisec/llama.cpp/llama-b11669` that ends `--cache-ram 0 --reasoning off --no-ui --offline`. The script checks the model file against its line in `SHA256SUMS` first, and stops when there is none. Then it waits until `http://127.0.0.1:8080/health` answers.

8. Confirm that the port is closed to everything but the worker itself.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'sudo ss -ltnp | grep llama-server'
   REPLACE_WITH_SSH aisec-orchestrator \
     'curl -s -m 5 -o /dev/null -w "%{http_code}\n" http://10.40.0.36:8080/health; echo "rc=$?"'
   ```

   Expected: one listener on `127.0.0.1:8080`, then `000` and `rc=28` from the orchestrator.

   The `S` checks in `validation/platform-checks.sh` repeat this step and five more. See [validation](../validation/model-server.md).

## Measure

9. Run the measurement cases. Each of the five is a question that needs evidence, the calls for it, and an answer held to a JSON schema. Two runs take about fifteen minutes with Qwen3.5-4B.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'python3 feed/model-server/scripts/measure.py --runs 2'
   REPLACE_WITH_SSH aisec-worker \
     'sudo grep -E "^(Rss|Pss_Anon|Pss_File)" /proc/$(pgrep -x llama-server)/smaps_rollup; free -m | sed -n 2p'
   ```

   Expected: the loaded model's path first, one line per turn, a table per case, and `10 of 10 cases correct`. The script exits 1 when a case is wrong. Then the server's memory. The numbers for each model are in the [worklog](../worklogs/0003-toolchain-integration.md). On `Standard_D2ps_v6` with `b11669`, on 2026-10-19, the earlier single exchange gave about 19 prompt tokens and 6 output tokens per second with Qwen3.5-4B, and 5.30 GB resident.

   `--thinking` runs every case again with thinking asked for per request. With `--reasoning off` on the server, those requests still think: on 2026-10-19 they gave three times the output tokens of the others, and took 36 seconds for a tool call against 25.

## Clean up

10. Remove the staged inputs from the worker. Keep them on the orchestrator for the next rebuild.

    ```bash
    REPLACE_WITH_SSH aisec-worker 'sudo rm -rf /home/aisec-feed/model-server/stage && df -h / | tail -1'
    ```

    Expected: about 4.8 GB used on the worker's disk.

## After a worker rebuild

A rebuilt worker is empty. Run steps 2 to 10 again. Step 3 finds the files already staged and prints `have` for each.

## Changing a server setting

The server's options are in `worker/model-server/aisec-llama-server.service`. Change them in a pull request, then copy the unit and run step 7 again. It restarts the server, which empties its prompt cache.

```bash
REPLACE_WITH_SSH aisec-worker 'cat > feed/model-server/scripts/aisec-llama-server.service' \
  < worker/model-server/aisec-llama-server.service
REPLACE_WITH_SSH aisec-worker 'cd feed/model-server && sudo scripts/install-server.sh'
```

Expected: `Active: active (running)` with the new command line. Run step 5 of the [agent runtime runbook](agent-runtime.md#run-and-measure) afterwards: its numbers are the review of the change.

Thinking is off through `--reasoning off`. Take the option out to get the model's default back. The measured difference is in the [worklog](../worklogs/0003-toolchain-integration.md#thinking-measured-both-ways).

## Build another model

Each file in `worker/model-server/models/` is a model the build can make. `AISEC_MODEL` picks one for every script, and without it they use `MODEL_NAME` from `pins.env`. Another model's file sits beside the current one in `/opt/aisec/models`, with its own line in `SHA256SUMS`, so the server can switch to it and back.

Run steps 2 and 4 as they are, and these in place of steps 3, 5, 7, and 9. `REPLACE_WITH_MODEL` is the file's name without `.tsv`. Stop the server before the build: the converter needs the memory it holds.

```bash
REPLACE_WITH_SSH aisec-orchestrator 'cd feed/model-server && AISEC_MODEL=REPLACE_WITH_MODEL scripts/fetch.sh stage'
REPLACE_WITH_SSH aisec-orchestrator 'cd feed/model-server && AISEC_MODEL=REPLACE_WITH_MODEL scripts/push.sh stage'
REPLACE_WITH_SSH aisec-worker 'sudo systemctl stop aisec-llama-server'
REPLACE_WITH_SSH aisec-worker 'cd feed/model-server &&
  sudo sh -c "nohup setsid env AISEC_MODEL=REPLACE_WITH_MODEL scripts/build-model.sh /home/aisec-feed/model-server/stage > build.log 2>&1 < /dev/null &"'
REPLACE_WITH_SSH aisec-worker 'cd feed/model-server && sudo env AISEC_MODEL=REPLACE_WITH_MODEL scripts/install-server.sh'
REPLACE_WITH_SSH aisec-worker 'python3 feed/model-server/scripts/measure.py --runs 2'
```

Expected: as in steps 3 to 9, with the model's name in place of `Qwen3.5-4B`. Run step 10 after each build, before the next model's push. To go back, run step 7 without `AISEC_MODEL`.

Open a fetch window around the fetch, as in step 3. Remove a model nobody needs from the orchestrator's stage afterwards: `REPLACE_WITH_SSH aisec-orchestrator 'rm -rf feed/model-server/stage/REPLACE_WITH_MODEL'`.

## Changing a pin

Change `artifacts.tsv`, the model's list in `models/`, `pins.env`, and `converter-requirements.txt` together, in a pull request. Read each new checksum from the publisher: the model repository's file listing, the release's asset digest, the package index. The converter source's pin is the SHA-256 of the `git archive` command in `fetch.sh`, run on the workstation. Run the same command on the old commit first: it has to give the old pin. Then run this procedure from step 1.

On a running worker, two more steps:

- Before step 3, remove the old llama.cpp archive from the orchestrator's stage: `REPLACE_WITH_SSH aisec-orchestrator 'rm -f feed/model-server/stage/llama/llama-REPLACE_WITH_OLD_BUILD-bin-ubuntu-arm64.tar.gz'`. The build refuses a staged file that `artifacts.tsv` does not name.
- Before step 5, stop the server: `REPLACE_WITH_SSH aisec-worker 'sudo systemctl stop aisec-llama-server'`. The converter needs the memory it holds. Step 7 starts it again.

Afterwards, remove the old version's directory from `/opt/aisec/llama.cpp`.
