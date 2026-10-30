# Glossary

The terms these docs use, what each means in this project, and the name it has in the code or in older pages. Decision records, worklogs, troubleshooting entries, and test evidence keep the words of their day, so the third column maps those too.

| Term | What it means here | In code and older pages |
| --- | --- | --- |
| Access specification | What each consumer account needs from NetBox and what NetBox must deny: grants, reads and their records, and denials. It sets the account's least privilege | `netbox/contract.json`, `ev-0001`, "contract" in the task, "consumer contract" |
| Agent loop | Goose's turns: the model reads the conversation and the tool list, calls a tool or replies, and Goose adds the result | |
| Agent runtime | Goose and the job program that runs it on the AI worker | `worker/agent-runtime/` |
| Agent's output | What the agent returns. For a NetBox job, a structured output, from which the job program writes the lines the verification gate reads | The result's `answer` field, "the answer" |
| Assume breach | The design treats the AI worker as compromised from the start, and limits its credentials and network access | |
| Defense in depth | Each step between the agent's output and NetBox checks it again on the trusted side ([table](components/agent-job.md#after-the-output)) | |
| Deterministic checks | Two code checks of an account's access: configured, from its permissions, and observed, from what its token returns | `N.14`, `N.17`, `netbox_access.py`, "the checks" |
| Eval, eval set, eval run | Evaluation of the agent on held-out cases. The eval set is those cases, and an eval run is one pass over them | `collectors/netbox/cases.json`, "scored cases", "scored run" |
| Fail side | A run of a check or drill against a broken input, or while the state it guards against holds, which has to fail before a pass counts | |
| Fail closed | A step that stops on anything it cannot confirm, instead of going on | |
| Ground truth | The deterministic checks' verdicts, which scoring takes as right | |
| Guardrails | The checks around the model that it cannot change: the schema, the verification gate, the policy, the staging test, and the approval | |
| Held-out cases | Variants of the access specification that the task was never tuned on | The case names in `cases.json` |
| Human-in-the-loop approval | The operator's tag, signed with the approval key, on the exact commit. The only approval | `approve/netbox/NAME` tags |
| JIT egress window | Just-in-time egress: an operator command opens code and package hosts on the edge VM for at most 60 minutes | `aisec-fetch-window`, `edge/fetch-hosts`, "fetch window" |
| KV-cache clear | Emptying the model server's slot, so that no job's prompt stays for the next | `slot_erased`, `/slots/0?action=erase`, "slot erase" in llama.cpp |
| Least privilege | An account gets exactly what its access specification grants, and nothing more | The verdict `within` |
| Model Context Protocol (MCP) | The protocol between Goose and the tool service | |
| Model evaluation | A comparison of candidate models on fixed cases | `worker/model-server/measure.py`, "model comparison" |
| Over-privileged, under-privileged, within its spec | The verdicts on an account against its access specification | The values `excess`, `missing`, and `within`, beside `inconclusive` |
| Policy as code | The policy check is a program: `platform/change/policy.py` decides whether a proposal goes on | |
| Prompt injection | Instructions planted in evidence, an advisory, or a tool result, which the model may follow | Threat A1 |
| Remediation proposal | The agent's proposed fix: one permission to remove from one over-privileged account | `Proposal:` lines, "proposal" |
| Staging copy, staging test | A second NetBox on the lab VM, reset from a dump before and after each test. A staging test applies a proposal there and runs both deterministic checks | `rehearse.py`, `aisec-rehearse`, `aisec-rehearsal-reset`, the `rehearsal` subnet, "rehearsal" |
| Structured output | The agent's output in a JSON schema, which Goose checks and the job program checks again | `recipe__final_output`, "final output" |
| System prompt | The instructions every job starts with | `worker/agent-runtime/system.txt`, "system text" |
| Tool service | The platform's MCP server on the orchestrator. It checks each tool call against the job's token and the policy, and logs it | `tool-service/` |
| Verification gate | The workflow step that compares the model's verdicts with the deterministic checks', and fails closed | The `compare` step, "the comparison" |
