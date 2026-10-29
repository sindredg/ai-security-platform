# Accepted risks and open items

## Accepted risks

These have no control and no gate. They are carried on purpose.

- **T15, T30:** a takeover of the operator's GitHub or Azure account defeats the design.
- **Provider compromise:** Azure, GitHub, and the mesh VPN provider are trusted.
- **Single approver:** nobody checks the operator.
- **T56:** the approval key sits on the operator's machine, beside the GitHub session. The workstation is out of scope, so whoever holds the key and its passphrase approves a delivery.
- **T02:** the router's mesh auth key was single use and expired a day after the router's first boot on 2026-10-17, and its file is gone (`A.4`). A spent copy in custom data and in the platform state enrolls nothing. Check again when a router is rebuilt with a new key.
- **T39:** a flaw in Squid gives the worker or the orchestrator root on the edge, which has the internet on TCP 443 and 80 and no credential for the cluster, the audit log, or the mesh. Nothing short of a real exploit drills it. The containment is in the checks T39 names, and the refusal alert.
- **T23, in part:** the checks' verdicts come from the target's own API and from the collector's records on the host ([0037](../decisions/0037-an-unscoped-copy-of-the-consumers-permission.md)). A comparison with the cloud API and the network, which the threat model planned for milestone 6, is not built: no exercise 1 fact is visible there. Build it with exercise 2, whose change surface is a network rule.
- **T31:** the bootstrap state has one copy off the operator machine, uploaded by hand after each apply. A forgotten upload leaves the copy behind the real thing, and a restore from it has not been run. Losing both costs imports, not resources.
- **No CIS benchmark result for the operating system.** No tool has a CIS profile for Ubuntu 26.04 yet: not ComplianceAsCode 0.1.82, and not the vendor's Ubuntu Security Guide. A Lynis audit stands in. Run the CIS profile when either ships one.
- **Seven advisories in the converter's packages.** None is reachable in how the model build uses them, for the reasons [below](#advisories-in-the-converters-packages).
- **The workstation:** out of scope. A deployment key taken from it is covered by T29.
- **Goose's own `load_skill` tool.** Goose 1.56.0 adds it to every request, and no setting removes it: `crates/goose/src/agents/state_machine_builder.rs` builds the skills operation into every agent, read at tag v1.56.0. It returns one of two texts bundled in the binary, because a job's skill directories are empty, in its unit's private `/tmp`. One of the two tells the model to search the web, which no tool in a job can do, and the worker has no route out. The job program fails a job offered any tool but `load_skill`, the tool service's, and a NetBox job's structured output tool ([#139](https://github.com/sindredg/ai-security-platform/issues/139)). One synthetic job called it on 2026-10-26 and got a bundled skill's text, and no audit record holds that call, only the job's transcript ([#207](https://github.com/sindredg/ai-security-platform/issues/207)). Check again at each Goose pin move: the source, and the tools a job's journal line names.
- **A job's transcript is kept 24 hours with its workflow.** It holds the evidence the agent read: the synthetic fixture, or for NetBox the collect command's documents of facts, with no free text from NetBox ([0040](../decisions/0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)). Root on the orchestrator and the operator's Argo account can read it until Argo deletes the workflow, 24 hours after it ends ([0030](../decisions/0030-how-a-job-reaches-the-worker.md)). The data is synthetic. Check again before a target with real data, or a document with free text, reaches a job.
- **The tool service (an MCP server) uses a pinned self-signed certificate.** The worker trusts a local copy rather than a certificate authority ([ADR 0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md)). If the private key is stolen, the server certificate and the worker's trusted copy both need to be replaced.

Push protection left this list on 2026-10-28: a made-up GitHub token with a valid checksum was refused at the push ([worklog](../worklogs/0007-operational-and-containment-drills.md#push-protection)).

T05 left this list on 2026-10-17. The orchestrator reaches the internet only through Squid on the edge VM, and its 3a criteria are tested ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-edge-vm)). What remains of it, the upload hosts during a just-in-time (JIT) egress window, is T40 in the [threat model](threat-model.md). Trivy's `AZU-0051` is no longer ignored on the orchestrator's security group.

The missing alert for a denied flow from the orchestrator or the worker left this list on 2026-10-21. Traffic analytics began processing the platform network's flow log at 20:43 UTC on 2026-10-20, with no change on the project's side, and `O.17` failed on it as written. The alert's query then matched none of the new rows, a defect the empty table had hidden ([troubleshooting](../troubleshooting/13-the-denied-flow-alert-matches-no-public-address.md)).

## Advisories in the converter's packages

The pipeline's converter dependency scan lists seven advisories against `worker/model-server/converter-requirements.txt`, the rows below. On 2026-10-26 `filelock` and `setuptools` moved to their newest releases, which cleared eight more, CVE-2026-59890 among them ([#211](https://github.com/sindredg/ai-security-platform/issues/211), [worklog](../worklogs/0006-remediation-pull-requests-and-delivery.md#the-start-pass)).

The versions are llama.cpp's own pins for its converter, so the fix for most of them is a version the converter was not written against. Earlier readings are in the [worklogs](../worklogs/0003-toolchain-integration.md#certifi-in-the-converter).

They are accepted because the code each one needs is never called. The converter's source at the pinned commit was searched for every call below:

```bash
grep -rnE 'from_pretrained|save_pretrained|AutoModel|Trainer|torch\.load|torch\.jit|json_format|ParseDict|load_custom_generate' \
  convert_hf_to_gguf.py conversion gguf-py/gguf
```

The only calls into `transformers` are `AutoTokenizer.from_pretrained` and one `AutoConfig.from_pretrained` with `trust_remote_code=False`. Every `torch.load` passes `weights_only=True`. The search ran first at commit `d8123504`, build `b11429`, and last on 2026-10-26 at `620d2225`, build `b11669`, with the same result.

| Advisory | Package | Severity | Needs | Here |
| --- | --- | --- | --- | --- |
| CVE-2026-4372 | `transformers` 4.57.6 | High | `AutoModelForCausalLM.from_pretrained`, then code fetched from the model hub | No `AutoModel` call. The build has no network |
| CVE-2026-5241 | `transformers` | High | A LightGlue model loaded with `AutoModel` | No `AutoModel` call |
| CVE-2026-80047 | `transformers` | High | `load_custom_generate` fetching a remote file. No fixed version exists | Never called. No network |
| CVE-2026-9856 | `transformers` | High | `save_pretrained` on a tokenizer or processor | Never called. The tokenizer is only read |
| CVE-2026-1839 | `transformers` | Medium | The `Trainer` class, with PyTorch below 2.6 | No `Trainer`. PyTorch is 2.11.0 |
| CVE-2026-0994 | `protobuf` 4.25.9 | High | `json_format.ParseDict` on nested input | Never called. The effect would be a failed build |
| CVE-2025-3000 | `torch` 2.11.0 | Low | `torch.jit.script` | Never called |

Some converter classes for other model families load a tokenizer with `trust_remote_code=True`. The files staged from each publisher hold no Python file, so there is nothing for that to run. Granite's repository has one, `granite_thinking_parser.py`, which its list in `models/` leaves out.

Limits:

- **A source search, not a traced run.** It covers the converter's own code. It does not prove that `transformers` never reaches one of these functions internally while it loads a tokenizer.
- **It holds for one commit and the models pinned in `models/`.** A change to `pins.env`, `artifacts.tsv`, or a list in `models/` means running the scan and this search again, in the same pull request. A new model also means reading which converter class and tokenizer path it takes, as for the [model evaluation](../worklogs/0003-toolchain-integration.md#will-the-pinned-converter-build-them).
- **It covers known advisories.** The tokenizer loader still parses the publisher's files, which is the trust in the publisher that [ADR 0015](../decisions/0015-build-the-model-file-on-the-worker.md) already states.

## musl in the pipeline's Trivy image

The Trivy 0.76.1 image that both repositories' pipelines use carries musl 1.2.6-r2, which CVE-2026-107891 affects. Alpine fixed it in 1.2.6-r3. Trivy 0.76.1 is the newest release, and its tag has not been rebuilt, so there is no fixed image to move to. The advisory's details are not public: NVD had no record of it, and CVE.org answered 404.

It is accepted because nothing the pipelines do runs that musl. Read on 2026-10-22 from the image pinned in the checks workflow, for `linux/amd64`:

| What | Read from | Result |
| --- | --- | --- |
| How the image starts | Its configuration | The entry point is `trivy`, with no shell |
| `/usr/local/bin/trivy` | Its ELF header and Go build settings | Static, with no interpreter, built with `CGO_ENABLED=0`. It uses no C library |
| What the pipelines ask of it | The checks workflows | `config` on files in a mounted directory, and `image` through the Docker socket. The one remote Terraform module, in the targets repository, is fetched first by the runner's own `terraform` and `git`, and Trivy reads it from disk |

The same reading did not clear the gitleaks image: its `git` mode starts the image's own `git`, which is linked to musl. Since 2026-10-23 the pipelines run the gitleaks release binary instead, which is static, with the runner's `git` ([#155](https://github.com/sindredg/ai-security-platform/issues/155)).

Limits:

- **Reasoned for the two modes, not traced.** That `config` and `image` start no other program is read from how the pipelines call them, not from a trace of Trivy's code. A Terraform module that Trivy has to fetch itself would start `git`.
- **It holds for this digest.** The musl version, the build settings, and the entry point were read from one image.

Read again when the Trivy pin moves, when a pipeline calls Trivy in a new way, or when the targets repository's step that checks for the fetched module changes.

## Open items

Threats that no decision or gate covers yet. Each needs an answer before the milestone named.

| Item | Threats | Needed before |
| --- | --- | --- |
| Cloud identity for cluster workloads | T36 | A collector that reads from Azure. None does in exercise 1 ([0037](../decisions/0037-an-unscoped-copy-of-the-consumers-permission.md)) |
| Sign-in strength on the operator's accounts cannot be shown by a gate | T15, T30 | Not planned |

Two items left this table on 2026-10-16. A rate limit for requests without a valid token is now a [milestone 3a](../roadmap.md#3a-edge-network-and-monitoring) criterion. The mesh agent's log upload is turned off on the router by [ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md), since 2026-10-17 (`R.5`). One more left on 2026-10-24: how the targets get packages, decided by [ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md). And one on 2026-10-26: how long a job's transcript is kept, now an accepted risk above. One on 2026-10-28: operator sessions to the targets, which the router logs to the workspace (`R.8`, [milestone 6 drill](../worklogs/0007-operational-and-containment-drills.md#operator-sessions-to-the-targets)).
