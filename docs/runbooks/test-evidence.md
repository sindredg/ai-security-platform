# Test evidence: operator procedure

Status: Implemented on 2026-10-26, when steps 1 and 2 ran on the live system, read only, for every workflow at once, and step 5 for the twelve evaluation (eval) jobs. The other records came from output saved by earlier runs, through the same builder. Steps 6, 8, and 9 ran on the workstation.

This turns a run set's jobs into records under [`docs/evidence/records/`](../evidence/records/) and the pages generated from them ([evidence](../evidence/README.md)). Argo deletes a workflow 24 hours after it ends, so steps 1 to 3 come first.

## Inputs and access

| Input | Notes |
| --- | --- |
| `REPLACE_WITH_SSH` | The operator's `ssh` command with its options, and a certificate signed today. Host alias `aisec-orchestrator` |
| A checkout of this repository | Run from its root |
| A directory outside the repository | `REPLACE_WITH_RAW`, for the raw output. It holds the transcripts and the task, which stay out of the repository |
| The run set's name | `REPLACE_WITH_SET`: the date and time of its first job, then a few words, as in `2026-10-25-2308-scored-cases` |
| Each job's name | `REPLACE_WITH_JOB`, the workflow's name |

## Save the output

1. Read each workflow, within 24 hours of its end.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator \
     'sudo k3s kubectl -n orchestration get workflow REPLACE_WITH_JOB -o json' > REPLACE_WITH_RAW/REPLACE_WITH_JOB.json
   ```

   Expected: a JSON object with `status.phase` and `status.nodes`. `NotFound` means Argo has deleted it, and only output saved some other way can give its record.

2. Read the tool service (an MCP server)'s audit log.

   ```bash
   REPLACE_WITH_SSH aisec-orchestrator 'sudo cat /var/log/aisec/tool-audit.jsonl' > REPLACE_WITH_RAW/audit.jsonl
   ```

   Expected: one JSON line per decision, each job's under its name in `job`.

3. For a NetBox job, save what the collect command printed, from step 11 of the [evidence collection runbook](evidence-collection.md), as `REPLACE_WITH_RAW/REPLACE_WITH_JOB.collected`.

   Expected: a line that starts with the job's name, and one `ACCOUNT:CONFIGURED/OBSERVED` pair per account.

## Build the records

4. Write the run set's header in `docs/evidence/records/REPLACE_WITH_SET.json`: `title`, `short`, `milestone`, `tested`, `changed`, `setup`, `source`, `links`, and `"jobs": []`.

   Expected: `tested` under 30 words, and `changed` and `source` at most three sentences each.

5. Add each job.

   ```bash
   python3 -I validation/evidence/record.py docs/evidence/records/REPLACE_WITH_SET.json \
     REPLACE_WITH_RAW/REPLACE_WITH_JOB.json REPLACE_WITH_RAW/audit.jsonl REPLACE_WITH_RAW/REPLACE_WITH_JOB.collected
   ```

   Expected: `REPLACE_WITH_JOB: Succeeded, 3 calls`, with the job's own phase and count. `not written` with two sets of verdicts means the collection and the verification gate disagree: find out why first. Leave out the last argument for a synthetic job.

   For a job whose fix was proposed, add the bundle, each delivery's result, and the fix's pull request in the targets repository. Copy them from the orchestrator's `/var/lib/aisec/proposals/` and `/var/lib/aisec/delivery/results/` first.

   ```bash
   python3 -I validation/evidence/record.py docs/evidence/records/REPLACE_WITH_SET.json \
     REPLACE_WITH_RAW/REPLACE_WITH_JOB.json REPLACE_WITH_RAW/audit.jsonl REPLACE_WITH_RAW/REPLACE_WITH_JOB.collected \
     --proposal REPLACE_WITH_RAW/proposal.json --delivery REPLACE_WITH_RAW/delivery-1.json --pr REPLACE_WITH_PR
   ```

   Expected: the same line. The page then gets a fixes table, and the job a remediation proposal and a delivery section.

6. Write the pages.

   ```bash
   python3 -I validation/evidence/render.py
   ```

   Expected: `wrote N pages`. A problem line names its record and nothing is written: a missing field, something not to publish, a lesson that names a missing job, or a broken page rule.

7. Read each new output, the record's `answer`, and each note before the commit. The check knows a few shapes of secret, not all of them.

   Expected: synthetic data only, and no address outside the private ranges.

8. Add a row to `docs/evidence/records/lessons.json` for what the run set taught, with the jobs that show it, then run step 6 again. Add the run set's bar to its milestone's chart, `test-outcomes-N.html` with N the milestone, as in [`test-outcomes-5.html`](../diagrams/test-outcomes-5.html), and export its SVG. A chart holds eight bars at most.

   Expected: the lesson on the [lessons page](../evidence/lessons.md), with a link to each job.

9. Check the pages against the records, as the pipeline does.

   ```bash
   python3 -I validation/evidence/render.py --check
   ```

   Expected: exit 0 and no output.
