# 0051. A NetBox job's schema names each of the job's accounts

Status: Accepted
Date: 2026-10-28

Changes the schema of [0049](0049-a-netbox-jobs-answer-is-a-final-output-checked-against-a-schema.md) and adds a field to the job line of [0030](0030-how-a-job-reaches-the-worker.md). The rest of both stands.

## Context

A NetBox job's recipe carries one schema for every job. Its `verdicts` is a list that needs one item, and its description asks for one per account in the contract ([#221](https://github.com/sindredg/ai-security-platform/issues/221)). Goose accepts an output that leaves an account out, the job program writes no verdict line for it, and the verification gate stops on `no verdict line`. That fails closed, but it is the stop [0049](0049-a-netbox-jobs-answer-is-a-final-output-checked-against-a-schema.md) set out to remove, and the model never hears that an account is missing.

What is fixed already:

- **The trusted side knows the accounts.** The collect command writes the checks' verdicts per account into the config map item the comparison step reads for the job ([0040](0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md), [0041](0041-the-workflow-compares-the-models-verdict-with-the-checks.md)). The dispatch step runs from the same image, with the comparison's reader in it.
- **Goose checks the whole schema.** It validates each call with a JSON Schema library, so a required property, an enumeration, and a refusal of other properties all reach the model as errors (`crates/goose/src/agents/final_output_tool.rs` in 1.56.0). The job program's own checker handles those keywords too.
- **The job program is told the target** since [0049](0049-a-netbox-jobs-answer-is-a-final-output-checked-against-a-schema.md), and refuses a line with fields it does not know.

## Options

| Option | What it changes | What it costs |
| --- | --- | --- |
| Keep one schema and let the gate stop | Nothing | The model is never asked to correct a missing account. The gap stays |
| A list with one entry per account | The schema's list gets a size and a clause per name | Two new keywords in the job program's checker, and an error the model has to map back to a name |
| An object with a property per account | The schema's `verdicts` becomes an object, built for each job from its account names | The names have to reach the worker, so the job line and the dispatch step change |
| The names from the contract document | The job program reads `ev-0001` | The worker, untrusted, would decide which accounts the answer covers |

## Decision

**The dispatch step reads the job's accounts from the checks' verdicts.** It mounts the same optional config map item as the comparison step and takes the account names through the comparison's own reader, so the model is asked for the accounts the comparison will check and no others. A NetBox job with no item, another job's, or one out of shape fails at the dispatch step before the job runs, with the stop the comparison step would have given after it.

**The job line carries the names, sorted, and nothing else from the item.** The checks' verdicts stay on the orchestrator. The job program requires `accounts` for a NetBox job, 1 to 20 names in the comparison's pattern with no repeat, and refuses the field for any other job.

**The schema is built for each job.** `verdicts` is an object with one required property per account, the verdict and its evidence under it, and no other property allowed. A proposal's account is one of the same names. The job program writes one verdict line per property, in the model's order, as before.

## Trade-offs

- **The dispatch step reads a file it did not before.** It takes the names only. A wrong item changes which accounts the model is asked for, and the comparison still checks every account in the same item, so no new trust rests on it (`W.12`).
- **The prompt grows with the accounts.** Goose puts the schema in the tool's description and in the system text, so a case with more accounts makes a longer first prompt. The held-out cases have one or two.
- **A dispatch image before this change cannot run a NetBox job** against a job program with it: the line has no accounts, and the job is refused. The image and the program are installed together.
- **The schema still checks form, not truth.** A verdict under every name can still be wrong. The verification gate is what stops that.
- **Not seen when this was written:** a job on the live system, an output refused for a missing account, and a scored run with the new schema.
