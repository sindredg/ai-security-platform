# 0005. NetBox target and exercise 1 investigation

Date: 2026-10-24 to
Milestone: 4, NetBox target and exercise 1 investigation

## Summary

Started on 2026-10-24. The decisions are ADRs [0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md) to [0037](../decisions/0037-an-unscoped-copy-of-the-consumers-permission.md). On the platform side, Squid's port for the targets' packages and its two rules are built ([below](#the-targets-package-port)). The NetBox VM and the lab VM are built, with the checks that read them ([below](#the-target-vms)). The update run is built, and has run once on each target ([below](#the-update-run)). NetBox runs on its VM, with no data yet ([below](#netbox-on-its-vm)). The [roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation) holds the criteria and the status.

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

## The target VMs

Date: 2026-10-24. The two VMs from the targets repository, and their checks on the platform side.

| VM | Address | Subnet | Packages its update run installs |
| --- | --- | --- | --- |
| `vm-aisec-netbox` | `10.50.0.4` | netbox | `podman postgresql-18 valkey-server` ([ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)) |
| `vm-aisec-lab` | `10.50.0.36` | consumer | None |

Both are `Standard_B2as_v2` in Poland Central, zone 3, with secure boot, a vTPM, a 30 GB disk, and no public address. Zones 1 and 2 are restricted for this size in this subscription. The two fill the region's 4 vCPUs. The lab VM has one interface, the consumer viewpoint.

First boot downloads nothing: the targets have no way out. It applies the platform VMs' hardening, takes only a certificate for the administrator, makes the update account, masks apt's timers and unattended upgrades, and points apt at `127.0.0.1:3129`, where an update run forwards Squid's target port ([ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)). The first-boot script and the update command are files in the targets repository's `host/`.

### Before the apply

| What | How | Result |
| --- | --- | --- |
| The packages exist for Ubuntu 26.04 | `apt-cache policy` on the orchestrator, read only, from the same mirror the targets use. Read again at 17:00 UTC | Candidates `podman` `5.7.0+ds2-3build1`, `postgresql-18` `18.6-0ubuntu0.26.04.1`, `valkey-server` `9.0.4-0ubuntu0.2` |
| The sshd block | The block given to the orchestrator's OpenSSH 10.2 as `sshd -T -f /dev/stdin -C user=...`, read only | The update account: forwarding `remote`, listen `127.0.0.1:3129`, open `none`, no terminal, the forced command. The administrator: no forwarding. A copy with a bad port: `rc=255` |
| The update key | A script on the orchestrator, 15:24 UTC | `/etc/aisec/target-update` `root root 700`, the private half `600`, the public half `644`, ED25519, comment `aisec-target-update`. The public half went into the targets root's local variables |

### The applies

On the live system, from the targets repository's branch.

| Time (UTC) | What | Result |
| --- | --- | --- |
| 15:25 | Plan `4 to add`, applied | The two interfaces were created. Both VMs failed with `PlatformImageNotFound` for image `26.04.202610220` |
| 15:27 | Plan with image `26.04.202610210`, `2 to add`, applied | `2 added, 0 changed, 0 destroyed`. Cloud-init finished on both at 15:28:47 |
| After | Targets plan | `No changes`, exit 0 |

`az vm image list` named versions up to `26.04.202610220` in Poland Central. `az vm image show` found `26.04.202610210` and did not find `26.04.202610220`. Hypothesis: the newest versions are listed before they reach the region. The variable's comment in the targets repository now says to pick the version with `image show`.

### First readings

On the live system, about 15:30 UTC, read only.

| What | Result |
| --- | --- |
| Host keys | The ED25519 fingerprint in each VM's serial log equals the one `ssh-keyscan` reads through the router |
| Login through the router with an operator certificate, 15:30 UTC | Accepted by certificate. Each target sees `10.45.0.36`, the router, as the client ([#106](https://github.com/sindredg/ai-security-platform/issues/106)) |
| First boot | The marker exists, no failed unit, the administrator's `authorized_keys` empty, `aisec-update` locked with a root-owned key file, one `sudo` command, the apt units `masked`, apt names the forwarded port, `binutils` removed |
| Ways out, from each VM | The internet, Azure DNS, the edge's port 3129, and the orchestrator's port 22 time out. Name lookups fail. `apt-get update` fails at once |
| The orchestrator to each VM on 22 | `open` |

The administrator's `authorized_keys` exists with no line: cloud-init writes it back empty after first boot removes it, as on the edge and the router. The checks count lines.

### The checks for the targets

`validation/platform-checks.sh` gains a section for each target, and four checks elsewhere:

| Checks | What they read |
| --- | --- |
| `VN.1` to `VN.19`, `VL.1` to `VL.19` | The login and the address the target sees, the update account's sshd settings, key line, key, groups, `sudo` rule, and command, apt's units and proxy, no listener on the forwarded port, no way out, first boot's marker, and no log agent ([targets](../validation/targets.md)) |
| `HN`, `HL` | The [hardening](../validation/host-hardening.md) list, as on the platform VMs |
| `E.15`, `E.16` | The orchestrator reaches both targets on 22, and the update key on it is `root 600` |
| `C.11` | The worker gets no connection to the lab VM. `C.2` now aims at a VM that listens |
| `Z.27`, `Z.28` | The effective rules on each target interface equal its subnet group's configured rules ([#107](https://github.com/sindredg/ai-security-platform/issues/107)) |
| `Z.1` | Reads the target group too |

`VN.9` and `VL.9` compare the update command with a checkout of the targets repository, named by `AISEC_TARGETS`.

What proves each new check can fail: a copy of the script with one broken input per check, run against the live system, and every new check `FAIL`. Written before the run. The copy and its output are kept outside the repository.

| Checks | Broken input |
| --- | --- |
| `.1` | The whole `SSH_CLIENT`, not its first field |
| `.2` | Root's `authorized_keys`, which has a line |
| `.3` | `permittty` in place of `permitopen` |
| `.4`, `.7`, `.8` | The administrator in place of `aisec-update` |
| `.5` | The certificate authority's file in place of the key file |
| `.6`, `E.16` | The orchestrator's host key in place of the update key, and the group in place of the mode |
| `.9` | No `AISEC_TARGETS` |
| `.10` | `ssh.service` in place of `unattended-upgrades.service` |
| `.11` | The platform's proxy line |
| `.12` | Port 22 |
| `.13` to `.17` | The target's own loopback, where sshd and the stub resolver listen |
| `.18` | A marker that does not exist |
| `.19` | `openssh-server` in place of the agent's package |
| `E.15` | Port 80 on the lab VM |
| `C.11` | The worker's own port 22 |
| `Z.1` | A resource group that does not exist |
| `Z.27`, `Z.28` | Each interface against the other target's group |

Result, ending at 16:58 UTC: `318 passed, 53 failed`. The 53 are the 44 new and changed checks, and nine checks that share a changed probe line: `A.5`, `A.7`, `A.13`, `A.16` (root's file), `A.8`, `A.10`, `A.14`, `A.17` (`permittty`), and `O.4` (the package). Each `.6` failure showed two different keys, and `Z.27` printed the rule whose destination differed. `HN` and `HL` were not given a broken input: they run the same code as the other hardening checks, whose fail side is in the [milestone 3a worklog](0004-edge-network-and-monitoring.md#the-fail-side-of-the-edge-checks).

Every check, on the live system, from the branch with the changes uncommitted, ending at 16:51 UTC: `380 passed, 0 failed`.

### Not verified

- The update account has not been logged in to. That is the update run, next.
- No packages are installed. The targets carry the image's state from 2026-10-21 until the first update run, and no check reads their pending security updates yet.
- Nothing from the targets reaches Azure Monitor: no log agent, and no path to the private endpoint. Operator sessions to the targets are an [open item](../security/accepted-risks.md#open-items).
- The first-boot template ran once, on these two VMs. The [network foundation runbook](../runbooks/network-foundation.md)'s target steps are still not run in their current form ([#108](https://github.com/sindredg/ai-security-platform/issues/108)).

## The update run

Date: 2026-10-24. The orchestrator's side of [ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md): a command that opens the session, forwards Squid's target port into the target, and lets the update key's one command run.

### What changed

| File | Change |
| --- | --- |
| `platform/target-update/aisec-target-update-run` | Root's command on the orchestrator: `aisec-target-update-run netbox` or `lab`. SSH with no configuration file, the pinned host key, no agent, and one remote forward from the target's `127.0.0.1:3129` to `10.45.0.4:3129`. A journal line when the run starts and one when it ends, with the target, the exit status, and the target's two result lines |
| `platform/target-update/install-target-update.sh` | Makes the update key if there is none, pins both targets' host keys when given, and installs the command as `root 700` |
| `validation/platform-checks.sh` | `E.17`, `E.18` on the orchestrator. `VN.20`, `VL.20`, `U.14`, and `U.15` on the targets |
| The targets repository's `target.yaml.tftpl` | The Azure mirror named for both archives under `apt:` |

### The targets' apt sources

The first run of the new checks, at 17:30 UTC without the Azure and workstation checks, read `330 passed, 6 failed`. Written before the run: `E.17`, `E.18`, `VN.20`, `VL.20`, `U.14`, and `U.15` fail, the rest pass. All six failed on absence. `U.14` and `U.15` read `no 0 no`: the image's package list from 2026-10-21 shows nothing pending, which is why the check also asks for a refresh after first boot.

`VN.20` and `VL.20` showed a problem that would have stopped every update run: the targets' apt sources named `archive.ubuntu.com` and `security.ubuntu.com`, which Squid's target port refuses. Cloud-init keeps the Azure mirror only if its name resolves, and the targets have no DNS ([troubleshooting 16](../troubleshooting/16-targets-apt-sources-fall-back-without-dns.md)). The target template now names the mirror.

What proves the template change is valid: the target's own cloud-init, 26.04's, accepts the rendered template with `cloud-init schema`, and refuses a copy with `uri` misspelled. Written before the run. Read only, with the rendering on standard input.

| Input | Result |
| --- | --- |
| The template rendered with placeholder values | `Valid schema /dev/stdin` |
| The same with `uri` changed to `urii` | `Invalid user-data /dev/stdin` |

### The rebuild

On the live system, from the targets repository's branch, to prove the template at first boot. The targets held nothing yet.

| Time (UTC) | What | Result |
| --- | --- | --- |
| 17:39 | Plan with `-replace` for both VMs | `2 to add, 0 to change, 2 to destroy`. Only the custom data differs. `26.04.202610210` is still the newest version `image show` finds in Poland Central |
| Ending about 17:45 | Applied | `2 added, 0 changed, 2 destroyed`. Each VM destroyed in 56 s and created in 49 s |
| 17:47 | Host keys | The fingerprint in each serial log equals the one the scan reads through the router. Both are new |
| 17:48 | First boot | Each cloud-init log reads `Apt Mirror info: {'PRIMARY': 'http://azure.archive.ubuntu.com/ubuntu/', 'SECURITY': 'http://azure.archive.ubuntu.com/ubuntu/', ...}`, with no search. The marker exists, no failed unit, and each target sees `10.45.0.36` |

### The first update runs

A script ran the [targets runbook](../runbooks/targets.md#update-run)'s install with both host keys, then steps 10 to 12, 18:03:06 to 18:04:53 UTC. Each step printed what it expected before it ran. A first attempt at 17:51 stopped at the install: the install script was not executable, and nothing on the orchestrator had changed but the copied files. The install that ran took both host keys. The script's path without them was added after the run and tested on the workstation with stubs: it makes a key, two keys are pinned, and a key in another form is refused.

| Step | Expected | Seen |
| --- | --- | --- |
| Install | The existing key's fingerprint, `root 700`, the command's SHA-256 equal to the checkout's, both pins | As expected. The key is the one made at 15:24, `SHA256:uCvSmvHu...` |
| NetBox VM, 18:03:09 to 18:04:33 | Lists and packages from the Azure mirror, `podman`, `postgresql-18`, and `valkey-server` installed, an upgrade, `security_updates_pending=0`, exit 0 | As expected. 45 packages installed, `podman` `5.7.0+ds2-3build1`, `postgresql-18` `18.6-0ubuntu0.26.04.1`, `valkey-server` `9.0.4-0ubuntu0.2`. Then `zlib1g` and `libnss3` upgraded. `reboot_required=no` |
| Lab VM, 18:04:34 to 18:04:46 | The same, with nothing extra | `zlib1g` and `libnss3` upgraded. `security_updates_pending=0`, `reboot_required=no` |
| The orchestrator's journal | A start and an end line per target | As expected, each end with `status=0` |
| Squid's log, from `10.40.0.4` since the first run | `GET` to `azure.archive.ubuntu.com` only, and no refusal | `133 TCP_MISS/200` and `2 TCP_MISS/304`, all `GET` to `azure.archive.ubuntu.com` |
| A listener on 3129 on either target afterwards | None | `0` on each |
| Reboot | Only where asked for | Neither target asked |

Squid's log names the orchestrator for every request, as ADR 0036 says. The journal's start and end lines are what tie each request to a target.

### Every check

On the live system, from the branch with the changes uncommitted, ending at 18:12 UTC: `386 passed, 0 failed`. `E.17`, `E.18`, `VN.20`, `VL.20`, `U.14`, and `U.15` passed after failing at 17:30. Every earlier target check passed on the rebuilt VMs too, the first run of first boot from the template on new VMs after the first build.

### Not verified

- The pending count and the reboot field of `U.14` and `U.15` were not seen to fail on their own. The age part failed before the first run.
- A run that needs a reboot. Neither did.
- A run on a target whose host key changed without a new pin. `StrictHostKeyChecking=yes` should refuse it. Not tried.
- A run whose forward fails, for example a second run on the same target at the same time. `ExitOnForwardFailure=yes` should end it. Not tried.

## NetBox on its VM

Date: 2026-10-24. [ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md), with the TLS key made on the VM ([ADR 0038](../decisions/0038-netboxs-tls-key-made-on-the-netbox-vm.md)). The procedure is the [NetBox runbook](../runbooks/netbox.md).

### What changed

| File | Change |
| --- | --- |
| The targets repository's `netbox/image.env` | The pin: the image index by digest, its linux/amd64 manifest, and that manifest's config, whose digest is the image ID |
| The targets repository's `netbox/netbox.container`, `netbox-worker.container` | Podman Quadlet units for NetBox and its background worker. The image by ID, never pulled, the VM's network, the image's `netbox` account, a read-only root, no capabilities, no new privileges, and the secrets as files |
| The targets repository's `netbox/netbox.env` | The settings that are not secret, Granian's TLS among them |
| The targets repository's `netbox/install-netbox.sh` | Root's script on the NetBox VM: loads the archive and starts nothing unless the image ID is the pin, makes four secrets and the TLS key once, the PostgreSQL role and database, Valkey's password, and installs and starts the units |
| The targets repository's `infra/targets/main.tf` | TCP 8443 into the NetBox VM from `10.40.0.4/32` and the consumer subnet, and out of the consumer subnet to the NetBox VM |
| The targets repository's checks workflow | A `Quadlet units` job: Quadlet's own dry run reads the units, and a copy with an unknown key has to fail it. ShellCheck reads `netbox/` |
| `platform/target-images/fetch-netbox-image.sh` | Root's script on the orchestrator, in a fetch window: pulls the index by digest into containerd's `aisec-targets` namespace, exports linux/amd64, checks the archive against the pin, and removes the image from the namespace |
| `infra/platform/main.tf` | `allow-netbox-to-targets`: TCP 8443 from `10.40.0.4/32` to `10.50.0.4/32` |
| `validation/platform-checks.sh` | `N.1` to `N.11` and `C.12`. `Z.25` names the two new inbound rules |

### Before the change

Read on 2026-10-24, on the workstation, from GitHub and from `ghcr.io` without a token.

| What | Read |
| --- | --- |
| Newest releases | NetBox `v4.7.3`, released on 2026-10-13, and `netbox-docker` `5.1.1`, on 2026-09-10. The pin in ADR 0035 stands |
| The index `v4.7.3-5.1.1` | SHA-256 `1d6e0b5f...`, the digest in ADR 0035. Four entries: linux/amd64 `95426f0f...`, linux/arm64 `d15c0a89...`, and one BuildKit attestation manifest for each, an unsigned SLSA provenance statement |
| The linux/amd64 manifest | Config `sha256:6942b6b0...`, 18 layers, 262,271,880 bytes compressed |
| Granian 2.8.2, the image's server | Its command line reads options from `GRANIAN_` variables, `--ssl-certificate` and `--ssl-keyfile` among them, with TLS 1.3 as the default minimum. The key has to be PKCS#8 |
| Plans | Platform: `0 to add, 1 to change, 0 to destroy`, one rule added, none removed. Targets: `0 to add, 2 to change, 0 to destroy`, three rules added, none removed |

Both applies ran before 19:48 UTC: `0 added, 1 changed` and `0 added, 2 changed`. A plan of each root after them exited `0`.

### The install

From a script that ran the runbook's steps 3 to 12, with each step's expected result printed before it ran. The first run, 19:48:09 to 19:57 UTC:

| Step | Expected | Seen |
| --- | --- | --- |
| The pin on the orchestrator | The checkout's SHA-256 | The same, `6e45828a...` |
| Fetch window | Open | Open for 30 minutes at 19:48:13 |
| Pull and check | The index digest, then the archive with 18 layers and the pinned config | `ok    pulled` with `sha256:1d6e0b5f...`, `ok    archive: 18 layers, config sha256:6942b6b0...`. The archive is 262,312,448 bytes. The `aisec-targets` namespace holds no image afterwards |
| Close | Closed | `open tunnels ended: 4`, then closed at 19:48:49 |
| Squid's log, from `10.40.0.4` during the window | Tunnels to `ghcr.io` and `pkg-containers.githubusercontent.com` only | `6 TCP_TUNNEL/200 CONNECT ghcr.io:443`, `3 TCP_TUNNEL/200 CONNECT pkg-containers.githubusercontent.com:443`, nothing else |
| Copy to the NetBox VM | The same SHA-256 | `d638b782...` on both, after about three minutes through the operator's session |
| Install | The image ID, four secrets, the key, PostgreSQL, Valkey, the units, then `login_page=200` | Everything up to the units as expected, started at 19:52:30. Both containers ran image `6942b6b0...`. Then `login_page=000` after the script's five minutes, and exit 1 |

The script stopped, not NetBox. The journal showed the image's entrypoint still in the first start's migrations, at `trace_paths`. Port 8443 listened at 19:58:27, about six minutes after the start, and Granian logged `Listening at: https://:::8443`. The worker restarted 8 times in those minutes, because it needs the migrated database, and then ran. The script's wait is 30 minutes now, with a line each minute. The unit's `TimeoutStartSec=300` went too, with its comment: systemd counts the unit as started when the container starts, so the setting never covered the migrations.

The second run, from 20:00:02, ran the changed install script and steps 9 to 12:

| Step | Expected | Seen |
| --- | --- | --- |
| Install, a second time | `have` for the image, each secret, and the key. `login_page=200` | As expected. `login_page=200` about a minute after the restart, the same certificate |
| The certificate to the orchestrator | The same fingerprint on both, `root 644` | `42:E9:DA:18:...` on both, `root 644` |
| From the orchestrator | `200` with the pin, `000` in plain HTTP | `200`, `000`. `openssl s_client` with the pin: `TLSv1.3`, `TLS_AES_256_GCM_SHA384` |
| The units' journal | Granian on 8443, no traceback | `Listening at: https://:::8443`, two workers, `GET /login/ HTTP/2 200`. `NRestarts=0` for both |
| The VM's copy of the archive | Removed | Removed. The orchestrator keeps `/var/lib/aisec/target-images/netbox.tar` for a rebuild |

### What the first deployment settled

ADR 0035 left two parts to the first deployment.

- **The check on the target.** ADR 0035 expected `podman load` to drop the registry's digest. With containerd's OCI archive it did not: the load printed `Loaded image: ghcr.io/netbox-community/netbox@sha256:1d6e0b5f...`, and `podman images` lists that digest for the image. The archive's `index.json` names the index by that digest, and holds 21 blobs: the index, the amd64 manifest, its config, and the 18 layers. The VM compares the image ID anyway, which does not depend on what names the archive carries. Not looked into: whether Podman checked the listed digest against the index's bytes.
- **TLS from Granian.** It works with the two variables, and no reverse proxy is needed. No new record beyond ADR 0038.

Read on the NetBox VM after the install: Podman's `secretsdata.json` is `root 600`. `/etc/valkey/aisec-netbox.conf` is `valkey valkey 640`. PostgreSQL holds the `netbox` role's password as `SCRAM-SHA-256`.

### Every check

On the live system, from the branch with the changes uncommitted. The first run ended at 20:09:57 UTC: `396 passed, 2 failed`. Written before it: 398 checks, all pass, with the values of `N.6` and `N.8` reasoned and not yet seen.

- `Z.25` failed for the right reason: its expected value listed only the SSH allows, and the NetBox group now has two more. The claim changed, so the expected value names the two rules now.
- `N.7` failed for a wrong one: it matched `secret` in a value, the path `/run/secrets/tls.key` of `GRANIAN_SSL_KEYFILE`, and no secret was in the environment. It reads the variables' names only now, as its claim says.

After both fixes, ending at 20:19:58 UTC: `398 passed, 0 failed`.

### Each new check fails

A copy of the script with one broken input per new or changed check, run without the Azure and workstation checks on the live system, ending at 20:23:16 UTC: `336 passed, 12 failed`, the 12 below. Written before the run: these 12 fail and nothing else does.

| Check | Broken input | Result |
| --- | --- | --- |
| `N.1` | The tool service's certificate as the pin | `000 000` |
| `N.2` | Another file, `root 600` | `root 600` |
| `C.12` | Squid's port on the edge, which the worker reaches | `open` |
| `N.3` | Port 22, which the router reaches | `open` |
| `N.4` | A unit that does not exist | `active inactive active active` |
| `N.5` | The pin with its last character changed | The two running IDs, not the pin |
| `N.6` | Another field in the read-only flag's place | `999:0 false false` for each |
| `N.7` | `path` added to the pattern, which `PATH` matches | `2` |
| `N.8` | Loopback no longer left out | `22 53 5432 6379 8443` |
| `N.9` | The password given | `PONG` |
| `N.10` | Another certificate on the VM | Another fingerprint |
| `N.11` | Port 8444 | `timeout`. Written before the run: `refused`. The consumer subnet's rules allow only 8443 out, so 8444 never reaches the VM |

`Z.25`'s fail side is its first run above. `N.7`'s path for a failed read, which prints an error in place of a count, was not fed a broken input.

### Not verified

- The `Quadlet units` job in the targets repository's pipeline has not run. Its fail side is inside the job: a unit with an unknown key has to fail the dry run. It is not a required check yet.
- One run of the install from start to end on a new VM. The first run stopped at the wait, and the second ran on the same VM.
- The install script's refusal of an archive that holds another image. `N.5` fails on another ID, but the script's own comparison was only seen to pass ([#188](https://github.com/sindredg/ai-security-platform/issues/188)).
- No capabilities and no new privileges for either container: configured in the units, and no check reads them ([#186](https://github.com/sindredg/ai-security-platform/issues/186)).
- An update run with NetBox running. PostgreSQL and Valkey restart when apt upgrades them, and NetBox's response to that was not seen ([#187](https://github.com/sindredg/ai-security-platform/issues/187)).
- The undo, and a rebuild of the NetBox VM from the archive the orchestrator keeps.
- The consumer's pin. There is no consumer yet.
