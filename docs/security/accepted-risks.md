# Accepted risks and open items

## Accepted risks

These have no control and no gate. They are carried on purpose.

- **T05:** a compromised orchestrator can send anything anywhere on port 443, and in cleartext on port 80. [ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) denies egress to pods, which will narrow this to root on the host once it is built. Closing port 80 was tried and costs more than it removes. See [troubleshooting 03](../troubleshooting/03-proxy-cannot-fetch-upstream-over-tls.md).
- **T15, T30:** a takeover of the operator's GitHub or Azure account defeats the design.
- **Provider compromise:** Azure, GitHub, and the mesh VPN provider are trusted.
- **Single approver:** nobody checks the operator.
- **T31:** the bootstrap state has one copy off the operator machine, uploaded by hand after each apply. A forgotten upload leaves the copy behind the real thing, and a restore from it has not been run. Losing both costs imports, not resources.
- **No CIS benchmark result for the operating system.** No tool has a CIS profile for Ubuntu 26.04 yet: not ComplianceAsCode 0.1.82, and not the vendor's Ubuntu Security Guide. A Lynis audit stands in. Run the CIS profile when either ships one.
- **Push protection is not tested.** Secret scanning with push protection is read as enabled on the repository. No secret was pushed to see it refused, because a real secret must not go to a public repository and a fake one proves little. The secret scan in the pipeline has been seen to fire once, on a false positive.
- **The orchestrator has not been rebuilt from its current template.** It was changed by hand to match cloud-init. The worker was rebuilt on 2026-10-11 and passed every [validation check](../validation/README.md), so the worker template is proven and the orchestrator's is not. An orchestrator rebuild takes a new mesh VPN key, a signed node, and K3s from nothing, and was not run. The first real one is the test.
- **Eight advisories in the converter's packages.** None is reachable in how the model build uses them. The reason for each is [below](#advisories-in-the-converters-packages).
- **The workstation:** out of scope. A deployment key taken from it is covered by T29.

## Advisories in the converter's packages

The pipeline's dependency scan lists eight advisories against `worker/model-server/converter-requirements.txt`. Read on 2026-10-12 with Trivy 0.75.0. The versions are llama.cpp's own pins for its converter, so the fix for most of them is a version the converter was not written against.

They are accepted because the code each one needs is never called. The converter's source at the pinned commit was searched for every call below:

```bash
grep -rnE 'from_pretrained|save_pretrained|AutoModel|Trainer|torch\.load|torch\.jit|json_format|ParseDict|load_custom_generate' \
  convert_hf_to_gguf.py conversion gguf-py/gguf
```

The only calls into `transformers` are `AutoTokenizer.from_pretrained` and one `AutoConfig.from_pretrained` with `trust_remote_code=False`. Every `torch.load` passes `weights_only=True`.

| Advisory | Package | Severity | Needs | Here |
| --- | --- | --- | --- | --- |
| CVE-2026-4372 | `transformers` 4.57.6 | High | `AutoModelForCausalLM.from_pretrained`, then code fetched from the model hub | No `AutoModel` call. The build has no network |
| CVE-2026-5241 | `transformers` | High | A LightGlue model loaded with `AutoModel` | No `AutoModel` call |
| CVE-2026-80047 | `transformers` | High | `load_custom_generate` fetching a remote file. No fixed version exists | Never called. No network |
| CVE-2026-9856 | `transformers` | High | `save_pretrained` on a tokenizer or processor | Never called. The tokenizer is only read |
| CVE-2026-1839 | `transformers` | Medium | The `Trainer` class, with PyTorch below 2.6 | No `Trainer`. PyTorch is 2.11.0 |
| CVE-2026-0994 | `protobuf` 4.25.9 | High | `json_format.ParseDict` on nested input | Never called. The effect would be a failed build |
| CVE-2026-59890 | `setuptools` 81.0.0 | Medium | Building a source distribution on macOS | Nothing is built. Wheels only, on Linux |
| CVE-2025-3000 | `torch` 2.11.0 | Low | `torch.jit.script` | Never called |

Some converter classes for other model families load a tokenizer with `trust_remote_code=True`. The nine files staged from the publisher hold no Python file, so there is nothing for that to run.

Limits:

- **A source search, not a traced run.** It covers the converter's own code. It does not prove that `transformers` never reaches one of these functions internally while it loads a tokenizer.
- **It holds for one commit and one model.** A change to `pins.env` or `artifacts.tsv` means running the scan and this search again, in the same pull request.
- **It covers known advisories.** The tokenizer loader still parses the publisher's files, which is the trust in the publisher that [ADR 0015](../decisions/0015-build-the-model-file-on-the-worker.md) already states.

## Open items

Threats that no decision or gate covers yet. Each needs an answer before the milestone named.

| Item | Threats | Needed before |
| --- | --- | --- |
| Cloud identity for cluster workloads | T36 | Milestone 4 |
| Operator sessions to targets in the audit log | T04 | Milestone 4 |
| Log upload from the mesh agent to its vendor. On by default, [seen on the orchestrator](../components/mesh-vpn.md#limits) | No entry yet | Milestone 4 |
| What the broker allows into a pull request | A5 | Milestone 5 |
| Repository app permissions | T12 | Milestone 5 |
| Sign-in strength on the operator's accounts cannot be shown by a gate | T15, T30 | Not planned |
