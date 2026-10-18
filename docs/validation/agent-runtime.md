# Agent runtime

Goose on the AI worker, one static binary that runs once per job in a transient unit. Nothing about it runs between jobs, so the checks read what is installed and what a finished job leaves behind. The procedure is the [agent runtime runbook](../runbooks/agent-runtime.md), and the component is described on the [AI worker page](../components/ai-worker.md#the-agent-runtime).

Status: **tested** on the running system on 2026-10-18. `G.1`, `G.3`, and `G.4` pass. `G.2` fails: the fixture on the worker is the one installed on 2026-10-12, and two of its files were reformatted in the repository afterwards ([worklog](../worklogs/0004-edge-network-and-monitoring.md#before-the-ai-part)).

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `G.1` | The Goose binary is root's and the one pinned in this checkout | The binary is what reads the model's output and decides which tool to call. The install checked the archive, and nothing checked the unpacked file afterwards | Owner and mode `root 755`, and the SHA-256 of `/opt/aisec/goose/goose-<version>/goose` equals `GOOSE_BINARY_SHA256` in `worker/agent-runtime/pins.env`. The pin was read from the release archive after the archive matched `artifacts.tsv`, not from the worker. The path names the pinned version, so a pin that moves without an install fails here |
| `G.2` | The fixture tool and its prompts are the ones in this checkout | The fixture tool runs inside every agent run, and `check_answer.py` judges the result | One SHA-256 over the SHA-256 lines of the four files in `/opt/aisec/agent-fixture`, equal to the same over `worker/agent-runtime/fixture` |
| `G.3` | No agent job unit is loaded | A unit left loaded blocks the next job, which uses the same name, and keeps its private `/tmp` | `systemctl show aisec-agent-job -p LoadState` is `not-found` |
| `G.4` | No agent job left its private directories | A job's session database and its log of every prompt live there. One left behind is one job's data where the next can find it (T19, A6) | No directory under `/tmp` or `/var/tmp` for the unit's private `/tmp` |

`G.3` and `G.4` assume the checks run between jobs, as every check run has so far. During a job they read `loaded` and `2`. Once dispatch runs jobs on its own, a check run that meets one needs a look before it counts as a failure.

## Broken inputs

Each check's own probe line, run on the worker on 2026-10-18 at 19:04 UTC with the input changed. Read-only.

| Check | Broken input | Read |
| --- | --- | --- |
| `G.1` | `/usr/bin/python3` instead of the binary | `root 777 d1b87c36...` |
| `G.1` | A version that is not installed, `goose-0.0.0` | Empty |
| `G.2` | None needed: it fails on the live worker | The digest of the fixture as of commit `3eaa3ca` |
| `G.3` | The model server's unit, which is loaded | `loaded` |
| `G.4` | The model server's unit, which keeps a private `/tmp` | `2` |

## Limits

- `G.1` reads the file. A binary replaced while a run holds it open is not seen until the next check run.
- The sandbox of the transient unit is not checked. It exists only during a run, and `run-agent.sh` sets it from the operator's checkout. Its exposure score was read once, during a run on 2026-10-12.
- The tool set is a flag on the command line. No check reads which tools a run loads.
