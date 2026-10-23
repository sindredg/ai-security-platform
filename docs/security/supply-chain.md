# Supply chain

Which artifacts the platform runs, what pins each one, where the pin is checked before the artifact runs, and which signatures are checked. The versions are in the [version table](../components/README.md#versions). The threats are T06 in the [threat model](threat-model.md#b2-egress-and-downloads) and A4 in the [AI-specific threats](ai-threats.md).

Read from the code and the release pages on 2026-10-23. Each state uses the threat model's [words](threat-model.md#scope-and-method).

## The rule

Milestone 3's [criterion](../roadmap.md#3-toolchain-integration): every image and every input to the model file is pinned by digest and checked on the orchestrator before it runs or is pushed. T06 adds a signature check where upstream signs.

A pin proves that a file is the one first chosen, not that the first choice was safe. A signature or provenance check proves who built the file, not what it does. Both stop a file swapped after the pin. Neither stops a bad release from the publisher itself.

## Images

| Image | Pinned by | Checked before it runs | Signature | Held by | State |
| --- | --- | --- | --- | --- | --- |
| Argo's `workflow-controller` and `argoexec` | Digest, in `platform/argo/argo.yaml` | containerd checks the digest when `platform/argo/fetch.sh` pulls it on the orchestrator | cosign, against the release's public key, on the workstation before the pin | `W.2`, `W.3` | Verified. The signatures verified on 2026-10-19, and a check with another key failed (T50). `W.2` and `W.3` hold the running controller to the pins, and passed in the [last run](../validation/README.md#last-run) |
| Tool service | Digest of the image the pipeline pushed from `main`, in `platform/tool-service/tool-service.yaml` | containerd checks the digest at the pull. The pipeline and `deploy.sh` refuse a manifest image without one | None. The project's pipeline builds it, without provenance | `T.2` | Verified. `T.2` failed while the pod ran the previous digest, and passed after the deploy ([worklog](../worklogs/0003-toolchain-integration.md#checks-before-and-after)) |
| Dispatch | The same, in `platform/argo/workflow-template.yaml` | containerd checks the digest at the pull. The pipeline refuses a manifest image without one | None, as above | `W.9` | Verified. `W.9` failed while the cluster held the template with the previous digest, and passed after it was applied, in the same runs |
| The Python base of both | Digest, in `.github/workflows/checks.yml` and both Dockerfiles. The pipeline fails when they differ | The pipeline, at the build | Not checked | | Built |
| K3s's system images: `local-path-provisioner`, CoreDNS, `metrics-server`, and `pause` | The checksum of the release's airgap archive, in `infra/platform/variables.tf`, and each image's digest, in `infra/platform/k3s-images.txt` ([ADR 0033](../decisions/0033-k3s-system-images-from-the-release-archive.md)) | First boot checks the archive and puts it where K3s imports it at start. containerd pulls none of them: Docker Hub is not on the edge's list | None published | `K.11` | Verified on 2026-10-23: installed on the running orchestrator, and `K.11` passes. It named the changed image for a changed digest, a missing line, and an empty list ([worklog](../worklogs/0003-toolchain-integration.md#installed-k3ss-system-images-from-the-releases-archive)). Until that day they were pulled by tag ([worklog](../worklogs/0003-toolchain-integration.md#k3ss-system-images)). No first boot from the changed template has run |

## Files

| File | Pinned by | Checked before it runs or is pushed | Signature or provenance | Held by | State |
| --- | --- | --- | --- | --- | --- |
| K3s binary, install script, and the archive of its system images | SHA-256 each, in `infra/platform/variables.tf` | The orchestrator's first boot, before any of them runs | None published | `K.11`, for the images | Built |
| Argo's namespace install, for its custom resource definitions | SHA-256, the release's digest of the asset, in `platform/argo/pins.env` | `platform/argo/fetch.sh` on the orchestrator, before `install.sh` applies it | None | | Built |
| llama.cpp binaries | SHA-256, in `worker/model-server/artifacts.tsv` | `fetch.sh` on the orchestrator before the push, and `build-model.sh` on the worker before the build | SLSA provenance, signed through Sigstore, checked with cosign on the workstation | Nothing compares the installed binaries with the pin | Verified for the provenance on 2026-10-23: built by `release-publish.yml` in `ggml-org/llama.cpp`, from the pinned commit. A wrong identity and a changed file failed ([worklog](../worklogs/0003-toolchain-integration.md#provenance-of-llamacpp-and-goose)) |
| The converter's source | The commit, and the SHA-256 of the archive packed from it, in `worker/model-server/pins.env` | The same two scripts | The commit ID is a hash of the content | | Built |
| The converter's Python packages | SHA-256 per file, in `artifacts.tsv` | The same | Not checked | | Built |
| The model's files | SHA-256 per file and the publisher's revision, in `worker/model-server/models/Qwen3.5-4B.tsv` | The same | None published | `S.7` compares the built model file with the build's own checksum | Verified for the built file: `S.7` passed in the [last run](../validation/README.md#last-run). Its fail side was seen on the workstation ([checks](../validation/model-server.md)) |
| Goose | SHA-256 of the archive, the release's digest, and of the binary inside it, in `worker/agent-runtime/` | `fetch.sh` on the orchestrator, and `install-agent.sh` on the worker, which refuses a binary that does not match | SLSA provenance, checked as for llama.cpp | `G.1` | Verified. The provenance on 2026-10-23: built by `release.yml` at `v1.55.0`, with the same fail sides. `G.1` failed on another binary, read on the worker ([checks](../validation/agent-runtime.md#broken-inputs)) |
| The tool service's Python packages | SHA-256 per file, in `tool-service/requirements.txt` | pip, with `--require-hashes`, when the pipeline builds the image | Not checked | Dependabot proposes updates, unproven with hashed files ([#46](https://github.com/sindredg/ai-security-platform/issues/46)) | Built |

## From a vendor's signed channel

These are not pinned by checksum. The vendor's signature on its package index is the check.

| What | Pinned | Check | State |
| --- | --- | --- | --- |
| Ubuntu packages on every VM, Squid among them | Not pinned. Unattended upgrades install security fixes daily | apt checks the archive's signed metadata with the key in the image | Built |
| The mesh VPN agent on the router | Version, held. `U.2` holds it | apt checks Tailscale's signed repository. First boot fetches Tailscale's key over HTTPS, with no fingerprint pinned | Built |
| The Azure Monitor Agent | Minor version, automatic upgrades off | Azure installs and checks it. Nothing on the project's side does | Built |
| The Ubuntu image | Version, in `infra/platform/variables.tf` | Azure. Trusted Launch checks the boot chain with Secure Boot | Built |

## In the pipeline

Every scanner and linter runs as an image pinned by digest. Terraform and gitleaks run from release archives checked against a pinned SHA-256, and the one action is pinned by commit ([pipeline](../components/pipeline.md)). Argo's command line image had its cosign signature checked before its pin. Nothing else in the pipeline is signature-checked.

## SBOM

None is produced. Milestone 8 needs one for the artifact its exercise picks ([roadmap](../roadmap.md#8-exercise-3-vulnerable-image-or-dependency)). Planned.

## Limits

- **Signatures and provenance are checked once, on the workstation, before the pin.** Nothing on the orchestrator checks them again. The checksum carries the result forward, so a new pin needs the check again.
- **The project's own images carry no signature or provenance.** Only `main` pushes to the repository's registry, and the digest in each manifest is copied from the pipeline's summary by hand.
- **llama.cpp's provenance names a build from its `master` branch,** at the pinned commit. The build tag `b11669` is not in the signed identity.
- **No check compares the installed llama.cpp binaries with their pin.** `S.7` covers the model file only.
- **Tailscale's package key is trusted on first use.**
- **The first pin is trusted on sight** (T06).
