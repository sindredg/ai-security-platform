# 0015. Build the model file on the worker, from the publisher's weights

Status: Accepted
Date: 2026-10-11

## Context

llama.cpp loads one file format, GGUF. The starting model is Qwen3.5-4B, which replaced the Qwen3-4B-Instruct-2507 the plan first named. Qwen publishes weights for it and no GGUF. Every quantized file on offer comes from someone else.

[A4](../security/ai-threats.md) rates a poisoned model file as a high threat and answers it with digest pins and a known publisher. A digest pin on a third-party file proves the file did not change after it was pinned. It says nothing about what the third party put in it.

The header of the two most used files was read on 2026-10-11 and compared with Qwen's repository:

| | `bartowski/Qwen_Qwen3.5-4B-GGUF` | `unsloth/Qwen3.5-4B-GGUF` |
| --- | --- | --- |
| `Q4_K_M` size | 3,013,027,808 bytes | 2,740,937,888 bytes |
| Tensors | 441 | 426 |
| Embedded chat template | Byte-identical to Qwen's | Different: the tool-call loop is rewritten and thinking is off by default |
| Tokenizer arrays | Same as the other file | Same as the other file |

So the two files do not agree with each other, one of them changes the text that wraps every prompt, and nothing can show whether the weights in either are Qwen's. llama.cpp has also published advisories for memory corruption in its GGUF parser, from 2024 through March 2026, so a GGUF from a stranger is a hostile input to the server as well.

## Options

| Option | Who has to be trusted | What it costs |
| --- | --- | --- |
| A third-party GGUF, pinned by revision and checksum | Qwen, llama.cpp, and the quantizer | One download. The weights cannot be checked against anything |
| Convert on the orchestrator | Qwen, llama.cpp, and the converter's Python packages, on the trusted machine | PyTorch and 26 other packages run on the machine that holds everything worth stealing |
| Convert on the worker | Qwen, llama.cpp, and the same packages, on the machine that is already assumed turned | 9.3 GB of weights go through the orchestrator to the worker. The build needs about 21 GB of disk there for a few minutes |
| Convert in the repository pipeline and pull the result | Qwen, llama.cpp, the packages, and the hosted runner | The orchestrator would run a file that an outside machine built. A bigger build than a model server needs |

## Decision

The orchestrator downloads Qwen's weights and everything the build needs, and checks each file against a checksum pinned in the repository. The worker converts and quantizes. The procedure is in the [model server runbook](../runbooks/model-server.md).

- **Inputs are pinned, all of them.** `worker/model-server/artifacts.tsv` lists 38 files with their SHA-256: the weights and tokenizer files at one revision of Qwen's repository, the llama.cpp binaries, pip, and 27 Python packages. The converter's source is fetched by commit ID.
- **The orchestrator hashes and never opens.** It does not unpack an archive, import a package, or load a model. [ADR 0009](0009-one-egress-point-on-the-orchestrator-subnet.md) already made it the only machine that downloads.
- **The worker checks again, then builds in a sandbox.** The converter runs in a transient unit with its own account, no network, no view of `/home`, and one writable directory. The account and the directory are deleted afterwards.
- **llama.cpp comes prebuilt.** The binaries are the project's own release build `b11429`, pinned by the checksum the release publishes. Building from source would put a compiler on a machine where the hardening pass removed even the assembler and linker.
- **Quantization is plain `Q4_K_M`.** No calibration data, so nothing else has to be fetched and trusted.
- **The server listens on localhost.** The agent runs on the same machine. Nothing else has a reason to reach the model.

## Trade-offs

- **Qwen and llama.cpp are still trusted.** A backdoor in the published weights, or in the release build, arrives intact with a matching checksum. Worker containment is what stands behind that, as before.
- **The pins are trust on first use.** The checksums were read from the publisher's repository and the package indexes on 2026-10-11. They prove that every later build gets the same bytes, not that those bytes were good that day.
- **The model file itself has no pin from outside.** It is built here, so its checksum is a record, not a check against anyone else's. Whether a second build produces the same checksum has not been tested.
- **The converter's packages deviate from upstream's list in one place.** llama.cpp pins `numpy~=2.2.6`, which has no build for the worker's Python 3.14. The build uses 2.3.5.
- **No calibration costs some quality.** Third-party files use an importance matrix that a plain quantization skips. How much it matters for tool calling is unmeasured.
- **A worker rebuild repeats the build.** About ten minutes, and the orchestrator has to keep 9 GB of inputs or download them again.
- **The release is a prerelease by label.** llama.cpp marks every numbered build that way. Its stable tag `v0.6.0` ships no binaries and points at this build.
- **Any process on the worker can call the model.** There is no key on the local port. The worker runs one job at a time under one design, and a turned worker gains nothing from a model it could already run.
