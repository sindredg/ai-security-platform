# 12. The model server refuses a slot erase without a save path

Date: 2026-10-20
Milestone: 3, toolchain integration

## Symptom

The first two jobs through the job socket on the worker, `hand-1` and `hand-2` at 19:27 UTC, steps 10 and 11 of the [agent runtime runbook](../runbooks/agent-runtime.md#jobs-over-the-socket), both logged that the slot was not erased:

```text
{"job": "hand-1", "outcome": "ended", "slot_erased": false}
{"job": "hand-2", "outcome": "cancelled", "slot_erased": false}
```

The model server's log shows what the erase is for. `hand-2`'s first turn processed 4 prompt tokens, because the slot still held `hand-1`'s prompt:

```text
selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.783
prompt eval time =     274.20 ms /     4 tokens
```

`hand-1`'s first turn processed all 1004 of its prompt tokens, in 57.5 seconds.

## Cause

Confirmed. The job program's request, sent by hand on the worker:

```text
$ curl -s -X POST "http://127.0.0.1:8080/slots/0?action=erase"
{"error":{"code":501,"message":"This server does not support slots action. Start it with `--slot-save-path`","type":"not_supported_error"}}
```

llama.cpp's server at the pinned commit refuses every slot action, erase included, when no save path is set (`post_slots` in `tools/server/server-context.cpp`). Its README names the save path under save and restore only, and the job program was written from the README ([worklog](../worklogs/0003-toolchain-integration.md#slice-jobs-over-a-socket)). The job program's tests use a stub that answers 200, so nothing sent the request to the real server before the worker did.

## Fix

The unit starts the server with `--slot-save-path /opt/aisec/llama.cpp/slots`, a directory that `install-server.sh` creates empty and owned by root. The server's account cannot write it, and the unit's read-only file system would stop it anyway. A save fails, and there is nothing to restore. From the same source, a save that cannot open its file answers `Unable to save slot` and the server keeps running: `llama_state_seq_save_file` catches the error.

The server takes a cancel only between prompt batches of up to 2048 tokens, and the erase waits behind it. With the slot empty, a cancel during the first turn waits for that turn's prompt, about a minute for the fixture. The job program now gives the erase 90 seconds instead of 10, and the cancel steps in both runbooks wait for the unit to end. `G.10` reads the last job's line.

## Verification

Run on the worker on 2026-10-20 at 20:12 UTC with the fix installed. The erase request answered with `n_erased`, a save by hand failed with `Unable to save slot`, and a completed job (`hand-3`) and a cancelled job (`hand-4`) each ended with `"slot_erased": true`. The completed job's first turn processed its whole 1004-token prompt at 17.5 tokens per second, not a warm-cached handful, so no prompt carried over from the job before it. `G.10` passed ([worklog](../worklogs/0003-toolchain-integration.md#installed-and-run-on-the-worker)).
