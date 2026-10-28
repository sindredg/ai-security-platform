# Model server

llama.cpp serves one model on the worker, on `127.0.0.1:8080`. Nothing outside the worker is meant to reach it, and the file it loads was built on the worker from pinned inputs. The design is [ADR 0015](../decisions/0015-build-the-model-file-on-the-worker.md). The procedure is the [model server runbook](../runbooks/model-server.md).

Status: **tested** on the running system on 2026-10-12. `validation/platform-checks.sh` reported 101 passed, 0 failed, with all seven `S` checks among them. Before that run, each check was run locally with stubs against the broken inputs listed below, and failed.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `S.1` | The worker's rules drop the orchestrator on port 8080 | The server has no key on its port. The worker's rules let the orchestrator in on port 22 and nothing else | TCP from the orchestrator to `10.40.0.36:8080` times out. Nothing listens on that address (`S.4`), so `refused` would mean the rules let the packet in |
| `S.2` | The unit is active | No model, no agent | `systemctl is-active` |
| `S.3` | The unit starts at boot | A restarted worker comes back without a hand | `systemctl is-enabled` |
| `S.4` | The only listener on 8080 is `llama-server`, on loopback | A second address on that port is the server exposed. Another program on it is not the server | Every listener on the port from `ss -ltnp`, with its address and program name, equals `127.0.0.1:8080 llama-server` |
| `S.5` | The server answers with a loaded model | An active unit can still be loading, or stuck | `/health` on loopback returns 200. The server returns 503 while it loads |
| `S.6` | The unit's exposure score is 1.3 | The server parses a model file and every prompt, so its sandbox is the control. A setting dropped from the unit moves the score | `systemd-analyze security` |
| `S.7` | The model file the server loads matches its checksum from the build | The file is 2.78 GB of weights that nothing else looks at after the build | The path after `--model` on the unit's command line, hashed and compared with its line in `SHA256SUMS` |
| `S.8` | The prompt batch is 512 tokens | A cancel reaches the server between batches. A longer batch outlasts the erase wait, and a timed-out job leaves its prompt in the slot ([ADR 0052](../decisions/0052-a-smaller-prompt-batch-so-a-cancel-reaches-the-model-server-in-time.md)) | The value after `--batch-size` on the unit's command line |

`S.1` and `S.4` are two layers of one claim. `S.4` says the server does not listen where the network can see it. `S.1` says the network would drop the packet anyway.

## Broken inputs

No broken input was made on the running system: that would mean stopping or changing the server. Run on the workstation on 2026-10-12, with the system tools replaced by stubs that print what the real tools print. One good input passed all seven. Each of these failed its check and no other. The one exception is a unit that does not exist, which fails `S.6` and `S.7`:

| Check | Broken input | Reported |
| --- | --- | --- |
| `S.1` | The connection is refused, opens, or the probe gives no answer | `refused`, `open`, empty |
| `S.2` | The unit has failed, or no answer | `failed`, empty |
| `S.3` | The unit is disabled | `disabled` |
| `S.4` | The listener is on `0.0.0.0`, on `*`, on a second address as well, belongs to `python3`, is absent, or is on port 18080 | The listeners found, or empty |
| `S.5` | The server returns 503, or there is no connection | `503`, `000` |
| `S.6` | The score is 1.5, or the unit does not exist | `1.5`, empty |
| `S.7` | One byte added to the file, an empty `SHA256SUMS`, no `SHA256SUMS`, a wrong checksum on the line, a `SHA256SUMS` that lists another file that matches, a unit that loads a file with no line, no model directory, no unit | `differ` |
| `S.8` | A command line without `--batch-size`, the unit before the change, or one with `--batch-size 2048` | empty, `2048` |

The formats the probes parse were read from the real tools on the workstation: `ss -Hltnp`, `systemctl show -p ExecStart`, and the last line of `systemd-analyze security`, on systemd 255. The worker runs a newer systemd. The run on the system confirms its output parses the same way: `S.4`, `S.6`, and `S.7` each got a value and it was the expected one.

## Limits of these checks

- `S.7` compares the file with a checksum stored next to it. It catches a file that changed since the build. It does not catch someone with root on the worker, who can rewrite both. The repository pins no checksum for the result, because a second build from the same pins has not been run and nobody knows whether the checksum repeats.
- `S.6` is a score, not a list of settings. Two changes that cancel out pass. A systemd release that scores differently fails, and then the unit has to be read again before the expected value moves.
- `S.6` reads the unit as systemd has it loaded. A unit file edited and not reloaded does not show.
- `S.5` proves the server answers. It does not prove the output is any good. The measurement exchange in the [runbook](../runbooks/model-server.md#measure) is the test of that, and it is not part of this script because it takes six minutes.
- Nothing here tests the port from the mesh. The [mesh policy](../components/mesh-vpn.md#access-policy) grants ports 22 and 6443 and no other, and no check tries 8080 from a mesh device.
