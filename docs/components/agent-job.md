# The agent's job

What the agent reads, what it may call, how it works through a job, and every check its output passes before anything reaches NetBox. The agent is Goose driving Qwen3.5-4B on the AI worker. It reads evidence through one tool, returns structured output, and authorizes nothing.

| | |
| --- | --- |
| State | Built. A NetBox job returns structured output since 2026-10-27 ([evidence](../evidence/2026-10-27-1948-final-output-answers.md)) |
| Runs on | The AI worker, in a sandboxed unit started for each job ([AI worker](ai-worker.md#the-agent-runtime)) |
| System prompt | [`worker/agent-runtime/system.txt`](../../worker/agent-runtime/system.txt), the same for every job |
| Task | [`collectors/netbox/task.txt`](../../collectors/netbox/task.txt) for a NetBox job, passed as the workflow's `task` parameter |
| Program | [`worker/agent-runtime/job/agent_job.py`](../../worker/agent-runtime/job/agent_job.py): checks the job, writes the recipe, runs Goose, and writes the result |
| Decisions | [0030](../decisions/0030-how-a-job-reaches-the-worker.md) the way to the worker, [0041](../decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md) the verification gate, [0043](../decisions/0043-proposals-are-remove-only-and-a-policy-check-decides.md) remediation proposals, [0049](../decisions/0049-a-netbox-jobs-answer-is-a-final-output-checked-against-a-schema.md) structured output |

## What it sees

The system prompt, in full:

```text
You investigate security findings for an infrastructure team. You have no knowledge of the systems involved beyond what tools return. Call a tool to get evidence before you conclude anything. Never guess a fact a tool can establish. Keep answers short. If the task says how the answer ends, end it that way. Otherwise end every answer with two lines. The first is `Status: confirmed`, `Status: refuted`, or `Status: inconclusive`. The second is `Excess:` and the items the evidence shows in excess, separated by commas, or `Excess: none`.
```

The NetBox task names the three documents: `ev-0001` the access specification (the task calls it the contract), `ev-0002` each account's configured permissions, and `ev-0003` what each account's token returned. It defines four verdicts, asks, for each over-privileged (`excess`) account, for the permission whose removal fixes it, and asks for its output through Goose's structured-output tool.

The job program writes these into a recipe for Goose, with one extension: the tool service, over the Model Context Protocol (MCP), with this job's token in a header. For a NetBox job the recipe also carries the output's schema: an analysis of at most 2,000 characters, one verdict per account with its evidence, and one proposal per over-privileged account.

## What it can call

| Tool | What it does | Who sees the call |
| --- | --- | --- |
| `get_evidence` | Returns one of this job's documents by reference, with only the fields its schema names | The [tool service](../security/tool-service.md), which checks the token and logs every call |
| `load_skill` | Goose's own, offered on every request. No setting removes it, an [accepted risk](../security/accepted-risks.md) | Goose only. The transcript keeps a call, and no audit line does ([#207](https://github.com/sindredg/ai-security-platform/issues/207)) |
| `recipe__final_output` | Goose's own, for a recipe with a schema. Takes the output and checks it against the schema | Goose only. It reaches no service |

The job program reads the tool list of every request Goose logged, and fails a job offered any other tool. No other extension is configured, so the agent has no shell tool and no file tool.

## The agent loop

Goose works in turns. Each turn sends the model the system prompt, the task, the conversation so far, and the tool list, and the model replies with text or a tool call. Goose runs the call and adds the result to the conversation.

A NetBox job ends when Goose accepts a structured output. A call that does not fit the schema gets its validation errors back, and a turn that ends without one gets a reminder to call it. These are the only retries: nothing from after the job reaches the model.

The job stops at its turn limit or its time limit, both set per workflow: 8 turns and 1200 seconds for the evaluation (eval) jobs. The model server holds 8,192 tokens of context, and thinking is off ([#36](https://github.com/sindredg/ai-security-platform/issues/36)).

## One job

Job `nb-10271948-p1` on 2026-10-27, on the seed's access specification after the fix ([its page](../evidence/2026-10-27-1948-final-output-answers.md#nb-10271948-p1)):

| Time (UTC) | The model's call | What came back |
| --- | --- | --- |
| 19:54:34 | `get_evidence`, `ev-0001` | The access specification, 1,483 bytes |
| 19:56:33 | `get_evidence`, `ev-0002` | The configured permissions, 838 bytes |
| 19:57:37 | `get_evidence`, `ev-0003` | What each token returned, 1,666 bytes |
| Not logged | `recipe__final_output` | Accepted: an analysis, and `within` for both accounts |

The first call came almost five minutes into the job, after the model had read the system prompt, the task, and the schema. The next two came two minutes and one minute later, and the structured output about four minutes after the last. The job ran 707 seconds and sent 17,758 prompt tokens over its requests, and the model wrote 1,237.

## After the output

The job program checks the structured output against the schema again, and writes the analysis as one line, a `Verdict:` line per account, and a `Proposal:` line per proposal. The worker is untrusted, so these checks give the output its form, not trust. The trusted side checks again at every step, so no single check carries the trust (defense in depth):

| Step | Runs on | Refuses | Decided in |
| --- | --- | --- | --- |
| The job program | The worker, untrusted | Structured output outside the schema, a job offered another tool, and output it would have to cut | [0049](../decisions/0049-a-netbox-jobs-answer-is-a-final-output-checked-against-a-schema.md) |
| The dispatch step | The orchestrator, in the workflow | Output over 8 KiB, or with `{{`, a control character Argo's quoting breaks, or a character above U+FFFF | [0041](../decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md), T55 |
| The verification gate | The orchestrator, in the workflow's comparison step | A verdict that is not both deterministic checks' verdict, and a missing or unreadable line. Either stops the workflow | [0041](../decisions/0041-the-workflow-compares-the-models-verdict-with-the-checks.md) |
| `propose-netbox-fix` | The orchestrator host, as root, on the operator's request | A workflow from another entrypoint, a stop, unread proposal lines, and more than one proposal per account | [0043](../decisions/0043-proposals-are-remove-only-and-a-policy-check-decides.md), [0048](../decisions/0048-the-workflows-steps-are-inline-so-no-workflow-runs-one-alone.md) |
| Its policy | The same | Any action but remove, a permission the deterministic checks do not call `excess`, one held through a group, and a removal that leaves the account short | [0043](../decisions/0043-proposals-are-remove-only-and-a-policy-check-decides.md) |
| The staging test | The staging copy on the lab VM, reset before and after | A change after which either check calls an account in the access specification anything but `within` | [0044](../decisions/0044-the-rehearsal-copy-is-a-second-netbox-on-the-lab-vm.md) |
| Publishing | The operator's machine | Any text from the model's output: the pull request is built from checked fields, one users line per change | [0045](../decisions/0045-the-operator-publishes-a-checked-proposal.md) |
| The merge | GitHub | A seed change whose head carries no signed approval | [0050](../decisions/0050-a-guarded-change-merges-only-with-an-approval-on-its-head.md) |
| Delivery | The orchestrator host, as root | Another key's tag, a used or day-old tag, a change beyond removing users, and drift from `main` | [0046](../decisions/0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md), [0047](../decisions/0047-a-delivery-token-for-each-delivery.md) |

No step runs code or text the model wrote. The proposal is an account name and a permission ID, and trusted code turns it into the change.

## Validation

The job program's suite runs in the pipeline's "Dispatch tests", with a whole NetBox job through a fake Goose. `G.1` and `G.8` check that the worker runs the binary and the program in the checkout ([agent runtime checks](../validation/agent-runtime.md)). Each live job is in the [test evidence](../evidence/README.md).

## Limits

- **A small model on two vCPUs.** A NetBox job takes 10 to 12 minutes. This size proves the path, not how good an investigation can be.
- **The model follows planted text.** Every model tried followed injected instructions ([A1](../security/ai-threats.md)). Nothing it says is trusted before the deterministic checks agree.
- **The schema checks form, not truth.** Structured output that fits can still be wrong. The verification gate is what stops that.
- **No second try.** A refused proposal or a failed staging test goes to the operator, never back to the model. A retry would let the model, or whoever steers it through the evidence, search for a change that passes.
- **The context is small.** 8,192 tokens hold three documents of under 2 KB each and a job's turns. A target with more evidence needs smaller documents, not a longer prompt.

## Official documentation

- [Goose](https://github.com/aaif-goose/goose)
- [Goose recipe reference](https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/recipes/recipe-reference.md)
- [MCP transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [llama.cpp's server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)
