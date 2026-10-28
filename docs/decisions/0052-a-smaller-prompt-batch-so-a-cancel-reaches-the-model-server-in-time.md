# 0052. A smaller prompt batch so a cancel reaches the model server in time

Status: Accepted
Date: 2026-10-28

## Context

A job that reaches its time limit is cancelled on the worker, and the job program then erases the model server's slot, waiting 90 seconds for the erase ([troubleshooting 12](../troubleshooting/12-slot-erase-needs-a-save-path.md)). The server takes a cancel only between prompt batches, and its default batch is 2048 tokens. Late in a job the server reads a prompt at about 7 tokens per second, so one batch can take about 290 seconds, and the erase fails behind it ([#199](https://github.com/sindredg/ai-security-platform/issues/199)).

The next job erases the slot before it starts, so no job ran on another job's prompt. Until then the slot held the timed-out job's prompt, and the dispatch step failed the job for it. The figures are from job `nb-10251751-b` on 2026-10-25.

## Options

| Option | What it changes | What it costs |
| --- | --- | --- |
| A longer erase wait | `ERASE_SECONDS` to about 300, and the dispatch step's wait past the limit with it | Every timed-out job holds the worker up to five minutes longer. The slot still holds the prompt that long |
| A smaller prompt batch | `--batch-size 512` on the server's command line | Prompt reading may slow: more batches per prompt. To be measured |
| Both | The two above | The costs of both |
| Cancel the server's request earlier | The job program would have to end the model request itself, not Goose | Goose owns the request. A change to it, or a proxy in front of the server |

## Decision

**The server's prompt batch is 512 tokens, and the waits stay.** At the slowest rate measured, 7 tokens per second, a batch is about 75 seconds, inside the 90-second erase wait. `S.8` reads the value from the unit's command line.

## Trade-offs

- **Prompt throughput may fall.** llama.cpp reads a prompt in batches of this size, and a smaller batch means more of them. The first prompt of a NetBox job, about 3,800 tokens, took 309 seconds at 2048 on 2026-10-28, and the drill measures it at 512.
- **The margin is from one job's rates.** A slower rate, from a longer context or a larger model, makes a batch longer than the wait again. Then the wait moves, with the dispatch step's.
- **Not seen when this was written:** a timed-out job's erase succeeding at 512, and the throughput at 512. Both come from milestone 6's drill.
