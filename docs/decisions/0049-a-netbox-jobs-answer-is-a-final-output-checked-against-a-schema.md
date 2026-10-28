# 0049. A NetBox job's answer is a final output checked against a schema

Status: Accepted
Date: 2026-10-27

The schema names each of the job's accounts, and the job line carries them: [0051](0051-a-netbox-jobs-schema-names-each-account-of-the-job.md).

## Context

The comparison reads one verdict line per account, in a strict form, and stops on anything else ([0041](0041-the-workflow-compares-the-models-verdict-with-the-checks.md)). The task asks for those lines in plain text, and for a proposal line per excess account ([0043](0043-proposals-are-remove-only-and-a-policy-check-decides.md)).

What is fixed already:

- **The model often gives the right verdict in the wrong form.** In milestone 5's scored run, 10 of 18 verdicts were right, against 13 of 18 before the task asked for proposals ([#215](https://github.com/sindredg/ai-security-platform/issues/215)). Five of the eight misses had no verdict line, and at least four of those five gave the right verdict in prose instead, such as a bold line or a list.
- **Goose 1.56.0 can enforce an answer's form.** A recipe with a response schema makes Goose offer the model a tool of its own for the answer, check each call against the schema, hand the errors back, and ask for the call when a turn ends without one. The tool reaches nothing.
- **The held-out cases cannot tune the task** ([0042](0042-held-out-cases-and-the-baseline-without-the-agent.md)). A new wording gets development jobs on the seed's contract, then a new scored run.

## Options

| Option | What it changes | What it costs |
| --- | --- | --- |
| Reword the task | The text the model reads | No guarantee from a small model. The task already asks for plain lines, with examples |
| Read more forms in the comparison | The parser on the trusted side | Each form is a new way to misread prose, chosen from held-out answers |
| A final output, with the worker writing the lines | The answer's form, checked by Goose and again by the job program | One more tool offered. The worker writes the lines, not the model |
| A final output, read by the comparison | The comparison's input | The same, plus a second parser in the comparison and a new dispatch image |

## Decision

**A NetBox job's recipe carries a response schema.** The answer is an analysis, one verdict per account with its evidence, and one proposal per excess account with a permission ID and its evidence. The names and references follow the comparison's patterns.

**The job program writes the lines the comparison reads.** It takes the last final output Goose accepted, checks it against the same schema, and writes the analysis as one line, then a verdict line per account and a proposal line per proposal. Without an accepted output that fits, the answer is the model's last text, as before, and the result says so.

**The comparison does not change.** It reads the same lines, from an answer whose form no longer depends on the model's formatting.

**The dispatch step names the job's target in the job line.** The job program offers the final output only to a NetBox job, and fails any other job that is offered it.

## Trade-offs

- **The model is offered one more tool.** It is Goose's own, takes only the answer, and reaches no service.
- **The answer the comparison reads is written by the worker.** A compromised worker could already write any answer. The transcript keeps the model's call and Goose's response to it.
- **The prompt grows by the schema,** which Goose puts in the tool's description and in the system text, so each job takes longer to start.
- **Prose a model writes outside the final output is lost** from the answer. The transcript keeps it.
- **Not seen when this was written:** a job on the live system, and the scored run with the new task.
