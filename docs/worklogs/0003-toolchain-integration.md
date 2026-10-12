# 0003. Toolchain integration

Date: 2026-10-11, in progress
Milestone: 3, toolchain integration

## Summary

The milestone is built in slices. One is done: the model server on the AI worker. The gate is not met.

| Gate | Result |
| --- | --- |
| A workflow starts a worker job, the agent calls one authorized tool, and a schema-checked result comes back | Open |
| A tool call for another job or target is refused by the tool service | Open |
| Cancelling a workflow stops the worker job and cleans up its session | Open |
| Model memory use, latency per turn, and tokens per second are measured on the chosen size | Met for the model server alone. Not measured with the agent runtime beside it |
| Component footprint on the orchestrator is measured | Open |
| The threat model covers dispatch, workload identity, and the AI-specific threats | Open |
| Every image and every model input is pinned by digest and verified on the orchestrator | Met for the model server: 38 files and one commit. No image exists yet |
| Every tool call is logged with caller, job, and decision, out of the worker's reach | Open |
| A revoked or expired job token is refused | Open |
| A pod in a workload namespace cannot open a connection to the internet | Open |
| The worker's journal is copied to the orchestrator on a schedule | Open |

## Slice: the model server

llama.cpp serves Qwen3.5-4B on the worker, on localhost. The model file was built on the worker from Qwen's own weights ([ADR 0015](../decisions/0015-build-the-model-file-on-the-worker.md)). The procedure is the [model server runbook](../runbooks/model-server.md).

### Versions

Read from the official sources on 2026-10-11.

| Component | Version | Source |
| --- | --- | --- |
| llama.cpp | Build `b11429`, commit `d81235049384534c167caea52b85a694f6103d14`, released 2026-10-05 | GitHub releases. The newest stable tag is `v0.6.0`, from the same day. It ships no binaries. The numbered builds do, and every one is labelled a prerelease |
| Model | `Qwen/Qwen3.5-4B`, revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, Apache-2.0 | The publisher's repository. Still its newest revision on the day |
| Converter packages | PyTorch 2.11.0 (CPU build), transformers 4.57.6, numpy 2.3.5, and 24 more | The converter's requirements file at that commit, resolved for CPython 3.14 on aarch64 |
| pip | 26.2.1 | The package index. Run from its wheel, not installed |
| `libgomp1` | 16-20260322-1ubuntu1 | The Ubuntu archive, through the package proxy |

The plan named Qwen3-4B-Instruct-2507, from August 2025. Qwen3.5-4B replaced it in March 2026.

One deviation from upstream: the converter pins `numpy~=2.2.6`, and that series has no build for Python 3.14. The build uses 2.3.5. PyTorch comes from its own CPU index, because the build on the general package index pulls in GPU libraries.

### Download and verify

```bash
scripts/fetch.sh stage      # on the orchestrator
```

38 files matched their pinned SHA-256, and the converter's source was fetched as the pinned commit. 21:20:56 to 21:23:24 UTC, 9.0 GB. The orchestrator did not unpack or load anything.

The two weight files are 5,329,398,688 and 3,990,429,408 bytes. Their checksums in `artifacts.tsv` are the ones the publisher's repository lists for them.

### Push

```bash
scripts/push.sh stage       # on the orchestrator
```

21:23:38 to 21:25:26 UTC, over SSH with the feed key.

### Build on the worker

```bash
sudo scripts/build-model.sh stage    # on the worker
```

| Step | Result |
| --- | --- |
| Check the pushed files again | `all files match artifacts.tsv` |
| Unpack the binaries | `version: 0.6.0-dev (build 11429, commit d81235049)` |
| Convert to 16-bit float | 441 tensors, 8,665,619,808 bytes, 2 min 25 s |
| Quantize to `Q4_K_M` | 8253.72 MiB to 2644.04 MiB, 5.13 bits per weight, 209.8 s |
| Install | `/opt/aisec/models/Qwen3.5-4B-Q4_K_M.gguf`, 2,783,446,368 bytes |
| SHA-256 of the result | `e9aee5c7eedb88bab8415f4d768c6348e7083d7ca661950ab82a2bd84cfd38c4` |

The conversion ran in a transient unit with its own account, no network, and no view of `/home`. It fit in the worker's 8 GiB without swap. The unit's memory peak was 7.69 GB, which counts the page cache of the files it read and wrote, so it is a ceiling and not the converter's own use. That was not measured separately.

The build account and directory were gone afterwards: `id aisec-build` returned `no such user`.

Three attempts failed before the one that worked. All three were in the build script, and the scripts in the repository are the fixed ones.

| Failure | Cause | Fix |
| --- | --- | --- |
| `python3: can't open file '.../pip-*.whl/pip'` | A shell pattern does not expand through a file as if it were a directory. Confirmed | Resolve the wheel's name first |
| pip: `No space left on device` | pip unpacks into the temporary directory, and the sandbox's own is small. Confirmed by moving it | `TMPDIR` inside the build directory |
| `tar: Cannot open: Function not implemented`, then PyTorch `failed to map segment from shared object` | Hypothesis: with `DynamicUser=yes` the state directory is mounted with mapped ownership, and that mount refuses these operations. It was listed as owned by `nobody` from outside. Not investigated further | A real system account for the build, deleted afterwards |

### The server

```bash
sudo scripts/install-server.sh       # on the worker
```

| Check | Command | Result |
| --- | --- | --- |
| Running and enabled | `systemctl is-enabled aisec-llama-server` | `enabled`, `active (running)` |
| Listens on localhost only | `sudo ss -ltnp \| grep llama-server` | `127.0.0.1:8080` |
| Closed from the orchestrator | `curl -m 5 http://10.40.0.36:8080/health` | No connection, exit code 28 |
| Sandbox | `systemd-analyze security aisec-llama-server.service` | Exposure 1.3 |

The [platform checks](../validation/README.md) were run after the install: 94 passed, 0 failed. Containment of the worker is unchanged.

The server runs with 2 threads, an 8192-token context, one slot, no web interface, and its RAM prompt cache off. The default for that cache is 8192 MiB, more than the machine has.

At load the server warns that 14 tensors of block 32 are unused. They belong to the model's multi-token prediction head, which this server does not use. They cost about 70 MB of file.

### Measurements

`Standard_D2ps_v6`, 2 vCPUs, 8 GiB. `measure.py --runs 3`, started 21:46 UTC, with prompt caching off so every turn pays for its whole prompt.

The exchange is a question that needs evidence, one tool definition, the tool call, the tool's answer, and a verdict held to a JSON schema.

| Mode | Turn | Correct | Prompt tokens | Output tokens | Prompt tokens/s | Output tokens/s | Seconds per turn |
| --- | --- | --- | --- | --- | --- | --- | --- |
| No thinking | Tool call | 3 of 3 | 387 | 32 | 18.8 | 6.1 | 25.7 |
| No thinking | Verdict | 3 of 3 | 250 | 45 | 18.6 | 6.0 | 20.8 |
| Thinking | Tool call | 3 of 3 | 385 | 98 | 18.7 | 6.0 | 36.7 |
| Thinking | Verdict | 3 of 3 | 248 | 115 | 18.7 | 6.0 | 32.4 |

Values are medians. The three runs of each turn differed by less than 0.2 s.

| Memory and start | Value | How |
| --- | --- | --- |
| Resident, right after load | 5.75 GB: 3.10 GB anonymous, 2.65 GB the mapped model file | `/proc/<pid>/smaps_rollup` |
| Resident, after an exchange | 5.96 GB: 3.31 GB anonymous | Same |
| Available to everything else | 4.1 GB | `free -m` |
| Start, model file in the page cache | 3.0 s to `model loaded` | The unit's journal |
| Start, page cache dropped | 25.7 s | Same, after `echo 3 > /proc/sys/vm/drop_caches` |

What the numbers say:

- **The prompt is the cost.** A 387-token prompt takes 20 of the 26 seconds. An agent runtime's own system prompt and tool list will be several times that. Prompt caching, which was off here, is what keeps later turns short.
- **Thinking adds 11 seconds a turn** on this exchange and changed no answer.
- **Tool calling works through the model's own template.** The server returned one parsed call with the right argument every time.
- **A response schema and tool definitions cannot go in the same request.** The server answers `400 failed to parse grammar`. The verdict turn sends the schema without the tools.
- **The mapped file can be given back under pressure, the anonymous part cannot.** So the floor is about 3.3 GB, and the agent has 4 GB to live in. Why the anonymous part is that large for an 8192-token context was not investigated.

### Limits

- Twelve correct turns on one easy, fixed exchange show that the plumbing works. They say nothing about investigation quality.
- No agent runtime has called the server yet. Goose's own prompt size and tool format are unmeasured.
- A second build from the same pins has not been run, so nobody knows whether the model file's checksum repeats.
- The validation script has no checks for the model server yet.
