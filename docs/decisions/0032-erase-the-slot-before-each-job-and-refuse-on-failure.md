# 0032. The slot is erased before each job as well, and a job is refused when that fails

Status: Accepted
Date: 2026-10-23

Changes step 4 of [0030](0030-how-a-job-reaches-the-worker.md), where the job program erases the model server's slot after Goose ends and writes the outcome to the journal only.

## Context

The model server keeps the last prompt in its one slot, and the next request reuses whatever matches. 0030 erases the slot after each job so that the next job starts with nothing of this one ([#32](https://github.com/sindredg/ai-security-platform/issues/32)). Two cases leave the slot full, and nothing stops the next job ([#157](https://github.com/sindredg/ai-security-platform/issues/157)):

- **The erase fails.** The job program wrote `"slot_erased": false` to the journal, and the result still said `completed`. On 2026-10-20 the server refused every erase until it had a save path, and the second job's first turn reused the first job's prompt ([troubleshooting 12](../troubleshooting/12-slot-erase-needs-a-save-path.md)).
- **The erase never runs.** A unit stopped at its time limit, or killed, ends before the job program reaches it.

`G.10` reads the last erase, but only when the operator runs the checks, and only for the last job. The milestone 3 criterion "Cancelling a workflow stops the worker job and cleans up its session" rests on each job starting from an empty slot.

## Options

| Option | What it gives | What it costs |
| --- | --- | --- |
| Keep 0030 and rely on `G.10` | Nothing new | A full slot is found after the next job has run, if at all |
| Restart the model server before each job | A new process holds no prompt | The model is loaded again for every job. The job unit runs as a throwaway account and cannot restart a system service, so the restart needs a privileged helper on the untrusted side |
| Erase before the job as well, and refuse the job when that fails | A job starts only after an erase worked, whatever the job before it did | A server that cannot erase stops every job until the operator restarts it |

## Decision

The third option, with the outcome of the erase after the job in the result.

1. **Before the job.** Once the job line passes its checks, the job program erases the slot. Without a 200 from the server within 90 seconds, it refuses the job with `the model server's slot could not be erased`, and Goose does not start. The dispatch step fails on the refusal, and the exit handler revokes the token.
2. **After the job.** As in 0030, whatever the outcome. The result line carries `slot_erased`, true only for a 200. The dispatch step requires it as a boolean, and fails the step when it is false, after writing the result.
3. **The journal.** Each erase writes one line with the job and `slot_erased`: `"erase": "before"` for the first, the outcome for the second. `G.10` reads the last.

A restart of the model server empties the slot, so the next erase works and jobs start again.

## Trade-offs

- **A server that cannot erase stops all jobs.** That is the point: no job runs on a slot that may hold another job's prompt. The cost is availability, and the fix is a restart by the operator.
- **The first erase counts against the job's time.** It runs after the job's clock starts. Behind a prompt batch the server is still reading for an earlier job, it waits for that batch, up to 90 seconds.
- **A cancelled job still writes no result.** The outcome of its erase is in the journal only. The next job's first erase covers it.
- **A 200 is the server's word.** Nothing reads the server's memory to see that the slot is empty, as in 0030.
