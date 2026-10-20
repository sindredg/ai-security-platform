# Agent runtime

Goose on the AI worker, one static binary that runs once per job in a transient unit. Nothing about it runs between jobs, so the checks read what is installed and what a finished job leaves behind. The procedure is the [agent runtime runbook](../runbooks/agent-runtime.md), and the component is described on the [AI worker page](../components/ai-worker.md#the-agent-runtime).

Status: **tested** on the running system on 2026-10-19. `G.1` to `G.4` pass, with Goose 1.55.0 and the fixture installed again that day ([worklog](../worklogs/0003-toolchain-integration.md#llamacpp-and-goose-on-the-worker)). `G.2` failed from 2026-10-18 until then: the fixture on the worker was the one installed on 2026-10-12, and two of its files had been reformatted in the repository afterwards ([worklog](../worklogs/0004-edge-network-and-monitoring.md#before-the-ai-part)). `G.5` to `G.9`, for how a dispatched job arrives ([ADR 0030](../decisions/0030-how-a-job-reaches-the-worker.md)), were written on 2026-10-19 and have not run against the worker. Before `install-job.sh` runs there, `G.5` to `G.8` fail on absence, as expected.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `G.1` | The Goose binary is root's and the one pinned in this checkout | The binary is what reads the model's output and decides which tool to call. The install checked the archive, and nothing checked the unpacked file afterwards | Owner and mode `root 755`, and the SHA-256 of `/opt/aisec/goose/goose-<version>/goose` equals `GOOSE_BINARY_SHA256` in `worker/agent-runtime/pins.env`. The pin was read from the release archive after the archive matched `artifacts.tsv`, not from the worker. The path names the pinned version, so a pin that moves without an install fails here |
| `G.2` | The fixture tool and its prompts are the ones in this checkout | The fixture tool runs inside every agent run, and `check_answer.py` judges the result | One SHA-256 over the SHA-256 lines of the four files in `/opt/aisec/agent-fixture`, equal to the same over `worker/agent-runtime/fixture` |
| `G.3` | No agent job unit is loaded | A unit left loaded blocks the next job, which uses the same name, and keeps its private `/tmp` | `systemctl show aisec-agent-job -p LoadState` is `not-found` |
| `G.4` | No agent job left its private directories | A job's session database and its log of every prompt live there. One left behind is one job's data where the next can find it (T19, A6) | No directory under `/tmp` or `/var/tmp` for the private `/tmp` of the fixture's unit or of a dispatched job's unit |
| `G.5` | The dispatch key is restricted to the orchestrator and the job runner | The key lives in the cluster. On the worker it has to run one command and nothing else (T46) | One line in `/home/aisec-job/.ssh/authorized_keys`, `root root 644`, with `from="10.40.0.4",restrict,command="/usr/local/sbin/aisec-job-runner"` before the key |
| `G.6` | The job account has no other group, no sudo, and not its own home | Its only right is to connect to the job socket | `id -nG` is `aisec-job`, `sudo -l` lists nothing, and the home is root's |
| `G.7` | The job socket listens, and only root and the job account may use it | Any process that can connect starts a job | The socket unit is `active`, and the socket is `root aisec-job 660` |
| `G.8` | The worker runs the job runner, program, and units in this checkout | They are the boundary on the worker, and the sandbox is in the unit file | One SHA-256 over the five installed files, in install order, equal to the same over the checkout, with the Goose path filled into the service template as `install-job.sh` does |
| `G.9` | No dispatched job's unit is loaded between jobs | A unit left loaded keeps its private `/tmp`, and the socket allows one connection at a time | `systemctl list-units --all 'aisec-agent-job@*'` lists nothing |

`G.3`, `G.4`, and `G.9` assume the checks run between jobs, as every check run has so far. During a job they read `loaded` and `2`. Once dispatch runs jobs on its own, a check run that meets one needs a look before it counts as a failure.

## Broken inputs

Each check's own probe line, run on the worker on 2026-10-18 at 19:04 UTC with the input changed. Read-only.

| Check | Broken input | Read |
| --- | --- | --- |
| `G.1` | `/usr/bin/python3` instead of the binary | `root 777 d1b87c36...` |
| `G.1` | A version that is not installed, `goose-0.0.0` | Empty |
| `G.2` | None needed: it fails on the live worker | The digest of the fixture as of commit `3eaa3ca` |
| `G.3` | The model server's unit, which is loaded | `loaded` |
| `G.4` | The model server's unit, which keeps a private `/tmp` | `2` |
| `G.8` | Locally, on 2026-10-19, not on the worker: the five files installed into a temporary directory the way `install-job.sh` does, then `MemoryMax` changed in the unit, then the runner removed | `match`, then `differ` twice |

## Limits

- `G.1` reads the file. A binary replaced while a run holds it open is not seen until the next check run.
- The sandbox of the transient unit is not checked. It exists only during a run, and `run-agent.sh` sets it from the operator's checkout. Its exposure score was read once, during a run on 2026-10-12.
- The tool set is a flag on the command line. No check reads which tools a run loads.
