# 0005. NetBox target and exercise 1 investigation

Date: 2026-10-24 to
Milestone: 4, NetBox target and exercise 1 investigation

## Summary

Started on 2026-10-24. The decisions are ADRs [0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md) to [0037](../decisions/0037-an-unscoped-copy-of-the-consumers-permission.md). On the platform side, Squid's port for the targets' packages and its two rules are built ([below](#the-targets-package-port)). No target VM exists yet. The [roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation) holds the criteria and the status.

Before the build, five pins moved to their newest stable release: Terraform, `hashicorp/azurerm`, Ruff, Goose, and Argo Workflows. Goose and Argo run on the platform, so both were installed and every check ran after them.

## Pin moves

Date: 2026-10-24. Each release was read from its project's release page that day, and none is a preview.

| Pin | From | To | Where it runs |
| --- | --- | --- | --- |
| Terraform | 1.16.6 | 1.17.0 | Workstation and pipeline |
| `hashicorp/azurerm` | 5.10.0 | 5.11.0 | Workstation and pipeline |
| Ruff | 0.17.1 | 0.17.2 | Pipeline |
| Goose | 1.55.0 | 1.56.0 | Worker |
| Argo Workflows, its executor, and its command line | v4.1.5 | v4.1.6 | Orchestrator and pipeline |

### Terraform and azurerm

Locally, on the workstation. What proves the Terraform archive is HashiCorp's: `SHA256SUMS` verifies against HashiCorp's key, fingerprint `C874 011F 0AB4 0511 0D02 1055 3436 5D94 72D7 468F`, and the archive matches its line. Written before the run.

```bash
gpg --verify terraform_1.17.0_SHA256SUMS.sig terraform_1.17.0_SHA256SUMS
sha256sum -c --ignore-missing terraform_1.17.0_SHA256SUMS
```

| Input | Result |
| --- | --- |
| The release's `SHA256SUMS` | `Good signature from "HashiCorp Security (hashicorp.com/security) <security@hashicorp.com>"`, primary key `C874 011F ... 72D7 468F` |
| The same file with one checksum changed | `BAD signature` |
| The arm64 archive | `OK`. The pipeline pins the amd64 line, `c168cab7...` |

1.17.0's notes list new features, a JSON field in `terraform version`, and Go 1.26.10. Nothing these roots use changed. azurerm 5.11.0 adds resources and fixes one, and none of the 32 resource and data source types the roots use is among them.

The lock files were made again for `linux_amd64` and `linux_arm64` with `terraform init -upgrade` and `terraform providers lock`. The azurerm hashes are the same in all three roots. Then a plan of each root, with the platform identity for the platform root and the operator's sign-in for bootstrap:

```bash
terraform plan -input=false -detailed-exitcode -lock=false
```

Both printed `No changes. Your infrastructure matches the configuration.` and exited 0. A plan reads the live resources, so this is the live system, read only.

### Ruff

Locally, with 0.17.2 from PyPI and the pipeline's two commands. The image is pinned by its index digest, `d69a8c8d...`, read from `ghcr.io`. 0.17.1's index digest equals the old pin, so the new one is the same kind of digest.

| Input | Result |
| --- | --- |
| `ruff check --no-cache worker platform tool-service` | `All checks passed!` |
| `ruff format --no-cache --check worker platform tool-service` | `36 files already formatted` |
| A copy of `worker/` with `x = undefined_name` added to `agent_job.py` | `Found 1 error.`, exit 1 |

0.17.2's one new rule is a preview rule, which the default set does not select.

### Goose

On the workstation, before the pin. What proves the archive is Goose's build: cosign v3.1.4 verifies the release's SLSA provenance with the identity of its release workflow at the tag, and the commit in the provenance is the tag's commit. Written before the run, as for 1.55.0 ([provenance](0003-toolchain-integration.md#provenance-of-llamacpp-and-goose)).

| Input | cosign | Exit |
| --- | --- | --- |
| `goose-aarch64-unknown-linux-musl.tar.gz`, `release.yml@refs/tags/v1.56.0` | `Verified OK`. The source commit is `9949cf92...`, the commit of the tag `v1.56.0` | 0 |
| The same with the identity for `v1.55.0` | `no matching CertificateIdentity found` | 1 |
| The archive with one byte appended | `provided artifact digests do not match digests in statement` | 1 |

The archive matches the release's digest, `a3e86032...`. It holds one file, a static aarch64 binary, SHA-256 `e90f1a59...`, which is `GOOSE_BINARY_SHA256` now. It prints `1.56.0`.

Read in the source, by comparing the two tags:

- **Tool names.** 1.56.0 renames MCP tools whose names a provider would reject. A name made of `[a-zA-Z0-9_-]` is unchanged, so `tools__get_evidence` stays.
- **Skills ([#139](https://github.com/sindredg/ai-security-platform/issues/139)).** The places skills are found, the two bundled skills, and the check on a skill's supporting files are the same as in 1.55.0. The code moved into a new crate.
- **The recipe template and the task prefixes.** The recipe code is byte-identical. The session code changed only to report status to a terminal through OSC 7501. That needs text output and a terminal, and a job has neither: it runs `--output-format json` with stdout on a pipe.
- **Automatic thinking level** is opt-in, and code mode is an extension the recipe does not name.

The job program's tests passed locally: 51, with `/usr/bin/python3 -I -S` on the workstation's Python 3.12.3. The pipeline runs them on the hosts' release.

### Argo

On the workstation, before the pin. What proves each image is Argo's: cosign verifies its digest against the release's public key. Written before the run, as for v4.1.5 (T50).

| Input | Result |
| --- | --- |
| `workflow-controller@sha256:a012a639...` | Verified against the key, exit 0 |
| `argoexec@sha256:28432d91...` | The same |
| `argocli@sha256:acb4c1de...` | The same |
| The controller with a key made for the test | `no matching signatures`, exit 12 |

The key file is byte-identical to v4.1.5's. The release's `namespace-install.yaml` matches its listed digest, `acf23714...`, and differs from v4.1.5's only in the version inside descriptions and in the two image tags. v4.1.6 has five commits after v4.1.5, and none changes `workflow/controller/`, `workflow/signal/`, or the manifests. So the Role, the reason for leaving out `secrets: get`, and the reason for `pods/exec` hold as written in `argo.yaml` and `.trivyignore.yml`. `argo lint --offline` with the v4.1.6 command line passes on the workflow template.

### The install

On the live system, 2026-10-24 13:02 to 13:13 UTC, from `chore/move-pins` with the Goose and Argo pins uncommitted. One script ran the [agent runtime](../runbooks/agent-runtime.md) steps 2 to 5, 7, and 8 and the [workflows](../runbooks/workflows.md) steps 3, 4, 9, and 10, then every check. Each step printed what it expected before it ran.

| Step | Expected | Seen |
| --- | --- | --- |
| One fetch window for both | `ok` for Goose's archive, `47M` staged on the worker, `ok` for the release file and the three images, `closed`, and no denied request | As expected. The close ended 11 tunnels. The denied count read 21: all 21 lines are from the morning's check runs, 06:48 to 07:14 UTC, and none from the window. The count reads the last 60 lines, not the window |
| Goose on the worker | Both pins match, and the job unit starts the new binary | `the archive matches artifacts.tsv`, `the binary matches GOOSE_BINARY_SHA256`, and the unit names `/opt/aisec/goose/goose-1.56.0/goose`. 1.55.0 stays in its own directory |
| Argo on the orchestrator | The definitions established, the controller rolled out on the new digest | `successfully rolled out`, and the new pod on `a012a639...`. The old pod was still terminating when the list was printed |
| The fixture three times | 3 of 3 correct, one tool call each, as with 1.55.0 on 2026-10-19 | 2 of 3. Run 1 asked for `ev-0001`, then made up `ev-0002` to `ev-0006`, which the fixture refused. Runs 2 and 3 were correct with one call. Nothing points at Goose: the model chose the references |
| A round trip through the workflow | `Succeeded`, one tool call, `slot_erased` true | `Succeeded` in 2 minutes. `completed`, `tool_calls` 2 with the same arguments twice, `tool_errors` 0, `slot_erased` true. The answer's last lines were `Status: confirmed` and `Excess: tenancy.contact, circuits.circuit`. The audit has the register, two allowed calls, and the revoke |
| Goose's first request to the model (#139) | `load_skill` and `tools__get_evidence`, and the two bundled skills named, as on 2026-10-20 | As expected. Goose 1.56.0 also writes `advertised_tools` into each assistant message's metadata |
| The worker's disk after the stage is removed | About 5.0 GB used | 8.6 GB. The 5.0 GB is from before the model comparison, whose two other model files are still on the worker |
| Every check | All pass | 286 of 286, 13:08 to 13:13 UTC. `G.1` passed on the new binary, `W.2` and `W.3` on the new controller and executor |

### Not verified

- The first request is Goose's only. A later request with tool results in it was not read.
- No job hit its time limit or was stopped under v4.1.6.
- The fixture's 2 of 3 is one run of three. It says nothing about whether 1.56.0 changes accuracy.

## The targets' package port

Date: 2026-10-24. The platform side of [ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md): Squid's second port on the edge and the two rules to it. The update run that forwards the port to a target comes with the target VMs.

### What changed

| File | Change |
| --- | --- |
| `infra/platform/cloud-init/edge.yaml.tftpl` | `http_port 10.45.0.4:3129 name=target-packages`, an ACL on that port name, and two rules before the fetch window's include: allow the orchestrator `GET` and `HEAD` on port 80 to `azure.archive.ubuntu.com`, then deny everything else on the port |
| `infra/platform/main.tf` | `allow-target-packages-to-edge`: outbound TCP 3129 from `10.40.0.4/32` to the edge subnet, priority 1040 |
| `infra/platform/edge.tf` | `allow-target-packages-from-orchestrator`: inbound TCP 3129 from `10.40.0.4/32`, priority 1030 |
| `validation/platform-checks.sh` | `P.23` to `P.29`, `M.9`, `Z.26`. `P.2` lists both listeners, and `Z.21` the new inbound rule |

The source address is the orchestrator's, not its subnet as on 3128, because the ADR names the address and Squid's ACL holds the same `/32`.

### Before the change

What proves Squid accepts the configuration: the edge's own Squid, 7.2, parses the rendering of the template and exits 0, and a copy with one broken ACL type makes it exit 1. Written before the run. The file went to `squid -k parse -f /dev/stdin` on the edge, which reads and changes nothing.

| Input | Result |
| --- | --- |
| The template rendered with the platform's addresses | `rc=0`, no `ERROR` or `FATAL` line |
| The same with `myportname` changed to `myportnam` | `FATAL: Bungled /dev/stdin line 5`, `rc=1` |

The fail side of each new check, on the live system at 14:18 UTC, before the apply and the install:

| Check | Expected after the change | Seen before |
| --- | --- | --- |
| `P.2` | `10.45.0.4:3128 10.45.0.4:3129` | `10.45.0.4:3128` |
| `P.23` | 200 | `000`: nothing listened on 3129, and no rule allowed it |
| `P.24` to `P.27`, `P.29` | 403 | `000` each |
| `P.28` | `timeout` | `timeout`. Not seen to fail: the worker's rules cannot be loosened read-only. The same probe on 3128 reads `open` |
| `M.9` | `timeout` | `timeout`. Not seen to fail, for the same reason. The same probe on port 22 of the edge reads `open` |
| `Z.21`, `Z.26` | The new rule listed, and named | Not run before the apply. The plan showed neither rule existed. IP flow verify from the orchestrator to port 3129 read `Deny deny-all-outbound` when `Z.23`'s fail side was taken ([milestone 3a worklog](0004-edge-network-and-monitoring.md)) |

`P.28` and `M.9` passed before Squid listened on 3129, so before the change they proved only that no path existed. After the install, Squid listens there (`P.2`), so a timeout is the rules.

### Rollout

On the live system. The plan read `0 to add, 2 to change, 0 to destroy`: one added rule in each of the orchestrator's and the edge's groups, nothing else. Applied at 14:34 UTC with `Resources: 0 added, 2 changed, 0 destroyed`. Right after, from the orchestrator, TCP to `10.45.0.4:3129` read `refused`: the packet now reached the edge, where nothing listened yet. From the worker it still read `timeout`.

A script then ran the [edge runbook](../runbooks/edge-vm.md#the-targets-package-port) steps 15 and 16, 14:37:24 to 14:37:37 UTC. Each step printed what it expected before it ran.

| Step | Expected | Seen |
| --- | --- | --- |
| Render | Two `http_port` lines | As expected. SHA-256 `c9568686...` |
| Parse on the edge | `rc=0` | `rc=0` |
| Install and reload | The installed file's SHA-256 equal to the rendering's, `root 644`, `active` | As expected. The old file is in `/var/backups/squid.conf.20261024T143727Z` |
| Listeners | `10.45.0.4:3128 10.45.0.4:3129` | As expected, after a reload. No restart was needed |
| The port, no window | Mirror 200, other host 403, upload 403, port 8080 403, tunnel 403 | As expected |
| The port, window open | Tunnel on 3128 200, on 3129 403, mirror on 3129 200 | As expected. The window then closed |
| Squid's log | The same requests from `10.40.0.4` | `TCP_MISS/200` for the two mirror requests, `TCP_DENIED/403` for the four refusals and the two refused tunnels, `TCP_TUNNEL/200` for the tunnel on 3128 |

The log does not name the port a request came in on: the `squid` log format has no field for it. The order of the lines and the script's own output tie each line to its port.

### Every check

On the live system, 14:38 to 14:43 UTC, from the branch with the changes uncommitted: `295 passed, 0 failed`. The new and changed checks read as expected: `P.2` both listeners, `P.23` 200, `P.24` to `P.27` and `P.29` 403, `P.28` and `M.9` `timeout`, `Z.21` with `allow-target-packages-from-orchestrator 3129-3129`, and `Z.26` naming `allow-target-packages-to-edge`. `P.19` passed on the new file and `P.22` on the reload. A platform plan after the run printed `No changes` and exited 0.

### Not verified

- The listener on 3129 at first boot of a rebuilt edge. The template has it, and the running edge got it from a copy and a reload.
- A target using the port. No target VM exists, and the update run that forwards it is not written yet.
- `P.27` during a window is shown by the runbook step only, once, at 14:37 UTC. The checks run with no window open.
