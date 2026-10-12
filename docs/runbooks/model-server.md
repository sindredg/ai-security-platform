# Model server: operator procedure

Status: Implemented on 2026-10-11. Built once. Steps 1 to 8 were run during that build. A second build from the same pins has not been run. The cleanup after a failed build and the `libgomp1` version line were added to the build script afterwards and have not been run on the worker. The unit was changed and installed again once, on 2026-10-12, to turn thinking off. Results are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md).

Run these steps to put llama.cpp and the starting model on the AI worker: download and verify on the orchestrator, push, build the model file on the worker, start the server, and measure it. No cloud resource changes.

## Inputs and access

| Input | Notes |
| --- | --- |
| Milestone 2, built | The [platform compute runbook](platform-compute.md). Both VMs up, the feed key in place, the package proxy working |
| SSH to both VMs over the mesh VPN | `REPLACE_WITH_SSH` below stands for the operator's `ssh` command with its options, for example `ssh -F <config>` |
| 10 GB of free disk on the orchestrator | The staged inputs stay there for the next rebuild |
| 22 GB of free disk on the worker | Only during the build. The finished install takes 2.9 GB |
| A checkout of this repository on the workstation | The scripts and pins are in `worker/model-server/` |

The design is in [ADR 0015](../decisions/0015-build-the-model-file-on-the-worker.md). Every file the build downloads is listed with its checksum in `worker/model-server/artifacts.tsv`.

The download leaves through the NAT gateway and is billed per GB.

## Check the pins

1. Confirm that the pins still name what the publishers serve. Run on the workstation.

   ```bash
   curl -sS https://huggingface.co/api/models/Qwen/Qwen3.5-4B | jq -r .sha
   gh api repos/ggml-org/llama.cpp/releases/tags/b11429 \
     -q '.assets[] | select(.name == "llama-b11429-bin-ubuntu-arm64.tar.gz") | .digest'
   grep -E 'qwen/config.json|ubuntu-arm64' worker/model-server/artifacts.tsv | cut -f1,2
   ```

   Expected: the revision in the `artifacts.tsv` URLs, and the release digest equal to the checksum on the `llama/` line. A newer revision or build is a decision, not a step: change the pins in a pull request first.

## Download and verify on the orchestrator

2. Copy the scripts to the orchestrator.

   ```bash
   tar -C worker/model-server -cf - . |
     REPLACE_WITH_SSH aisec-orchestrator \
     'mkdir -p feed/model-server/scripts feed/model-server/stage && tar -C feed/model-server/scripts -xf -'
   ```

   Expected: no output.

3. Download every input and check it.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'cd feed/model-server && scripts/fetch.sh stage'
   ```

   Expected: one `ok` line per file, 38 in all, then `ok    converter-src.tar (commit d81235049384534c167caea52b85a694f6103d14)`. About 9 GB, three minutes here. A `checksum mismatch` line stops the run and deletes the file. Do not go on.

   The orchestrator only hashes these files. It never unpacks, imports, or loads one.

## Push to the worker

4. Copy the scripts and the staged files with the feed key.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'cd feed/model-server && scripts/push.sh stage'
   ```

   Expected: `9.0G	feed/model-server/stage`, after about two minutes.

## Build the model file on the worker

5. Run the build as root. It takes about eight minutes, so start it detached and read the log.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cd feed/model-server &&
     sudo sh -c "nohup setsid scripts/build-model.sh stage > build.log 2>&1 < /dev/null &"'
   REPLACE_WITH_SSH aisec-worker 'tail -n 5 feed/model-server/build.log'
   ```

   Expected, in order in the log:

   - `all files match artifacts.tsv`
   - `libgomp1` and the installed version
   - `version: 0.6.0-dev (build 11429, commit d81235049)`
   - `Model successfully exported to /var/lib/aisec-model-build/Qwen3.5-4B-F16.gguf`
   - `llama_model_quantize_impl: quant size  =  2644.04 MiB (5.13 BPW)`
   - a last line with the checksum and `Qwen3.5-4B-Q4_K_M.gguf`

   The script installs `libgomp1` through the package proxy if it is missing and prints its version. It converts in a sandboxed unit named `aisec-model-build`, and removes the build account and directory when it ends, also when it fails.

   The first line proves the push arrived intact. The list it checks against came in the same push, so it says nothing about the orchestrator. Step 3 on the orchestrator is the check against the pins in the repository.

6. Read the result.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cat /opt/aisec/models/SHA256SUMS; ls /var/lib/aisec-model-build; id aisec-build'
   ```

   Expected: one checksum line, then `No such file or directory` and `no such user`. The first build produced `e9aee5c7eedb88bab8415f4d768c6348e7083d7ca661950ab82a2bd84cfd38c4`. Whether a second build gives the same value is untested. Record what it gives.

## Start the server

7. Install the unit and start it.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'cd feed/model-server && sudo scripts/install-server.sh'
   ```

   Expected: `Active: active (running)`, and a command line that ends `--cache-ram 0 --reasoning off --no-ui --offline`. The script checks the model file against `SHA256SUMS` first and waits until `http://127.0.0.1:8080/health` answers.

8. Confirm that the port is closed to everything but the worker itself.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'sudo ss -ltnp | grep llama-server'
   REPLACE_WITH_SSH aisec-orchestrator \
     'curl -s -m 5 -o /dev/null -w "%{http_code}\n" http://10.40.0.36:8080/health; echo "rc=$?"'
   ```

   Expected: one listener on `127.0.0.1:8080`, then `000` and `rc=28` from the orchestrator.

   The `S` checks in `validation/platform-checks.sh` repeat this step and five more. See [validation](../validation/model-server.md).

## Measure

9. Run the measurement exchange. It takes about six minutes.

   ```bash
   REPLACE_WITH_SSH aisec-worker 'python3 feed/model-server/scripts/measure.py --runs 3'
   REPLACE_WITH_SSH aisec-worker \
     'sudo grep -E "^(Rss|Pss_Anon|Pss_File)" /proc/$(pgrep -x llama-server)/smaps_rollup; free -m | sed -n 2p'
   ```

   Expected: twelve lines with `"ok": true`, then a table. On `Standard_D2ps_v6` the first run gave about 19 prompt tokens and 6 output tokens per second, and 5.96 GB resident.

   That run was made before the unit had `--reasoning off`. The script asks for thinking per request in half its turns. Whether the server honours that with the flag set is untested, so the two thinking rows may now show the same output as the others.

## Clean up

10. Remove the staged inputs from the worker. Keep them on the orchestrator for the next rebuild.

    ```bash
    REPLACE_WITH_SSH aisec-worker 'rm -rf feed/model-server/stage && df -h / | tail -1'
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

## Changing a pin

Change `artifacts.tsv`, `pins.env`, and `converter-requirements.txt` together, in a pull request. Read each new checksum from the publisher: the model repository's file listing, the release's asset digest, the package index. Then run this procedure from step 1.
