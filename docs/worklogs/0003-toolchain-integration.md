# 0003. Toolchain integration

Date: 2026-10-11, in progress
Milestone: 3, toolchain integration

## Summary

The milestone is built in slices. Two are done on the system: the model server on the AI worker, and the agent runtime running headless against it with a fixture tool. A third is written and not deployed: the tool service, tested in the pipeline and on a workstation. The gate is not met.

| Gate | Result |
| --- | --- |
| A workflow starts a worker job, the agent calls one authorized tool, and a schema-checked result comes back | Open |
| A tool call for another job or target is refused by the tool service | Open on the system. Tested in the service's own tests, where nothing is deployed |
| Cancelling a workflow stops the worker job and cleans up its session | Open |
| Model memory use, latency per turn, and tokens per second are measured on the chosen size | Met for the model server alone, and for one agent run beside it on a fixture. Not measured with a tool over the network |
| Component footprint on the orchestrator is measured | Open |
| The threat model covers dispatch, workload identity, and the AI-specific threats | Open |
| Every image and every model input is pinned by digest and verified on the orchestrator | Met for the model server (38 files and one commit) and for the agent runtime (one file). No image exists yet |
| Every tool call is logged with caller, job, and decision, out of the worker's reach | Open. The service prints the line, tested. Nothing stores it yet |
| A revoked or expired job token is refused | Open on the system. Tested in the service's own tests |
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
- The agent runtime has called the server on one fixture question. See the limits of that slice below.
- A second build from the same pins has not been run, so nobody knows whether the model file's checksum repeats.
- The validation script has seven checks for the model server, `S.1` to `S.7`. They were shown to fail on broken inputs with stubs, and passed on the system on 2026-10-12, in a run of 101 passed, 0 failed. See [validation](../validation/model-server.md).

## Slice: the agent runtime

Goose runs headless on the worker, against the model server on localhost, with one tool. It is not a service: `run-agent.sh` starts one run in a transient unit. The procedure is the [agent runtime runbook](../runbooks/agent-runtime.md).

The tool is a fixture. It runs on the worker and returns the same synthetic evidence the model server measurement used, so the two sets of numbers can be compared. The tool service on the orchestrator ([ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)) is not built.

### Version

Read from the official source on 2026-10-12.

| Component | Version | Source |
| --- | --- | --- |
| Goose | `v1.54.0`, released 2026-10-08, Apache-2.0. The static `aarch64-unknown-linux-musl` build | GitHub releases, `aaif-goose/goose`. The newest release, and not a prerelease. The project moved there from `block/goose` |

The pinned checksum is the digest the release lists for the file. A download on the workstation gave the same value.

### What Goose does, found before it went on the worker

Run on the workstation on 2026-10-12, with the pinned binary, against a stub that records each request and answers with a fixed reply. The run was inside a network namespace with a loopback interface and nothing else.

| Question | Finding | Consequence |
| --- | --- | --- |
| Does it run with no network? | Yes. It made no request the namespace could not serve | The worker's containment does not break it |
| Can the tool set be restricted? | `--no-profile` with one `--with-extension` put exactly one tool in the request, `evidence__get_evidence`. With no extension named, none | The extension that runs shell commands is never loaded |
| What else does it send the model? | One extra request per run, to make up a title for the session | Turned off with `GOOSE_DISABLE_SESSION_NAMING`. On this machine it would cost about 20 seconds a job |
| What settings does it send? | The messages, the tools, and a request to stream. No temperature, no token limit, no thinking switch | The model's defaults apply. Thinking was on, until the server was told otherwise below |
| What does it write? | A session database and a log of every request with its full prompt, under `GOOSE_PATH_ROOT`. `--no-session` does not stop either | The run script points that at the unit's private `/tmp` |
| Is the text output the answer? | No. With `--quiet` it still prints each tool call and the tool's result | Checks read the JSON transcript, and only the agent's last message |

### Install

```bash
scripts/fetch.sh stage && scripts/push.sh stage    # on the orchestrator
sudo scripts/install-agent.sh stage                 # on the worker
```

16:10:00 to 16:10:15 UTC. `ok    goose/goose-aarch64-unknown-linux-musl.tar.gz`, 49 MB staged, `the archive matches artifacts.tsv` on the worker. The install script does not run the binary. The first thing to execute it was the sandboxed unit.

Tested locally before the install, each against a broken input:

| Script | Broken input | Result |
| --- | --- | --- |
| `fetch.sh` | A wrong checksum in `artifacts.tsv` | `checksum mismatch, removed`, exit 1, nothing left in the staging directory |
| `install-agent.sh` | One byte added to the archive | `FAILED`, exit 1, before anything is written |
| `install-agent.sh` | No line for the archive in `artifacts.tsv` | Refused, exit 1 |
| `evidence_tool.py` | Eleven malformed or hostile requests: not JSON, another tool, an extra argument, a path as the reference, a list as the reference | Each refused or ignored, and the tool kept running. The list crashed the first version, which is why this test exists |
| `check_answer.py` | Ten broken transcripts: the right answer with no tool call, with two calls, with another reference, with a tool error, with a run that did not complete, an answer naming one of the two record types, an empty input | Each failed. A transcript where the agent said only "ok" failed too, which a search of the whole output would have passed |

### The run

```bash
sudo scripts/measure-agent.sh --runs 3      # on the worker
```

16:16:57 to 16:20:23 UTC. `3 of 3 runs correct`: in each, one call to the tool for `ev-0001`, no tool error, and a last message that named both record types the evidence shows in excess.

| | Turn 1, the tool call | Turn 2, the answer | Whole run |
| --- | --- | --- | --- |
| First run after the install, at 16:10 | 670 prompt tokens in 37.1 s, 124 output tokens in 20.7 s | 109 new prompt tokens in 7.4 s, 191 output tokens in 31.9 s | 97.4 s |
| Three measured runs, median | 4 new prompt tokens in 0.3 s, 122 output tokens in 20.3 s | 109 new prompt tokens in 7.3 s, 240 output tokens in 40.2 s | 67.0 s (63.4, 67.0, 73.6) |

The token counts and times are the model server's own, from its journal. The wall time is the script's.

| Agent | Value | How |
| --- | --- | --- |
| Memory peak of the unit, Goose and the tool together | 54.8 to 55.6 MB | What `systemd-run` reports when the unit ends |
| CPU time | 0.35 s per run | Same |
| Exposure score of the transient unit | 1.3 | `systemd-analyze security aisec-agent-job.service`, during a run |
| Accounts | Goose and the tool both ran as `aisec-agent-job`, an account that exists only while the unit does | `ps`, during a run |

| Session and cleanup | Result |
| --- | --- |
| During a run | Two private directories for the unit under `/tmp` and `/var/tmp`, holding `sessions.db` and `llm_request.*.jsonl` |
| After each run | `unit: inactive`, `private tmp directories: 0` |
| A second run started while the first existed | `Failed to start transient service unit: Unit aisec-agent-job.service was already loaded or has a fragment file.`, exit 1. The first run finished and was correct |

What the numbers say:

- **Goose's own prompt costs 285 tokens.** The first turn is 670 tokens, against 385 for the same exchange sent bare. That is 15 seconds on this machine, once. It is less than feared, because one tool is loaded and none of Goose's own.
- **The model server's prompt cache is what makes later runs fast, and it crosses jobs.** The measured runs skipped all but 4 tokens of the first turn, because the server still held the previous run's prompt. A real job with different evidence pays for its own prompt. It also means something of one job is still in the server's memory when the next starts. Nothing reads it back, and the next prompt overwrites it, but it is state that outlives the session. Not cleared today.
- **Thinking was on, and Goose has no switch for it.** Every turn in the transcripts starts with a thinking block. The earlier measurement put thinking at 11 seconds a turn. Turning it off is a setting on the model server. It was measured both ways afterwards and turned off: see [Thinking, measured both ways](#thinking-measured-both-ways).
- **The agent needs almost nothing.** 56 MB beside a model that leaves 4 GB.
- **Prompt processing ran at 14.8 tokens per second on the short second turn**, against 18.1 on the long first one and 18.7 in the model server measurement. Not investigated.

### Thinking, measured both ways

The model thinks by default and Goose cannot turn that off, so the server decides. The unit now starts it with `--reasoning off`. The option was read from the pinned build's own `--help` on the worker.

What proves the flag works was written down before the runs: with thinking on, each of the agent's two turns carries a thinking part. With the flag, none does, the first turn produces far fewer output tokens, and the answers stay correct. `measure-agent.sh` got a line that counts the part types of the agent's messages for this. The run with thinking on is that line's failing case: it has to show the thinking parts before their absence means anything.

```bash
sudo scripts/measure-agent.sh --runs 3      # thinking on, the server as it had run since 2026-10-11
sudo scripts/install-server.sh              # the unit with --reasoning off, one restart at 17:06:35 UTC
sudo scripts/measure-agent.sh --runs 4      # thinking off, the first run with an empty prompt cache
```

On the worker, 2026-10-12, between about 17:02 and 17:11 UTC. The restart time is systemd's. The run times are worked out from the server's own log stamps, not read from a clock.

| | Thinking on | Thinking off |
| --- | --- | --- |
| Correct | 3 of 3 | 4 of 4 |
| Parts of the agent's messages | `{'thinking': 2, 'toolRequest': 1, 'text': 1}` in every run | `{'toolRequest': 1, 'text': 1}` in every run |
| Turn 1 output, the tool call | 118 tokens in 19.4 s (94, 118, 123) | 35 tokens in 5.7 s, the same in all four |
| Turn 2 output, the answer | 215 tokens in 35.9 s (172, 215, 266) | 61 tokens in 10.2 s (58, 61, 94). 48 in the first run |
| Whole run, prompt cache holding the previous run | 59.1 s (55.8, 59.1, 72.5) | 23.8 s (23.3, 23.8, 29.5) |
| Whole run, first after a server start | 97.4 s, from the install at 16:10 | 58.3 s |
| Turn 1 prompt, first after a server start | 670 tokens in 37.1 s | 672 tokens in 37.0 s |

Values with three in brackets are the median and the three runs. The thinking-off medians leave out the first run, which is in its own row.

After the restart the unit's command line reads `--cache-ram 0 --reasoning off --no-ui --offline`, from `systemctl status`.

What the numbers say:

- **Thinking costs 35 seconds a run and bought nothing here.** That is 60 % of a run with a warm cache, and 39 seconds of the first run after a start. All seven answers named both record types. The question is easy, so this says thinking is not needed for the plumbing, not that it never helps.
- **The time went into output tokens.** Generation runs at 6 tokens per second with or without it. Thinking made the model write 3.4 times as many tokens on the first turn and 3.5 times as many on the second.
- **Runs got steadier.** The first turn was 35 tokens four times out of four. With thinking on it ranged from 94 to 123.
- **The prompt grew by 2 tokens**, 672 against 670 on the first turn, and 111 against 109 on the second. Not looked into. The likely cause is the template closing an empty thinking block, which is a guess.
- **The slot still crosses jobs.** Runs 2 to 4 processed 4 prompt tokens on the first turn, as before. Nothing here changes that.

Thinking stays off. To turn it back on, take `--reasoning off` out of the unit and run `install-server.sh` again. A job that needs it would have to ask for it per request, and whether the server honours a request's own `enable_thinking` while the flag is set has not been tested. `measure.py` asks exactly that way for its two thinking rows, so those rows are unproven on the server as it runs now.

The [platform checks](../validation/README.md) were run after the restart, at 17:17 UTC: 100 passed, 1 failed. The seven model server checks, `S.1` to `S.7`, passed, so the unit's exposure score is still 1.3 with the new option. The failure is `U.1`: three security updates published that day were pending on the orchestrator (`libdbi-perl`, `libx11-6`, `libx11-data`), with the next unattended run due at 06:12 UTC on 2026-10-13. It has nothing to do with this change, and it is not fixed here.

### Limits

- One easy question, one tool, fifteen correct runs in all. It shows the runtime, the sandbox, and the cleanup work. It says nothing about investigation quality.
- The tool is a local fixture. No tool has been called over the network, with a token, or refused.
- The answer is free text checked by a search for two names. No result is held to a schema yet. The earlier measurement found that the server refuses a response schema together with tool definitions, and how Goose's own structured output deals with that is untested.
- The time limit and the turn limit on the unit have not been driven to their limits. Cancelling a run has not been tested.
- The sandbox settings are the model server's, and nothing was taken out to make Goose run. Whether each one holds was not tested one by one: the score is the evidence, and a score is not a test.
- Nothing dispatches a job. The run was started by hand, as root. The account, the forced command, and the job document of [ADR 0012](../decisions/0012-dispatch-over-ssh-with-a-forced-command.md) are not built.
- The validation script has no checks for the agent runtime yet.

## Slice: the tool service

The MCP server of [ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) is written, with its tests and its place in the pipeline. It is not deployed. There is no image, no pod, no certificate on the orchestrator, and no rule for its port. Every result in this slice comes from a workstation or from the pipeline, and none from the running system.

### Versions

Read from PyPI, the Python release list, and the image registry on 2026-10-13.

| Thing | Version | Pinned in |
| --- | --- | --- |
| Python | 3.15.0, released 2026-10-09 | The image digest in the checks workflow |
| MCP SDK | 2.3.0, released 2026-10-02 | `tool-service/requirements.in` |
| PyJWT, cryptography | 2.15.1 and 50.0.2 | The same file |
| Starlette, Uvicorn, jsonschema, AnyIO | 1.8.0, 0.54.0, 4.26.0, 4.15.1 | The same file. The SDK needs all four, and the service imports them |
| pytest | 9.1.1 | `tool-service/requirements-dev.in` |

`requirements.txt` is compiled from `requirements.in` and holds 28 packages, each with its hashes. `requirements-dev.txt` adds 5 for the tests. The pipeline installs both with `--require-hashes`.

Python 3.15.0 was four days old when it was pinned. Every package in the list ships a build for it, and the tests pass on it. A first release of a new Python line can still carry defects that a later patch release fixes. The pin is the newest stable release, and it moves with the next one.

### What Goose needs, found before the service was written

ADR 0014 named one thing the build had to show first: that the agent runtime speaks MCP over HTTP with TLS, a bearer token, and a restricted tool set. If it could not, the transport had to change before any code existed.

Run on a workstation on 2026-10-13, with the pinned Goose 1.54.0 binary, against a stub tool server and a stub model server. The run was inside a network namespace with a loopback interface and nothing else. The expected result of each case was written down before the run.

| Case | Expected | Result |
| --- | --- | --- |
| Certificate signed by a private authority, right token | The tool stub logs `initialize`, `tools/list`, and `tools/call`, each over TLS with the token. The model sees one tool | As expected. TLS 1.3 |
| One self-signed certificate, not marked as an authority, right token | The same | As expected |
| One self-signed certificate, marked as an authority | Not predicted | Refused by Goose. No request reaches the stub |
| Wrong token | 401. No `tools/call`. The model sees no tool | As expected |
| An authority the client does not trust | No request reaches the stub | As expected |
| A name that is not in the certificate | No request reaches the stub | As expected |
| No trust file given | No request reaches the stub | As expected |

What else came out of it:

| Finding | Consequence |
| --- | --- |
| `--no-profile` drops the extensions a recipe names. Goose ran with no tool and no error | The job runner leaves the option out. With an empty configuration directory the model still saw exactly one tool |
| There is no command-line option for a request header | The token goes in a recipe file in the unit's private `/tmp`. Nothing on a command line holds it, which is what [ADR 0012](../decisions/0012-dispatch-over-ssh-with-a-forced-command.md) asks for |
| Goose copies the recipe, token included, into its session database | That file is under `GOOSE_PATH_ROOT`, in the same private `/tmp`, and is deleted with the unit |
| `SSL_CERT_FILE` replaces the system's trust store | The agent trusts the tool service's certificate and nothing else |
| A tool server that cannot be reached is a warning on standard error. Goose exits 0 and answers without the tool | The job runner has to treat that as a failed job. Not built |
| Goose sends `server/discover` before `initialize` | The service answers both |
| After a 401, Goose asks eight OAuth discovery paths and posts to `/register` | The service refuses every path that is not the tool endpoint, with a line in the audit log for each |

The pinned certificate is why [ADR 0013](../decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md) no longer has a private authority.

### What was written

```text
tool-service/aisec_tools/   The server: gate, job registry, registration, audit line, entry point
tool-service/aisec_tools/tools/   The one tool, get_evidence
tool-service/tests/         153 tests
tool-service/count_lines.py The size check
policies/tool-service.json  The rules
```

The service has two listeners, both with TLS 1.3 and the same certificate.

- **The tool listener** is the one the worker reaches. A request passes two stages. The gate, in front of the SDK, decides who is calling: the path, the token, the size, and the shape of the message. The call handler, behind the SDK, decides what that job may do: the tool, the arguments against the policy's schema, the call limit, the result size, and whether the job is still alive when the tool returns. The handler is the authority, because it works on what the SDK parsed.
- **The registration listener** is for the dispatch step. It takes a job's ID, target, tools, lifetime, and the SHA-256 digest of its token, and it revokes by job ID. The caller's service account token is checked offline against a public key.

Two things the design did not have before the code:

- **The SDK can refuse what the gate let through**, for example a request with another host name. The gate watches the reply and writes a refusal line for it, so no refusal goes unrecorded.
- **`$` in a pattern lets a trailing newline through** in Python. The policy's patterns end with a lookahead that nothing follows, and a test holds every pattern in the file to that.

Evidence is stored per target, and a job's scope names one target. Two jobs on the same target read the same evidence. That is enough for synthetic evidence. It is not enough once a collector writes evidence for one job.

### Size

ADR 0014 gives small a number. The count is lines that hold code, in the server without its tools.

```bash
cd tool-service && python3 count_lines.py 300 aisec_tools/*.py
```

```text
    0  aisec_tools/__init__.py
   52  aisec_tools/__main__.py
   10  aisec_tools/audit.py
  102  aisec_tools/gate.py
   23  aisec_tools/http.py
   55  aisec_tools/jobs.py
   50  aisec_tools/registration.py
  292  total, limit 300
```

The first version was 342 lines and the check failed it. What brought it down was moving rules out of the code: the shape of a message and of a registration are schemas in the policy file now, and the listeners and the registration caller are settings there. Run with a limit of 291, the check fails with "the server is 1 lines over the limit".

Eight lines of room is not much. The next tool does not count, but the next feature of the server does.

### Tests

```bash
cd tool-service && python -m pytest -q
```

Result: 153 passed, on Python 3.15.0 with the packages installed by hash, and on Python 3.12.3. Both on a workstation. The tests drive the two applications in one process, without a socket and without TLS.

They cover each case in the roadmap's [hostile-input table](../roadmap.md#hostile-input-tests-for-the-tool-service), the registration caller, the tool on its own, the policy file, and the size check. Every refusal is held to the same three things: nothing of a result in the reply, exactly one audit line with the reason, and no token in the reply or the line.

A test that cannot fail proves nothing, so each control was removed in turn in a copy of the service, and the tests were run against the copy. 27 changes, one at a time: the late result kept, a schema not checked, a revoked or expired token accepted, the call limit off, any path let through, the read without a limit, the caller's subject, audience, or issuer not checked, a token written to the audit line, and so on.

| Run | Changes caught | Not caught |
| --- | --- | --- |
| First | 24 of 27 | The tool scope check, the declared length check, the algorithm list |
| After two tests were fixed | 26 of 27 | The algorithm list |

The first run found two tests that passed for the wrong reason. The out-of-scope tool did not exist as a function, so it was refused whether or not scope was checked. The oversized body was caught while reading, so nothing showed that the declared length was checked first. Both tests now fail when their control is removed.

The one left: accepting `HS256` in the algorithm list changes nothing the tests can see. The key is held as a public key object, and PyJWT will not use that as a shared secret. The algorithm list is a second layer behind the first, and the test for that attack passes with either one in place.

The tests also found a defect. PyJWT raises a `TypeError`, not one of its own errors, when a token's algorithm does not fit the key. A token signed with an RSA algorithm against an elliptic curve key crashed the registration handler. The algorithm now follows the type of the key, and the error is a refusal.

### End to end, on a workstation

The real service on Python 3.15.0, started as `python -m aisec_tools` with a self-signed certificate, the pinned Goose, and a stub model that asks for one piece of evidence. Inside a network namespace with loopback only, on 2026-10-13.

Expected, written before the run: the job registers, Goose's answer holds the marker from the evidence file, and the audit log has one allowed call with the file's size. After the job is revoked, Goose gets no tool, the answer holds no marker, and the audit log has refusals and no call.

| Step | Result |
| --- | --- |
| Register the job over TLS, with a signed caller token | 201 |
| Register with the job's own token | 401 |
| Offer TLS 1.2 to the tool listener | The handshake fails |
| Goose run with the live token | Exit 0. The marker is in the answer. The model was offered one tool |
| Revoke the job | 200 |
| Goose run with the revoked token | Exit 0, with the warning that the tool server failed. No marker. The model was offered no tool |

The audit log of that run, with the time and the digest left out:

```text
register  allowed  e2e-1  127.0.0.1
request   refused         127.0.0.1                 caller not accepted
call      allowed  e2e-1  127.0.0.1  get_evidence   result_bytes 295
revoke    allowed  e2e-1  127.0.0.1
request   refused  e2e-1  127.0.0.1                 revoked token
request   refused         127.0.0.1                 not the tool endpoint   (nine lines)
```

295 is the size of the evidence file. The token and the marker appear nowhere in the log. The nine last lines are Goose looking for an OAuth server after the refusal.

### The pipeline

| Change | Status |
| --- | --- |
| Ruff lints `tool-service/` with more rules than the default set, and checks the formatting of every Python file | **Tested** locally and in the pipeline with Ruff 0.17.0. Three files under `worker/` were reformatted to get there. The pipeline failed the first push on a shebang in a file that is not executable, which the local run cannot see on a file system without executable bits |
| A new job counts the lines and runs the tests on the pinned Python image | **Tested** in the pipeline on the pull request: 292 lines against the limit of 300, and 153 passed, in the container |
| The dependency scan covers the tool service's two package lists, and blocks | **Tested** locally with Trivy 0.75.0: 28 and 5 packages read, no finding, exit 0. A list with two old releases gave 18 findings and exit 1 |
| Dependabot watches `tool-service/` | **Configured, not tested**. Whether it keeps the hashes in step is unknown until its first update |

### Limits

- Nothing is deployed. No image is built, and the pod limits, the network policies, the port rule, and the certificate do not exist. The gate rows in the summary stay open.
- The audit line is printed. Nothing captures it or stores it out of the service's reach yet.
- The offline check of a service account token was tested with keys made for the test. That K3s signs with a key this check accepts, and what its issuer is called, were reasoned and not observed. The issuer, audience, and account name in the policy file are placeholders until the deployment.
- The end-to-end run had a stub for the model, no systemd sandbox, and one machine. The unit on the worker allows no address but localhost today.
- Jobs live in memory. A restart of the service forgets every job, so every token stops working. That fails closed, and it ends running jobs.
- Nothing limits the rate of refused requests before a token is checked, beyond sixteen connections at a time.
- The job runner on the worker is not changed. It still starts Goose with the fixture and `--no-profile`.
