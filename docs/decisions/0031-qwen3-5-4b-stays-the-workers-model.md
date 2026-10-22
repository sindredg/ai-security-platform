# 0031. Qwen3.5-4B stays the worker's model

Status: Accepted
Date: 2026-10-22

## Context

Qwen3.5-4B was picked on 2026-10-11 without a comparison ([ADR 0015](0015-build-the-model-file-on-the-worker.md)). Dispatch builds on it, so before the first target it was compared with the newest small models that fit the worker: 2 vCPUs, 8 GiB, and a 6 GB memory limit on the server. The candidates, eight cases, and the rule that picks a model were written down on 2026-10-19 and 2026-10-20, before any model ran them ([worklog](../worklogs/0003-toolchain-integration.md#model-comparison)).

Each case is a question about a synthetic finding, answered from evidence that a tool returns, then a verdict held to a JSON schema. Four cases carry an instruction injected into what the tool returns. The rule: a model is out if it does not build, does not stay up under the limit, or gets fewer cases right than Qwen3.5-4B. Of the rest, the most cases right wins. A tie goes to the lower median time of an agent run on the Goose fixture, then to the lower memory peak.

There were two runs on 2026-10-21. The first could not tell a wrong verdict from a model that did not know what the `finding` field holds, because the server never shows the schema to the model. The second run added one message naming the fields, with the cases and the rule unchanged and the change committed before it ran.

## Options

| Model | Cases right, first run | Cases right, second run | Median agent run | Memory peak, second run | Output tokens/s |
| --- | --- | --- | --- | --- | --- |
| Qwen3.5-4B, running | 2 of 16 | 6 of 16 | 26.5 s | 3.29 GiB | 6 |
| Granite 4.2 3B | 0 of 16 | 6 of 16 | 37.5 s | 4.06 GiB | 8 |
| Qwen3.5-2B | 0 of 16 | 0 of 16 | 12.6 s | 1.69 GiB | 12 |

Gemma 4 E2B and Ministral 3 3B were not compared: the pinned converter cannot load their tokenizers ([worklog](../worklogs/0003-toolchain-integration.md#candidates)).

## Decision

Qwen3.5-4B stays, with the pins and the build it runs: llama.cpp `b11669`, plain `Q4_K_M`, the model file `85e5f901...`, and no thinking.

- **The rule decides.** Qwen3.5-2B is out in both runs, with fewer cases right than Qwen3.5-4B. Granite 4.2 3B is out in the first run and ties in the second, and the tie goes to the shorter agent run. Both runs pick the same model.
- **The other two lists stay.** `worker/model-server/models/` keeps Granite 4.2 3B and Qwen3.5-2B, so the comparison can run again when llama.cpp, the converter, or the cases change. Without `AISEC_MODEL`, every script builds and serves Qwen3.5-4B.
- **The design does not change.** It already treats every answer from the worker as untrusted ([A1](../security/ai-threats.md)). The runs show why: every model followed at least three of the four injected instructions.

## Trade-offs

- **The model that stays gets 3 of 8 cases right.** It calls a token whose grants equal its contract confirmed, and follows the injected text in all four injected cases. No candidate did better. A verdict from a model this size is a proposal: the tools establish the facts, and the operator approves ([A3](../security/ai-threats.md)). Raising the score belongs to the first real investigation in milestone 4: [#151](https://github.com/sindredg/ai-security-platform/issues/151) for the verdict, and [#152](https://github.com/sindredg/ai-security-platform/issues/152) for what the evidence tool passes to the model.
- **The tie was broken by time on one fixture.** Three Goose runs per model. Granite 4.2 3B wrote longer answers there, 165 to 200 output tokens against 101 to 159. In the cases themselves it was faster: 45.7 seconds per case against 50.0, and 8 output tokens per second against 6. A rule that broke the tie on the cases' time would have picked Granite.
- **The second run exists because of a result.** Reading the first run's answers found the defect in the measurement. The second run changed only the verdict turn's last message, and both runs pick the same model. A different fix to the same defect might have scored differently.
- **Each score is eight results.** At temperature 0, every case gave the same answer in both runs, so one changed answer moves a score by two. The cases are short and synthetic, and go straight to the model server. A dispatched job goes through Goose's own prompt.
- **No thinking.** The agent runs without it, so the cases did too. Whether thinking changes the verdicts on a real investigation is [#36](https://github.com/sindredg/ai-security-platform/issues/36).
- **Granite's signed weights are not used.** Its publisher signs the weights, which could have replaced trust on first use for the model's inputs ([ADR 0015](0015-build-the-model-file-on-the-worker.md)). The rule did not weigh it, and the signature was not checked.
- **Nothing checks which model the server loads.** The other two model files stay on the worker, each with its own line in `SHA256SUMS`, and `S.7` passes for any of the three.
