# 0004. Edge network and monitoring

Date: 2026-10-16, in progress
Milestone: 3a, edge network and monitoring

## Summary

The milestone is built in slices. The first, orchestrator hardening, is on the system: pods reach the host only on the API server and kubelet ports, and every namespace refuses a privileged pod. The tool service limits requests without a valid token. The second is on the system too: the administrator account on both VMs takes only a certificate that expires within 12 hours, and the feed key logs in to an account of its own on the worker. The check that every commit in a pull request is signed by the operator's key is required, and on GitHub it blocks a pull request with a commit GitHub signed. The target network is in Poland Central, defined in its own repository. The mesh VPN agent runs on a router VM of its own, and the orchestrator is off the mesh. Squid runs on an edge VM, the orchestrator reaches the internet only through it, and only Squid resolves public names for the platform. The target network has its own peering with the edge network and takes SSH from the router. The audit lines, the worker's journal, and the edge's and the router's logs reach a Log Analytics workspace over Private Link, and every alert rule but one fired once on purpose. Traffic analytics does not process the platform network's flow log, an [accepted gap](../security/accepted-risks.md). The daily log volume, the cap set from it, and the agent's footprint were measured over one day, to 2026-10-19 10:00 UTC. Every criterion now has a result.

| Criterion | Result |
| --- | --- |
| The orchestrator reaches the internet only through the edge proxy, and only the hosts on its list | **Tested** on the live system: `E.12` times out on `1.1.1.1:443` and read `open` before the change, `Z.22` names `deny-to-internet`, and the edge refuses another host (`P.14`) and a tunnel with no window open (`P.15`), with `TCP_DENIED` lines in its log. In a window, the listed hosts answer ([the edge VM](#the-edge-vm)) |
| Only the edge resolves public names | **Tested** on the live system: Azure DNS gives the orchestrator no answer over TCP (`E.13`, `open` before the change) and over UDP (`E.14`), and gives the edge one ([fail side](#the-fail-side-of-each-new-check-3)) |
| The orchestrator is not on the mesh VPN | **Tested** on the live system: `A.11` reads `0 0` after the agent was removed, and read `1 1` before ([the router](#the-router)) |
| The operator reaches the orchestrator, the worker, the edge, and the targets through the router | **Tested** for the orchestrator, the worker, and the edge: the checks log in to their private addresses over the router's routes, and both VMs see `10.45.0.36` as the client ([the router](#the-router)). **Configured, not tested** for the targets: both halves of the edge and target peering are `Connected` (`Z.24`) and each target group allows SSH from the router subnet (`Z.25`), but no target VM exists to log in to ([the edge and target peering](#the-edge-and-target-peering)) |
| The mesh agent runs only on the router, with its own updates and its log upload off | **Tested** on the live system: `A.11` on the orchestrator, `U.6` and `R.5` on the router, and `Z.17` shows no inbound allow on the router ([the router](#the-router)). `R.5`'s fail side was seen on the orchestrator, `U.6`'s on 2026-10-16 |
| A check fails when the mesh agent is behind the current stable release | **Tested** with `U.7`: passes on the live router at 1.104.1, as on the orchestrator before it, and fails locally on an older version and on no answer from the package site ([fail side](#the-fail-side-of-each-new-check)) |
| The router cannot open a connection to an operator device | **Tested** for the policy: the console refused a policy with a grant from `tag:aisec-router` to `autogroup:member`, with `test(s) failed for user: tag:aisec-router` ([the policy tests](#the-policy-tests)). **Configured, not tested** for a connection: operator devices run `shields-up`, a device setting, and no check opens a connection from the router to a device that listens ([limits](#limits-2)) |
| The Kubernetes API is not reachable over the mesh VPN | **Tested** on the live system: `M.2` times out after the final policy, and was `open` at 08:50 the same day. The API answers through `ssh -L` to the orchestrator ([the router](#the-router)) |
| Operator SSH logins use certificates that expire within a day | **Tested** on the live system: a login with a 12-hour certificate works on both VMs, and the plain key, an expired certificate, one from another address, and one for another principal are refused, each with its reason in sshd's log ([slice (b)](#rollout-1)). `HO.17` to `HO.20` and `HW.17` to `HW.20` pass |
| A pod reaches the host only on the ports the host rule lists, from its first packet | **Tested** on the live system: a new pod reached SSH before the change and timed out after it, while 6443 and 10250 stayed open, and `E.8` passes ([rollout](#rollout)). The rule loads before K3s, so it holds from the first packet. That ordering is read from the unit, not observed on a boot |
| Every namespace rejects a privileged pod, whether or not it has a pod security label | **Tested** on the live system: `K.9` failed on `default`, `kube-node-lease`, `kube-public`, and `kube-system` before the change and passes after it ([rollout](#rollout)) |
| Requests to the tool service without a valid token are rate-limited | **Tested** on the live system: 33 requests without a token from the worker got 30 × 401 and 3 × 429, with 31 audit lines, one of them for the limit ([the rate limit](#on-the-live-system)) |
| The audit lines, the worker's journal, and the edge's and the router's logs reach a log store that no VM can delete from | **Tested** on the live system on 2026-10-17: rows from all three agents, two audit rows equal to the file's lines, and no role for any VM identity (`O.1` to `O.13`). The orchestrator's only path is the private endpoint ([monitoring](#monitoring)) |
| Alerts for a stopped agent, an audit gap, a missed pull, a refused request, and a security group or role change | **Tested** on the live system on 2026-10-18: each fired once on purpose, `heartbeat-missing`, `audit-sequence`, `journal-missing`, `squid-refused-orchestrator`, `security-groups`, `security-rules`, and `role-assignments`, with nine other rules ([the drills](#the-drills)). `daily-cap` fired on 2026-10-19 ([the drill](#the-drill)). `denied-flow-to-internet` cannot fire while the platform's flow log is not processed |
| Flow logs are recorded for the platform subnets | **Tested** for the records on the live system on 2026-10-18: the platform flow log's blobs hold the drill's denied connections from the orchestrator and the worker. **Accepted gap** for the alert: traffic analytics does not process them, so no alert reads them ([the platform flow log](#the-platform-flow-log), [accepted risks](../security/accepted-risks.md)) |
| The target network is in Poland Central, in its own repository. An unsigned commit fails a required check | **Tested** for the targets on the live system: `Z.14` reads `polandcentral`, after it read `denmarkeast` before the move, and the target root is in [its own repository](https://github.com/sindredg/ai-security-platform-test) ([the move](#the-targets-in-poland-central)). **Tested** for the signature check on GitHub: a pull request with a commit GitHub signed is blocked, also next to a passing job of the same name, and an unsigned push is refused ([fail side](#the-fail-side-on-github)) |
| Log volume per day is measured, and a daily cap is set from it | **Tested** on the live system on 2026-10-19: 67.06 MB of billable rows from 10:00 to 10:00 UTC in `Usage`, and a cap of 0.21 GB, three times that. A cap of 0.023 GB first stopped ingestion and fired `daily-cap`. Raising it brought ingestion back 44 minutes later, after nine more stops, and the workspace has no rows from about 14:15 to 15:10 UTC ([the measured day](#the-measured-day-and-the-daily-cap), [troubleshooting 10](../troubleshooting/10-raising-the-daily-cap-leaves-ingestion-flapping.md)) |
| The orchestrator's memory and CPU use with the log agent are measured | **Tested** on the live system on 2026-10-19: the agent's six units held 290 MiB and used 0.42 % of one core, from their systemd counters across the day. The edge and the router are in [the footprint](#footprint-1) |

## Slice (a): orchestrator hardening

Changes that touch only the orchestrator, the tool service, and the pipeline. Nothing in Azure changed.

### What changed

| Change | Where |
| --- | --- |
| An `input` chain in the host rule: pods reach the host on TCP 6443 and 10250, and replies to connections the host started. Everything else from `10.42.0.0/16` to the host is counted and dropped ([ADR 0023](../decisions/0023-the-host-rule-limits-what-pods-reach-on-the-host.md)) | `infra/platform/cloud-init/orchestrator.yaml.tftpl`, `E.8` |
| The kubelet's anonymous setting is checked | `K.8` |
| An admission configuration for the API server: `restricted` for every namespace without a label, no exemption. `kube-system` enforces `baseline` by its own label ([#70](https://github.com/sindredg/ai-security-platform/issues/70)) | The template, `K.9`, `K.10` |
| A rate limit in the tool service for requests without a valid token | `tool-service/aisec_tools/gate.py`, `policies/tool-service.json` |
| A check that the mesh agent is the current stable release | `U.7` |
| Terraform 1.16.6, azurerm 5.10.0, Checkov 3.3.29, Trivy 0.76.0, and Ruff 0.17.1 | `versions.tf` and lock files in each root, the checks workflow, the [version table](../components/README.md#versions) |

Why `kube-system` gets `baseline` and not an exemption: the K3s hardening guide exempts `kube-system`, which leaves one namespace that admits a privileged pod, the case the criterion names. A server-side dry run of the label on 2026-10-16 showed that all three system pods pass `baseline` and none passes `restricted`. The cost: `local-path-provisioner` makes a helper pod with a host path for each volume claim, and `baseline` refuses it. No claim exists. A K3s release that adds a system pod needing more than `baseline` is refused too, and `K.10` shows it as a deployment short of ready.

### Rollout

Run on 2026-10-16 at about 20:15 UTC on the live orchestrator, from commit `7212a42`, through scripts with the same contents as the [runbook](../runbooks/orchestrator-hardening.md).

Expected, written before the run: SSH from a new pod opens before the change and times out after it, the API server and the kubelet open in both runs, the privileged dry run is created before and forbidden after, and the system deployments come back.

| Step | Result |
| --- | --- |
| Probe from a new pod in `default`, before | `10.40.0.4:22 open  10.42.0.1:22 open  10.40.0.4:6443 open  10.40.0.4:10250 open` |
| Load the new table | Both chains listed, the `input` chain with `tcp dport { 6443, 10250 } accept` |
| Probe after | `10.40.0.4:22 timeout  10.42.0.1:22 timeout  10.40.0.4:6443 open  10.40.0.4:10250 open` |
| Drop counter of the `input` chain | `counter packets 10 bytes 600 drop` |
| Privileged pod in `default`, dry run, before | `pod/priv-dry created (server dry run)` |
| Admission file, argument, label, restart of K3s and the three system deployments | The API server's start line has `--admission-control-config-file=/var/lib/rancher/k3s/server/psa.yaml`. All three deployments `Available` |
| Privileged pod in `default`, dry run, after | `Forbidden: violates PodSecurity "restricted:latest": privileged ...` |
| A restricted pod in `default` | Runs, same probe result as after |
| Every check | 143 of 143 at 20:18 UTC |

The probe ran in `default`, not in `orchestration` as ADR 0023 names. `orchestration` denies all egress by policy, so a probe there shows kube-router's refusal and nothing about the host rule. `default` has no policy, and only the host rule decides. A probe in `orchestration` within a pod's first seconds, before kube-router writes its chain, was not run.

The restart of the system deployments printed a `would violate PodSecurity "restricted:latest"` warning for each. The label sets `enforce` only, so `warn` and `audit` in `kube-system` stay at the cluster default. The warnings refuse nothing.

### The fail side of each new check

Written before each run: the value that proves the claim, and an input that has to fail.

| Check | Pass | Fail seen |
| --- | --- | --- |
| `E.8` | Live after the rollout | Live before it: the chain was absent, empty answer against the expected rules |
| `K.8` | Live: `false Webhook` from the kubelet's `configz` endpoint | Locally, on the live answer with one field changed: anonymous `true`, authorization `AlwaysAllow`, and an empty answer. Each differs from the expected value |
| `K.9` | Live after the rollout: `none` | Live before it: `default kube-node-lease kube-public kube-system` |
| `K.10` | Live: `0` | Locally, on fabricated lines: a deployment with no ready replica gives `1`, no deployment gives `no deployments` |
| `U.7` | Live: 1.104.1 against 1.104.1 | Locally: an installed 1.102.0, an empty installed version, and a URL that answers with an error each fail |

`K.8` reads the kubelet's running configuration, not the file ADR 0023 names. A later file in the kubelet's configuration folder, or a flag, would override the file, and only the running configuration shows that.

### The rate limit

Requests to the tool listener that are refused before a token is accepted count against one limit per minute: no token, a malformed, unknown, revoked, or expired token, or another path. The limit is `untrusted_per_minute` in the policy file, set to 30. Past it, the gate answers 429 and writes no audit line, except one line for the first request over the limit. A valid token is never counted or limited.

What it protects is the audit file. A flood of refused requests used to write one line each, and a full file stops the record ([audit log](../security/audit-log.md#limits)).

The server is at 298 lines of its limit of 300 ([ADR 0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md)). A helper for the gate's refusal line, and one dictionary literal, freed the lines for it.

| Test | Result |
| --- | --- |
| The suite, locally on Python 3.12 with the hashed requirements | 169 passed |
| The limiter turned off (`_over_limit` returns `False`) | 4 failed |
| The minute never resets | 1 failed |
| Ruff 0.17.1 on `worker`, `platform`, and `tool-service` | Clean |

### On the live system

The image is built and pushed only from `main`. The pipeline pushed `tool-service@sha256:28985261c3bf82a347f601e60a51582d26062822329aea817d1ab096ccbded68` from `b3cf4d9`, the same digest in the push job's log and in the registry. The manifest moved to it, and the tool service was deployed again with `deploy.sh` on 2026-10-16, through the steps of the [tool service runbook](../runbooks/tool-service.md). The policy file reaches the pod as a ConfigMap from the same checkout, so code and limit arrived together.

Expected, written before the run: 30 × 401 and 3 × 429 for 33 requests within one minute, and 31 audit lines from the new process, one of them for the limit.

| Step | Result |
| --- | --- |
| Deploy | The new pod runs the digest above |
| 33 requests without a token from the worker, to `/mcp` with the pinned certificate | 30 × 401, 3 × 429 |
| Audit lines of the new process | 31: 30 × `no token, or a malformed one`, 1 × `rate limit reached, no line until the next minute` |
| Every check, more than a minute later | 143 of 143 at 20:39 UTC. `T.2` runs the new digest, `L.6` finds no line missing |

The probes of the pod are TCP, so they do not reach the gate and do not count.

### Version moves

Read from the official sources on 2026-10-16. The Terraform checksum is from the release's `SHA256SUMS`, whose signature checked against HashiCorp's key `C874 011F 0AB4 0511 0D02 1055 3436 5D94 72D7 468F`. Each image digest is the multi-platform index of the release tag, the same kind as the pins it replaces.

| Tool | From | To |
| --- | --- | --- |
| Terraform | 1.16.5 | 1.16.6 |
| `hashicorp/azurerm` | 5.9.0 | 5.10.0, lock files with hashes for `linux_amd64` and `linux_arm64` |
| Checkov | 3.3.27 | 3.3.29 |
| Trivy | 0.75.0 | 0.76.0 ([#56](https://github.com/sindredg/ai-security-platform/issues/56)) |
| Ruff | 0.17.0 | 0.17.1 |

`terraform validate` passes for all three roots with Terraform 1.16.6 and the read-only lock files, run locally on a copy of the tracked files. After merge, `terraform init -upgrade` and `terraform plan -lock=false -detailed-exitcode` ran in `bootstrap`, `platform`, and `targets` against the live state: `No changes` and exit 0 in each. The lock files did not change.

The pipeline passed with every new version on the pull request. Each Trivy step, read from the job logs of the last `main` run with 0.75.0 and the pull request's run with 0.76.0:

| Step | 0.75.0 | 0.76.0 |
| --- | --- | --- |
| Configuration: Terraform, manifests, Dockerfile | No finding in any file. Six suppressed findings on the state storage accounts | The same, in another order |
| Dependency scan | 8 advisories on the converter's packages, report only. None on the tool service's | The same 8 advisory IDs |
| Image scan | 0 in the Alpine packages and in each of 55 Python packages | The same |

### Limits of slice (a)

- First boot from the template with these changes has not run. The running orchestrator got them by hand, through the runbook's steps.
- The `input` chain cannot tell one pod from another. Every pod still reaches the API server and the kubelet, and both rely on authentication.
- `K.9` covers the namespaces that exist when it runs. The default level is what holds a namespace created later.
- The rate limit is shared by every caller and counts nothing per caller. How many requests were refused past the limit in a minute is not recorded.

## Slice (b): SSH certificates and the feed account

Changes to the SSH daemon on both VMs and a new account on the worker. Nothing in Azure changed.

### What changed

| Change | Where |
| --- | --- |
| The administrator account takes only a certificate from the operator's certificate authority, for the principal `aisec-operator`, checked against a revocation list. A plain key is refused ([ADR 0022](../decisions/0022-short-lived-ssh-certificates-for-the-operator.md)) | Both cloud-init templates, `operator_user_ca_public_key`, `HO.17` to `HO.20`, `HW.17` to `HW.20` |
| On the orchestrator, the administrator account may forward to `127.0.0.1:6443` and nowhere else. Every other account, and the worker, forwards nothing | The orchestrator's template, `A.8` to `A.10` |
| First boot removes the key Azure writes to the administrator's `authorized_keys`. sshd ignores the file for that account, so a line there is a change to look at | Both templates, `A.5`, `A.7` |
| The feed key logs in to `aisec-feed` on the worker, which has no sudo, a home owned by root, and a forced command that unpacks staged files into one directory or prints their size ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)) | `worker/feed/`, the worker's template, `E.4`, `E.9` to `E.11` |
| The scripts and the pin lists reach the worker from the operator's checkout. The model build refuses a staged file that no pin names. The converter's source archive, which `fetch.sh` packs on the orchestrator and nothing checked on the worker, gets a SHA-256 pin in `pins.env`, checked on both sides | `worker/*/push.sh`, `build-model.sh`, the [model server](../runbooks/model-server.md) and [agent runtime](../runbooks/agent-runtime.md) runbooks |

Why the feed key moved: on 2026-10-16 it was a plain line in the worker administrator's `authorized_keys`, and that account has `NOPASSWD: ALL` in sudo. Root on the orchestrator was root on the worker. ADR 0022's `AuthorizedKeysFile none` would also have cut the feed off.

Until the router exists, certificates name `source-address=100.64.0.0/10,10.40.0.4/32`. Routed logins reach the worker from the orchestrator's address ([ADR 0026](../decisions/0026-the-feed-key-gets-its-own-account-on-the-worker.md)).

### Tested before the rollout

Locally, with stubs:

| Test | Result |
| --- | --- |
| The feed command with eight requests that are not exactly `receive` or `size` and a component name: empty, `id`, `receive model-server; id`, `receive ../x`, a trailing space, a double space, a capital letter, a second line | Each refused with exit status 2 |
| The feed command with an archive holding an absolute path, a `..` path, and a symbolic link to a directory outside followed by a file through it | `tar` stripped or refused each one. Nothing was written outside the stage directory |
| The build's check of the staged files, run on its own against a stage with an extra file, a symbolic link, a changed file, and a missing file | Each stopped the check with exit status 1. An empty directory passes |
| The same check with a pinned converter archive, a changed one, and none | Passes, then exit status 1 twice |
| The file list of the live stage on the orchestrator, 39 files, against the pins | Nothing extra. A review of this change found that the first version of the check named only `artifacts.tsv`, and would have stopped every build on `converter-src.tar` |
| `git archive` of the pinned commit, on the workstation with git 2.43, against the live archive packed with git 2.53 | The same SHA-256, `cd546e25...` |
| `terraform validate` and `terraform fmt -check` in `infra/platform` with Terraform 1.16.6, and both templates rendered and parsed as YAML | Valid. The rendered drop-in has the `Match` block last |
| The signing commands, with a throwaway authority without a passphrase | Four certificates with the expected key ID, validity, principal, and options |

Read on the live VMs, without a change: sshd 10.2 accepts `TrustedUserCAKeys`, `RevokedKeys`, `AuthorizedPrincipalsFile`, `AuthorizedKeysFile`, `AllowTcpForwarding`, and `PermitOpen` inside `Match User`, read from a configuration on standard input. A `Match` block in an included file ends with that file: OpenSSH 10.2's `servconf.c` restores the match state after each `Include`.

### The fail side of each new check

Written before the run: every new check except `A.9` and `A.10` fails on the VMs as they were, 15 failures in all, and 129 passes from the 144 checks that run without Azure.

| Check | Pass | Fail seen |
| --- | --- | --- |
| `HO.17` to `HO.20`, `HW.17` to `HW.20` | Live after the rollout | Live before it: the default key files and `none` for the rest, no authority, no principal file, no revocation list. `.18` also fails without `AISEC_USER_CA` |
| `A.5`, `A.7` | Live after: `0` | Live before: `1` and `2` |
| `A.8` | Live after: `local 127.0.0.1:6443` | Live before: `no any` |
| `A.9`, `A.10` | Live before and after | On the live VMs with a configuration on standard input that allows the forward: `yes`, and `local 127.0.0.1:6443` |
| `E.4` | Live after: `2` | Live before: `255`, no such account |
| `E.9` to `E.11` | Live after | Live before: no key file, no account, no command |

The run before the rollout gave 129 passed and 15 failed, the 15 written down.

### Rollout

Run on 2026-10-16 between 21:24 and 21:32 UTC on both live VMs, from commit `53c921c`, with a script that runs the [runbook's](../runbooks/ssh-certificates.md) steps and stops at the first result that differs from the one written before it. The worker went first.

| Step | Result |
| --- | --- |
| Feed account installed with the orchestrator's feed key | The key line `from="10.40.0.4",restrict,command="/usr/local/sbin/aisec-feed-receive"`, root's, `644`. The account in no other group, no sudo rule, its home root's |
| Feed key from the orchestrator: `id`, an empty archive, `size` | Exit 2, exit 0, `4.0K /home/aisec-feed/agent-runtime/stage` |
| Feed line removed from the worker administrator's file, then the old login | `1` line left, the operator key. The old login refused, exit 255 |
| Files written, `sshd -t`, a 15-minute revert timer, reload | `syntax-ok` and the timer `active`, on each VM |
| Login with the certificate on a new connection | On each VM: `Accepted publickey for aisec ... ED25519-CERT ... ID aisec-operator-2026-10-16 (serial 1792185839) CA ED25519 SHA256:3e5U...` |
| The plain key, and the expired, wrong-source, and wrong-principal certificates | Exit 255 for each, on each VM. sshd logged `Certificate invalid: expired`, `not from a permitted source address`, and `Certificate does not contain an authorized principal` |
| `sshd -T` for another account, and globally, before and after | No difference on either VM |
| `-W 127.0.0.1:22`, and on the orchestrator `-W 127.0.0.1:6443` | `administratively prohibited` for 22 on each VM. The forward to 6443 opened |
| Timer stopped, the ignored key file and the backup removed | Timer `inactive`, no line in the administrator's `authorized_keys` |
| Every check without Azure | 144 of 144 |
| Every check, the Azure ones included, at 21:44 UTC | 157 of 157 |

The first run stopped at the worker's step 8. After the four refused logins, sshd's per-source penalty dropped every connection from `10.40.0.4` for 17 seconds, and the step's `sshd -T` got no answer. Every routed login reaches the worker from that address. [Troubleshooting 05](../troubleshooting/05-failed-logins-block-every-routed-session.md) has the detail. The worker's step 8 was then done read-only: the settings before were rebuilt from the kept drop-in and the other files sshd reads, given to `sshd -T` on standard input. On the orchestrator, which still had its old settings, the same rebuild gave output identical to the real `sshd -T`. On the worker, the rebuilt settings before and the real ones after are identical for another account and globally. The run then resumed at the worker's step 9, inside the revert timer's 15 minutes. The script waits for the penalty now, about 25 seconds on the orchestrator.

The orchestrator's log has the valid certificate refused before its reload at 21:28:44: the old settings did not trust the authority, so `ssh` offered the certificate, it was refused, and the plain key was accepted on the same connection. After the reload the certificate is accepted.

### Limits of slice (b)

- First boot from the templates with these changes has not run. The running VMs got them through the runbook's steps.
- The forward to 6443 opened, and no `kubectl` command ran through it. The Kubernetes API is still reachable over the mesh VPN until the router slice.
- No certificate was revoked, and the authority was not replaced. Steps 14 and 15 of the runbook have not run.
- No staged file has gone through the feed account yet. The model server and agent runtime runbooks' changed steps have not run.
- The orchestrator's address stays in every certificate until the router slice. A certificate copied to the orchestrator works on the worker from there.
- `operator_user_ca_public_key` has to be in the local `terraform.tfvars` before the next plan.

## Slice (c): signed commits

A check that every commit in a pull request is signed by the operator's key ([ADR 0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)). Nothing in Azure changed. The repository settings were changed by hand, below.

### What changed

| Change | Where |
| --- | --- |
| The public half of the operator's signing key, as the only allowed signer, with the principal `sindredg` | `.github/allowed_signers` |
| A script that runs `git verify-commit` on every commit in a range against that file, with the minimum trust level `fully`, and fails on an empty range, a commit missing from the clone, or a file with no key line | `.github/scripts/check-signatures.sh` |
| A workflow on `pull_request_target` with one job, "Commit signatures". It checks out `main`, fetches the pull request's head by hash, and runs the script from `main` | `.github/workflows/signatures.yml` |
| ShellCheck covers `.github/scripts/` | `.github/workflows/checks.yml` |

ADR 0024 put the job in `checks.yml`. It went into a workflow of its own because a `pull_request` job runs the pull request's own copy of the workflow: a pull request made with a stolen token could replace the check and pass it. The [pipeline page](../components/pipeline.md#the-signature-check) has the design. The cost is that this pull request is not judged by the check it adds.

The minimum trust level: Git 2.43 gives a good signature by a key the file does not name the trust level `undefined` and fails it even without the setting (test 4 below). The setting keeps it failing if a Git release scores it differently.

### Tested locally

Run on 2026-10-17 on the workstation, Git 2.43.0 and OpenSSH 9.6p1. Written before the run: the operator's commits pass, and the commits on `main` (squash merges, signed by GitHub), a commit signed with another key, an unsigned commit, an empty signers file, a signers file with another key, a hash not in the clone, and an empty range each make the script exit with a non-zero status.

| Test | Result |
| --- | --- |
| The 12 commits of pull request 88, the operator's | `ok` for each, exit 0 |
| The last three commits on `main`, squash merges signed by GitHub | `FAILED` for each, `%G?` = `E` (no public key), exit 1 |
| In a scratch repository: one commit signed with the operator's key | `ok`, exit 0 |
| The same: one commit signed with a throwaway SSH key | `FAILED`, `%G?` = `U`, exit 1. Plain `git verify-commit` without the trust setting and with an empty home directory: exit 1, `No principal matched` |
| The same: one unsigned commit | `FAILED`, `%G?` = `N`, exit 1 |
| A range with the good commit, then the other-key and the unsigned one | `ok`, `FAILED`, `FAILED`, exit 1 |
| An empty allowed signers file | Exit 1 at the key line check |
| An allowed signers file that names only the throwaway key, against the operator's commit | `FAILED`, exit 1 |
| A head hash not in the clone | `Invalid revision range`, exit 128 |
| A range with no commits | `No commits in ...`, exit 1 |

The workflow's steps, by hand: a fresh clone of the public repository over HTTPS with no credential and an empty home directory, `git fetch --no-tags origin <head of pull request 88>`, then the script with `HEAD` as the base. `ok` for all 12 commits, exit 0. The script and the signers file were copied into that clone, because `main` does not have them yet.

The key in `.github/allowed_signers` has the same SHA-256 fingerprint as the workstation's signing key, and its key text matches the signing key registered on the GitHub account (`gh api users/sindredg/ssh_signing_keys`).

ShellCheck 0.11 passes on the script, and yamllint (relaxed) on the workflow.

### Repository settings

Read from the GitHub API on 2026-10-17, before any change: one ruleset, `protect-main`, without the signature rule and without "Commit signatures" among its required checks. Merge commits, squash merges, and rebase merges were all allowed.

The operator then changed them in the web interface. Read again at 06:43 UTC, the [pipeline page](../components/pipeline.md#repository-settings) has the result: "Commit signatures" is required, every required check names GitHub Actions as its source, `main` takes squash merges only, and a second ruleset requires signed commits on every branch. Rebase merges were turned off in the repository settings at 06:46 UTC, after the first read, so squash is the only merge method anywhere.

### On GitHub

The first run of "Commit signatures" was on pull request 90, run `39008978522`, on 2026-10-17. Expected: one line, `ok`, for the pull request's one commit. Result: `ok      ae4836e...`, conclusion `success`. This shows the job runs from `main` on `pull_request_target`, fetches the head without a credential, and passes a commit signed by the operator's key. It does not show the fail side.

### The fail side on GitHub

Run on 2026-10-17 between 06:59 and 07:35 UTC, against `main` at `3fb614a`, with the operator's `gh` token. Written before the run, with what counts as a pass:

1. A pull request with one commit made through the API, which GitHub signs. Expected: "Commit signatures" fails, and the pull request is blocked. The second ruleset lets the commit in, because its signature is verified.
2. An unsigned commit pushed to a new branch. Expected: the push is refused, and the branch does not exist afterwards.
3. A pull request that adds a workflow with a job named "Commit signatures" that always passes. Expected: not known. Both runs come from GitHub Actions. A pass is the pull request staying blocked. If it can merge, the check can be faked, and that is a design fault, not an accepted gap.

The API commits were first made with the REST contents endpoint. The second ruleset refused both with HTTP 409, `Commits must have verified signatures`: GitHub does not sign a commit made that way with a user's token. The expectation was wrong on that point. The GraphQL mutation `createCommitOnBranch` makes a commit GitHub signs (`wasSignedByGitHub: true`, state `VALID`), and the ruleset accepted it. That is the path the check exists for, and the one the tests below use. ADR 0024 named a commit made in the web interface. GitHub signs both with its own key, which the check reads the same way: `E`, no public key.

| Test | Result |
| --- | --- |
| 1. Pull request 91, one commit `14aa820` made with `createCommitOnBranch` | "Commit signatures" failed, run `39011940429`: `FAILED 14aa820... E`. The other ten required checks passed. Once marked ready for review: `mergeStateStatus` `BLOCKED`, `viewerCanMergeAsAdmin` false |
| 2. Unsigned commit `5d20b30` (`%G?` = `N`) pushed to a new branch | `push declined due to repository rule violations`, `Commits must have verified signatures`. `GET branches/...`: 404 |
| 3. Pull request 92, one commit `a32fc88` with `createCommitOnBranch` that adds `.github/workflows/spoof.yml` | Two runs named "Commit signatures", both from app 15368: the real one failed, run `39011941975`, and the added one passed, run `39011942272`. The real one finished last. `BLOCKED` |
| 3, again, with the added job's pass last | Pull request reopened. The added job was re-run alone and finished at 07:08:17, after the real run's failure at 07:07:07. Still `BLOCKED`, `viewerCanMergeAsAdmin` false |
| 4. Pull request 94, one commit `51f3f7f` with `createCommitOnBranch` that makes `signatures.yml` run `true` and `check-signatures.sh` exit 0. Expected: the default branch's copy runs and fails, `BLOCKED` | One "Commit signatures" run, run `39013143955`, from the default branch's script: `FAILED 51f3f7f... E`. The edited job did not run. `BLOCKED` |

What proves the block is the check's: the ruleset on `main` asks for no approving review, the other ten required checks passed on each pull request, and every commit carries a verified signature. One setting of the ruleset, `require_extra_approval_for_unattributed_changes`, is on and not in GitHub's public documentation. The commits made with `createCommitOnBranch` have no GitHub user as committer, so the setting could have been a second reason. Pull request 91 was reopened to read it while open: `reviewDecision` was `null`, and the pull request page listed one failing check, "Commit signatures", and no review or approval item. The failing check is the one rule these pull requests break.

Pull requests 91, 92, and 94 were closed without merging and their branches deleted. `GET branches/...` returns 404 for each.

### Limits of slice (c)

- Not tried on GitHub: a pull request from a fork. GitHub does not let an account fork its own repository ([#95](https://github.com/sindredg/ai-security-platform/issues/95)).
- The settings were set in the web interface. The [runbook](../runbooks/repository-settings.md) writes the same steps down and was checked against the settings as read, not run again from the start.

## The targets in Poland Central

The target root moved to its own repository, [`sindredg/ai-security-platform-test`](https://github.com/sindredg/ai-security-platform-test), and the target network moved to Poland Central ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md), [ADR 0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)). Run on 2026-10-17 between 07:50 and 08:45 UTC. The repository was created as `ai-security-targets` and renamed after the run, the same day. The commands below ran against the old name, and GitHub redirects it.

### What changed

| Change | Where |
| --- | --- |
| The target root, as it was at platform commit `3d2044d`, with a `location` variable set to `polandcentral` and the shared module as a Git source pinned to that commit | `infra/targets/` in the targets repository, [pull request 1](https://github.com/sindredg/ai-security-platform-test/pull/1) |
| The signature check, a copy of this repository's, with the same allowed signer | The targets repository's `.github/`, on `main` before pull request 1 |
| A pipeline with Terraform format and validate, Checkov, Trivy, the secret scan, and ShellCheck, at this repository's pins | The targets repository's `.github/workflows/checks.yml` |
| The target root removed, and the validation loop and Dependabot without it | `infra/targets/`, `.github/workflows/checks.yml`, `.github/dependabot.yml` |
| `Z.11` builds its test interface in the region of the network, not of the group. `Z.14` and `Z.15` are new | `validation/platform-checks.sh` |

The resource group and the state account stay in Denmark East, where the bootstrap root made them. Nothing in the bootstrap root changed: it has no policy that limits regions.

### The plan for the move

Written before the plan: the network, four subnets, four security groups, four associations, and the target half of the peering are replaced.

`terraform plan` from the targets repository, as the target identity: `9 to add, 0 to change, 9 to destroy`. The network and the security groups were replaced, with `location = "denmarkeast" -> "polandcentral" # forces replacement`, and the associations with them. The subnets and the peering were not in the plan. They refer to the network by name, and the name does not change. Applied, the plan would have deleted the subnets with the old network and kept them in state. The plan was not applied. The move was made as a destroy and a fresh apply instead, and the [runbook](../runbooks/network-foundation.md#rebuild-the-target-network) says why.

### The new checks, before and after

Written before the run: `Z.14` reads the network's region and fails on `denmarkeast`. `Z.15` reads both halves of the peering, passes while they are connected, and fails once the target network is gone.

| When (UTC) | `Z.14` input | `Z.15` input | Result |
| --- | --- | --- | --- |
| 07:52, before the move | `denmarkeast` | `Connected Connected` | `Z.14` would fail, `Z.15` passes |
| 08:27, after the destroy | Network not found | `Disconnected` and no target half | Both would fail |
| 08:43, after the rebuild | `polandcentral` | `Connected Connected` | Both pass |

The first two rows are the queries the checks run, made by hand with `az`. The third is the full run below.

`Z.11` used to build its test interface in the group's region. With the group in Denmark East and the network in Poland Central, that template has a second fault. Validated by hand at 08:44 with both regions, Azure reported `RequestDisallowedByPolicy` for each: it evaluates the policy first. The old check would have kept passing. The change keeps it from resting on that order.

### The applies

Each was planned and read before it was applied, from a saved plan.

| Step | Root | Plan | Result |
| --- | --- | --- | --- |
| 1 | Targets, destroy | 14 to destroy | `0 added, 0 changed, 14 destroyed` |
| 2 | Targets | 14 to add, every `location` `polandcentral` | 13 created. The peering failed: `RemotePeeringIsDisconnected` |
| 3 | Platform, `-replace` on the peering | 1 to add, 1 to destroy | `1 added, 0 changed, 1 destroyed`. Platform half `Initiated` |
| 4 | Targets | 1 to add, the peering | `1 added, 0 changed, 0 destroyed` |

Step 2 failed because the platform half had turned `Disconnected` when the old network was deleted, and the rebuilt network keeps its ID, so a plain platform plan showed no change. [Troubleshooting 06](../troubleshooting/06-rebuilt-network-leaves-peering-disconnected.md) has the cause.

At 08:42, `terraform plan -detailed-exitcode` exited `0` for the platform, target, and bootstrap roots.

### Checks

`validation/platform-checks.sh` from this pull request's branch, at 08:43 before the commits and at 08:50 from commit `081eab2`: `159 passed, 0 failed` both times. That is the 157 of the last run plus `Z.14` and `Z.15`. `C.2` and `C.3` still time out against the rebuilt subnets, and `Z.11` passes with the test interface in Poland Central.

### The targets repository's settings

Set on 2026-10-17 through the API with steps 4 to 7 of the [repository settings runbook](../runbooks/repository-settings.md), the first run of those steps as written. Squash merges only, secret scanning and push protection on, and two rulesets. Read back at 08:05 UTC:

- `protect-main` on `~DEFAULT_BRANCH`: `deletion`, `non_fast_forward`, `required_signatures`, `pull_request`, `required_status_checks`, no bypass. Six required checks, each from app `15368`: Terraform format and validate, Checkov, Trivy, Secret scan, ShellCheck, Commit signatures.
- `signed-commits` on `~ALL`: `required_signatures` only, no bypass.

Steps 8 to 11, between 08:05 and 08:17 UTC:

| Test | Result |
| --- | --- |
| Pull request 2, one commit made with `createCommitOnBranch` (`wasSignedByGitHub: true`) | "Commit signatures" failed: `FAILED fe71970... E`. `blocked` |
| An unsigned commit (`%G?` = `N`) pushed to a new branch | `push declined due to repository rule violations`, `Commits must have verified signatures`. The branch returns 404 |
| Pull request 3, a commit that adds a job named "Commit signatures" that passes | The real check failed, the added one passed. Re-run alone, the added one finished last at 08:16:02. Still `blocked` |

Both pull requests were closed without merging and their branches deleted.

### The scanners and the module

Written before the run: with a security group rule that allows SSH from any source, Checkov and Trivy each fail, naming the rule. If either passes, it does not read the rules the root passes to the module.

The first pipeline run passed, and proved nothing. Checkov could not write the module into the read-only checkout, logged `Failed to download module`, and passed on two checks of the data source. Both jobs now scan a copy with the module fetched, and a step fails the job when the module is missing. Checkov then ran 5 checks.

A test commit, `d13de59`, set the SSH rule's source to `"*"` on all four subnets. Checkov: `Passed checks: 5, Failed checks: 0`. Trivy: 0 misconfigurations. Both passed. The module builds `security_rule` from a `for` expression, and neither scanner evaluates it. The commit was reverted in the next one. The platform repository uses the same module the same way, so the same holds there ([#96](https://github.com/sindredg/ai-security-platform/issues/96)). The rules are tested on the live system by `Z.4`, `Z.5`, and the `Z` flow checks, after an apply.

### Limits

- The scanners in both repositories do not judge security group rules ([#96](https://github.com/sindredg/ai-security-platform/issues/96)).
- The runbook steps that now use `$TARGETS` were rewritten and run only as the rebuild procedure. A build from scratch from two repositories has not been run.
- The signature script is a copy. A change to one has to be made in the other.


## The security group rules in the scanners

[#96](https://github.com/sindredg/ai-security-platform/issues/96) found that neither scanner judged the rules the network module builds. The module now builds them in a `dynamic "security_rule"` block instead of assigning a list made by a `for` expression. The rules stay inline on the security group, so a rule added by hand still shows up as drift.

### Tested locally

Written before the run: with the worker's `allow-ssh-from-orchestrator` rule opened to `"*"`, both scanners pass on the old module, and both fail on the new one. If either still passes, the change does not fix it for that scanner.

Checkov 3.3.29 from PyPI and Trivy 0.76.0 (the arm64 release archive, checksum matched), the versions the pipeline pins. Each ran on a `git archive` copy of `infra/`, so ignored local files were not scanned. The commands were the pipeline's: `checkov --directory infra --framework terraform --skip-download --quiet --compact` and `trivy config --skip-check-update --exit-code 1 infra`. Trivy ran with an empty `--cache-dir`, so it used the checks built into the binary, as the pipeline's image does. A first round used a check bundle cached on the workstation since 2026-10-11. That bundle lacks `AZU-0051`, and its Trivy results did not match the pipeline.

| Module | Input | Checkov | Trivy |
| --- | --- | --- | --- |
| `for` expression | As on `main` | `Passed checks: 30, Failed checks: 0` | Exit 0 |
| `for` expression | Worker SSH rule from `"*"` | `Passed checks: 30, Failed checks: 0` | Exit 0 |
| `dynamic` block, no suppression | As on `main` | `Passed checks: 34, Failed checks: 0` | Exit 1, `AZU-0051` on the orchestrator's group |
| `dynamic` block, with the suppression | As on `main` | `Passed checks: 34, Failed checks: 0` | Exit 0 |
| `dynamic` block, with the suppression | Worker SSH rule from `"*"` | `Passed checks: 34, Failed checks: 0` | Exit 1, `AZU-0047` and `AZU-0050` |
| `dynamic` block, with the suppression | Worker `deny-to-internet` changed to Allow | `Passed checks: 34, Failed checks: 0` | Exit 1, `AZU-0051` on the worker's group |

Trivy now judges the rules. Checkov does not. The four extra Checkov checks are `CKV_AZURE_9`, `CKV_AZURE_10`, `CKV_AZURE_77`, and `CKV_AZURE_160` on each security group, and they pass on the open rule. Small configurations, one shape each, showed why: Checkov resolves a dynamic block's `for_each` only when it is a literal list or locals of the same module. With `each.value`, a local indexed by `each.key`, a module variable, or separate rule resources over a flattened map, it passes the open rule. Trivy failed every shape. The module receives its rules as a variable, so no shape tried lets Checkov see them ([#99](https://github.com/sindredg/ai-security-platform/issues/99)).

The target root, scanned with its module source pointed at the changed module: Trivy exit 0, Checkov `Passed checks: 7, Failed checks: 0`. With its SSH rule opened to `"*"`, Trivy failed with `AZU-0047` and `AZU-0050` on each of the four target subnets.

### The suppression

Trivy's `AZU-0051` flags a rule that allows egress to every address. On the orchestrator that is true and intended: its HTTPS and HTTP rules to the internet are the platform's egress point, carried as accepted risk T05 until the edge VM takes them over ([0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)). The module ignores `AZU-0051` for the security group whose subnet key is `orchestrator`, with the reason next to the ignore. The last row of the table shows that the ignore does not reach other subnets.

The cost: the shared module names a platform subnet, and any other egress rule to every address on the orchestrator is hidden from Trivy too. A global entry in a `.trivyignore` file would have hidden the same finding on the worker and on every target subnet. The edge pull request moves the key to the edge subnet.

### On GitHub

The first push of this branch ran the pipeline with the `dynamic` block and no suppression. Trivy failed on `AZU-0051`, naming `azurerm_network_security_group.this["orchestrator"]` through the `dynamic.security_rule` content, so the pipeline's Trivy reads the rules. Checkov passed. The broken SSH rule was run locally only, not pushed.

### Plans

Expected before the run: no changes in either root, because the same rules are built through a different syntax. Run with Terraform 1.16.6, `plan -lock=false -detailed-exitcode`, against the live state, before the suppression comment was added. A comment does not change the configuration.

| Root | Result |
| --- | --- |
| Platform | `No changes`, exit 0 |
| Platform, with the SSH rule opened to `"*"` | Exit 2, `Plan: 0 to add, 1 to change, 0 to destroy`, the worker's security group updated in place. The plan sees a rule change, so `No changes` above means something |
| Targets, with the module source pointed at the changed local module | `No changes`, exit 0 |

The targets repository still pins the old module commit. Its pin moves in a pull request there after this one merges.

### Limits

- Checkov does not judge the security group rules ([#99](https://github.com/sindredg/ai-security-platform/issues/99)).
- `AZU-0051` is ignored for every rule on the orchestrator's security group, not only the two rules to the internet.
- The broken SSH rule was run locally, not on GitHub. The targets repository's pipeline gets the new module when its pin moves.

## The router

The mesh VPN agent moved from the orchestrator to a router VM of its own in Denmark East ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md)). The orchestrator is off the mesh. Run on 2026-10-17 between 13:40 and 14:35 UTC, through the steps of the [router runbook](../runbooks/mesh-router.md). This is the first of two stages of the edge network. The edge VM is not built.

### What changed

| Change | Where |
| --- | --- |
| The edge network, `10.45.0.0/24` in Denmark East, in the platform resource group, with the router subnet `10.45.0.32/27`. Outbound TCP 443 and 80 to the internet and TCP 22 to the platform, the targets, and the edge subnet. No inbound allow. Its own NAT gateway | `infra/platform/edge.tf` |
| The router VM, `Standard_B2ats_v2` in zone 1 at `10.45.0.36`, the same image as the other VMs. First boot installs the mesh agent at the held version with log upload off (`--no-logs-no-support`) and its own updater off, and advertises `10.40.0.0/20`, `10.50.0.0/20`, and `10.45.0.0/27` | `infra/platform/compute.tf`, `infra/platform/cloud-init/router.yaml.tftpl` |
| `allow-ssh-from-router` on the orchestrator's and the worker's security groups | `infra/platform/main.tf` |
| Peerings from the platform network to the edge network and back, and from the edge network to the target network | The same files. The network module takes a map of peerings now, with a `moved` block for the existing one |
| The orchestrator's template no longer installs the mesh agent, the segment size clamp, or IP forwarding | `infra/platform/cloud-init/orchestrator.yaml.tftpl` |
| The mesh checks read the router. New: `A.11` to `A.14`, `R.4` to `R.7`, `U.8`, `U.9`, `HR`, `M.6`, `M.7`, `Z.16` to `Z.19`. `M.2` now expects a timeout. `T.6` is retired | `validation/platform-checks.sh`, [access](../validation/access.md) |

The access policy grants operator devices TCP 22 to `tag:aisec-router` as well as to its three routes. ADR 0025 names the routes only, which leaves no way to administer the router itself over SSH.

### The applies

Written before the plan: 13 to add, 2 to change, 0 to destroy, and the existing peering moved in state, not replaced.

| Step | Plan | Result |
| --- | --- | --- |
| 1 | `13 to add, 2 to change, 0 to destroy`. `peering.this[0] has moved to ...this["peer-platform-to-targets"]` | 12 created, 2 changed. The VM failed: `PlatformImageNotFound: The platform image 'Canonical:ubuntu-26_04-lts:server:26.04.202610140' is not available` |
| 2 | `1 to add`, the VM, at `26.04.202610070` | `1 added, 0 changed, 0 destroyed` |
| After | `plan -detailed-exitcode` at 14:34 | `No changes`, exit 0 |

The first version gave the router `26.04.202610140`, read that morning with `az vm image list --publisher Canonical --offer ubuntu-26_04-lts --sku server --all`. That command matches `--offer` and `--sku` as prefixes. The version came from `ubuntu-26_04-lts-daily`, Canonical's daily builds, and from `server-gen1`. The newest release of `ubuntu-26_04-lts:server` was `26.04.202610070`, the pin the other VMs already had, so the router got that one. The runbook's first step now filters on the exact offer and SKU.

The auth key was not spent by the failed apply: the VM was never created.

### First boot and the change-over

| Step | Expected | Result |
| --- | --- | --- |
| Host key from the serial log, against a scan through the mesh | The same fingerprint | `SHA256:NsnbS5Js...` both times |
| First boot on the router | Marker, `status: done`, `/run/aisec` empty, units active, signed, the flag on the agent's command line | All as expected. `This node is accessible under Tailnet Lock`. `--no-logs-no-support` on the running `tailscaled`. `AdvertiseRoutes` the three networks |
| The orchestrator stops advertising its routes, from a detached unit | `AdvertiseRoutes` empty on the orchestrator, and both VMs see the router as the client | `"AdvertiseRoutes":null`. `SSH_CLIENT` `10.45.0.36` on the worker and on the orchestrator |
| The API server through `ssh -L` to the orchestrator, without credentials | TLS verifies against the cluster's certificate authority for `127.0.0.1`, and the answer is 401 | `ssl_verify_result=0`, HTTP 401. `openssl s_client -verify_ip 127.0.0.1`: `Verify return code: 0 (ok)` |
| Four failed logins to the worker through the router, then the feed key from the orchestrator | A penalty for `10.45.0.36` only, and the feed key accepted, exit 2 | `activating ipv4 penalty of 16 seconds` for `10.45.0.36`. Inside that window: `Accepted publickey for aisec-feed from 10.40.0.4`, exit 2 |
| The agent removed from the orchestrator, and its node removed in the admin console | No package, no interface, no clamp table | `A.11` reads `0 0` |
| The final access policy, with `tests` | Saved | Saved, with a placeholder where the operator's login belongs. See below |

The penalty result settles [#87](https://github.com/sindredg/ai-security-platform/issues/87). Operator sessions reach the worker from the router's address now, and the feed and the journal pull from the orchestrator's, so a failed operator login no longer blocks either. No exemption is needed.

The `kubectl` step ran without a kubeconfig: none exists on the workstation for this cluster, and copying the cluster administrator's credential off the orchestrator to show the path was not worth it. A request without credentials proves the tunnel, the certificate, and the API server. It does not prove a `kubectl` command.

### The policy tests

Written before the run: a policy that adds a grant from `tag:aisec-router` to `autogroup:member` on TCP 22 is refused by the second test, which denies the router the operator's login on 22, 80, 443, 445, and 3389.

The final policy was first saved with `REPLACE_WITH_YOUR_LOGIN` in place of the operator's login, in all six places. The console accepted it. With no such user, the router's `deny` entries pass whatever the grants say, so that policy proved nothing. The first test, which expects that user to reach the router on 22, passed too, though the name is not a member. That is read from the save, not explained.

The login was read from the router's own peer list (`tailscale status --json`, `LoginName`), filled in, and saved. Then the same policy with the bad grant added:

| Policy | Result |
| --- | --- |
| Final, with the operator's login | Saved |
| The same, plus a grant from `tag:aisec-router` to `autogroup:member` on `tcp:22` | Refused: `Error: test(s) failed`, `test(s) failed for user: tag:aisec-router` |

The bad policy was never in force. The console's error names the test's source and not the port.

### Checks

`validation/platform-checks.sh` from this branch:

| When (UTC) | Result |
| --- | --- |
| 14:24 | `193 passed, 1 failed`. `U.9`: 16 security updates pending on the router, `openssh-server` and `sudo` among them |
| 14:34, after `unattended-upgrade` on the router | `194 passed, 0 failed` |

The image is ten days old, and the daily upgrade first runs up to a day after boot: the timer was set for 06:13 the next morning. The router's template now runs `unattended-upgrade` at the end of first boot. That change has not run on a first boot.

### The fail side of each new check

Written before each run: the value that proves the claim, and an input that has to fail.

| Check | Pass | Fail seen |
| --- | --- | --- |
| `A.11` | Live after the change-over: `0 0` | Live on the orchestrator before it: `1 1`. The first version matched `install ok installed` and read `0 1` there, because a held package's status is `hold ok installed`. Half the check would have passed with the agent installed. It matches ` ok installed` now |
| `A.14`, `R.4`, `R.5` | Live on the router | Locally, with the orchestrator standing in as the router before the build: `local 127.0.0.1:6443`, two routes, and `0` |
| `M.2` | Live after the final policy: `timeout` | Live at 08:50 the same day, under the old claim: `open` |
| `U.9` | Live at 14:34: `0` | Live at 14:24: `16` |
| `Z.17` | Live: `0` | Locally, on the router's live effective rules with one inbound allow added: `1` |
| `A.2` to `A.4`, `A.12`, `A.13`, `R.1` to `R.3`, `R.6`, `R.7`, `E.5`, `U.2`, `U.6` to `U.8`, `HR`, `M.6`, `M.7`, `Z.16`, `Z.18`, `Z.19` | Live | On absence only: before the build, nothing answered. `R.6`, `R.7`, `U.6`, and `E.5` passed on the orchestrator before the change-over, the same values. No changed field was tried |

### Limits

- First boot from the router's template ran once, without the `unattended-upgrade` line. The orchestrator's template without the mesh has not run on a first boot.
- Each operator device has to run with `shields-up`, a device setting that no check reads. The policy's `tests` refused a bad change once, in the console. Nothing in the repository reads the policy, so a later edit that drops the tests goes unseen.
- The edge-to-targets peering is `Initiated`. The target repository adds its half, and an SSH rule from the router subnet, after this pull request merges.
- No `kubectl` command ran through the tunnel.
- The edge VM, Squid on it, the fetch window, and the orchestrator's loss of the internet are the next stage. Until then the orchestrator keeps its NAT gateway and its rules to the internet (T05).

## The edge VM

Squid moved from the orchestrator to an edge VM of its own in Denmark East, and the orchestrator lost its way out ([ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md)). Run on 2026-10-17 between 18:40 and 19:59 UTC, through the steps of the [edge runbook](../runbooks/edge-vm.md). This is the second stage of the edge network. Monitoring is not built.

### What changed

| Change | Where |
| --- | --- |
| The edge subnet, `10.45.0.0/27`, on the edge network's NAT gateway. Inbound TCP 3128 from the orchestrator and worker subnets and TCP 22 from the router subnet. Outbound TCP 443 and 80 to the internet | `infra/platform/edge.tf` |
| The edge VM, `Standard_B2als_v2` in zone 1 at `10.45.0.4`, the same image as the other VMs. First boot installs Squid and runs `unattended-upgrade`. No mesh agent | `infra/platform/compute.tf`, `infra/platform/cloud-init/edge.yaml.tftpl` |
| Squid on the edge: the worker gets `archive.ubuntu.com` and `security.ubuntu.com`, as before. The orchestrator gets `azure.archive.ubuntu.com` on port 80, and a tunnel on port 443 to the hosts in `edge/fetch-hosts` while a fetch window is open | The template, `edge/fetch-hosts` |
| The fetch window command: root only, at most 60 minutes, closed by a timer at a set time, every open and close logged. The window is a file under `/run`, so a reboot closes it | `edge/aisec-fetch-window` |
| The orchestrator's security group: no allow to the internet, denies for `Internet` and `AzurePlatformDNS`, TCP 3128 to the edge. Its inbound TCP 3128 from the worker goes. The worker's TCP 3128 goes to the edge | `infra/platform/main.tf` |
| The NAT gateway and public address in Sweden Central are gone. The edge network's gateway is the platform's only way out | `infra/platform/egress.tf`, removed |
| Squid is off the orchestrator. Its template sends apt, the operator's fetches (`/etc/environment`), and containerd's image pulls (`CONTAINERD_HTTPS_PROXY`) to the edge, and fetches K3s through it on first boot | `infra/platform/cloud-init/orchestrator.yaml.tftpl` |
| The first-boot scripts inside the templates are rendered and linted ([#101](https://github.com/sindredg/ai-security-platform/issues/101)) | `.github/scripts/render-first-boot.sh`, the ShellCheck job |
| New checks: `A.15` to `A.18`, `HE`, `P.12` to `P.18`, `U.10` to `U.13`, `E.12` to `E.14`, `C.10`, `M.8`, `Z.20` to `Z.23`. `P.1` to `P.4` read the edge. `P.5`, `U.3`, `M.3`, `Z.2`, and `Z.8` name the edge. `E.1` is retired | `validation/platform-checks.sh`, [validation](../validation/README.md) |

Pre-build reads, 17:39 UTC: image `26.04.202610070` is still the newest release, Denmark East had 2 of 4 cores in use, and `Standard_B2als_v2` is offered in zones 1 to 3 without restriction. The retail price API still has no Denmark East price. Sweden Central lists the size at USD 0.0389 per hour, as on 2026-10-16.

### The applies

Two applies, so the orchestrator kept its way out until both clients used the edge. Written before each plan.

| Apply | Expected | Plan | Result |
| --- | --- | --- | --- |
| 1, from `8879a73` | 6 to add, 2 to change, 0 to destroy | The same. Each of the two changed groups gains one rule for TCP 3128 to `10.45.0.0/27` | Applied at 18:46 UTC. A plan at 18:57 shows no changes |
| 2, from `99fbf6b` | 0 to add, 2 to change, 4 to destroy | The same: the Sweden Central gateway, its address, and both associations | `Apply complete! Resources: 0 added, 2 changed, 4 destroyed`, at 19:19 UTC |
| After | No changes | `plan -detailed-exitcode` at 19:50 | `No changes`, exit 0 |

### First boot and the change-over

| Step | Expected | Result |
| --- | --- | --- |
| Host key from the serial log, against a scan through the router | The same fingerprint | `SHA256:2sH0p8Aq...` both times |
| First boot on the edge | Marker, `status: done`, Squid active on `10.45.0.4:3128` only, window closed, nothing pending | All as expected. 0 failed units, 0 security updates pending, 572 MB of 3.8 GB in use |
| The worker's apt to the edge | `apt-get update` exits 0 from the two Ubuntu hosts | Exit 0. The edge logs `TCP_MISS` for both hosts from `10.40.0.36` |
| The orchestrator's apt, environment, and containerd to the edge, K3s restarted | Node `Ready`, every pod `Running`, `apt-get update` exits 0, a tunnel to `github.com` gets 403 | All as expected. containerd's environment has `HTTPS_PROXY`. The edge logs `TCP_MISS` for `azure.archive.ubuntu.com` and `TCP_DENIED/403 CONNECT github.com:443` |
| Squid removed from the orchestrator, after apply 2 | No package, nothing listening on 3128, K3s active | All as expected |

The change-over also logged four `TCP_DENIED/403 CONNECT esm.ubuntu.com:443` from the orchestrator. That is the image's apt hook for Ubuntu Pro's extended security maintenance, which is not enabled. It now reaches the proxy through `/etc/environment` and is refused. Not expected beforehand. Harmless.

### The fetch window

Written before the run: closed, a tunnel gets 403. Open, one small fetch from each host the orchestrator needs answers 200 or 206. Closed again, 403. A 1-minute window closes by its timer.

| Step | Result |
| --- | --- |
| Before | `closed`. Tunnel to `github.com`: 403 |
| Open for 15 minutes, then a ranged fetch from each host, as the operator's account | 206 from the K3s release asset (redirected to `release-assets.githubusercontent.com`), the K3s install script, a llama.cpp release asset, a Hugging Face file and a weight file (redirected to `us.aws.cdn.hf.co`), PyPI, and the PyTorch index. `git ls-remote` exit 0. Image pulls answered from the node |
| Close | `closed`. Tunnel to `github.com`: 403 |
| A 1-minute window | Closed by its timer 60 seconds after it opened |
| Image pulls of two images not on the node, in a second window | Both downloaded. Squid logged tunnels to `registry-1.docker.io`, `auth.docker.io`, `production.cloudfront.docker.com`, `ghcr.io`, and `pkg-containers.githubusercontent.com`, and refused nothing |

The first windows found three defects, fixed in `8ca922b`:

- Docker Hub serves layers from `production.cloudfront.docker.com`. The list named `production.cloudflare.docker.com`, so Squid refused the layer and the pull failed. The name now comes from Squid's log.
- `status` printed `open, closes` with no time. A timer started with `--on-active` has no wall-clock time to report. The close is scheduled with `--on-calendar` now.
- A timer close logged its line twice, once through `logger` and once from the service's standard output. One close, two lines. The output goes nowhere now.

The second test's first run tried to install the fixed command from `/dev/stdin` under `sudo`. That failed, so the run used the old command. Its second run installed the fix through a temporary file. The first run also removed an old tool service image that nothing used: the tag picked to test a download was already on the node.

A tunnel opened inside a window outlives it. Two tunnels that containerd opened before the manual close were logged 27 seconds after it, when they ended. Closing stops new tunnels only, as the command's header says.

Two names on the list have not appeared in a log: `objects.githubusercontent.com`, an older redirect target for GitHub release assets, and names under `.hf.co` other than `us.aws.cdn.hf.co`. Both belong to the same owner as a name that did appear.

### Checks

`validation/platform-checks.sh` from this branch:

| When (UTC) | Result |
| --- | --- |
| 19:15, after the change-over and before apply 2 | `230 passed, 5 failed`: `E.12` and `E.13` `open`, `P.12` `1`, `Z.2` `2`, `Z.22` `Allow allow-https-to-internet`. Exactly the five written down before the run |
| 19:23, after apply 2 | `234 passed, 1 failed`: `P.12`, Squid still installed |
| 19:30, after Squid was removed | `235 passed, 0 failed` |
| 19:59, with `E.14` and `C.10` | `237 passed, 0 failed` |

### The fail side of each new check

| Check | Pass | Fail seen |
| --- | --- | --- |
| `E.12`, `E.13`, `P.12`, `Z.2`, `Z.22` | Live after the change | Live at 19:15, before it, with the values above |
| `E.14`, `C.10` | Live: `timeout` | The same query from the edge, which may use Azure DNS: `answer` |
| `P.17`, `P.18` | Live | From a copy of the checkout with one line added to the command and to the list: `202 passed, 2 failed`, those two |
| `Z.21` | Live: the three inbound allows | Locally, on the edge's live effective rules with one inbound allow added: a fourth name in the list |
| `P.15`, `P.16` | Live, no window open | Not run during a window. The window test saw what they would read then: tunnels allowed, and `status` open |
| `A.15` to `A.18`, `HE`, `P.1` to `P.4`, `P.13`, `P.14`, `U.10` to `U.13`, `M.3`, `M.8`, `Z.20`, `Z.23` | Live | Not seen failing. No broken input was tried |

### Limits

- First boot from the orchestrator's template, which now fetches K3s through the edge in a window, has not run. A rebuilt orchestrator needs a window open before it boots, and the runbook says so.
- First boot from the edge's template ran once, with the command and list from `7532cbb`. The fixed command was installed by hand.
- An open tunnel outlives the window. A fetch started in the last minute of a window can run on after it closes.
- Squid sees host names, not content. During a window the orchestrator can upload to an account of its own on any listed host (T40).
- The edge-to-targets peering is still `Initiated`. The target repository adds its half, and SSH from the router subnet, after this pull request merges.
- cloud-init's final stage writes the administrator's `authorized_keys` back empty, after first boot removed it, on the router and the edge. Its log names the `ssh_authkey_fingerprints` module. The file authorizes nothing, and sshd ignores it for this account. The template comments said the file goes. They say what happens now.

## The edge and target peering

The router sits in the edge network, and peering is not transitive. The edge's half of its peering to the targets was built with the router and stayed `Initiated`. This change adds the target half and SSH from the router subnet on the target side ([ADR 0025](../decisions/0025-the-mesh-node-on-its-own-vm.md)).

### What changed

| Change | Where |
| --- | --- |
| The shared module pin moves from `9ffaba0` to `77803d8`, which takes a map of peerings. A `moved` block keeps `peer-targets-to-platform` in place | `infra/targets/main.tf` in the targets repository, [pull request 5](https://github.com/sindredg/ai-security-platform-test/pull/5) |
| `peer-targets-to-edge`, from a new `edge_virtual_network_id` input | The same |
| `allow-ssh-from-router` on each target group: TCP 22 from `10.45.0.32/27`, priority 1020 | The same |
| `Z.24` reads both halves of the edge and target peering. `Z.25` reads each target group's inbound allows | `validation/platform-checks.sh` |

The custom peering role the bootstrap root gives the target identity is scoped to the whole platform resource group, so it already covered the edge network. No role changed.

### The apply

Written before the plan, from the module diff: the peering moves in state with no change, the four security groups change in place to add the one rule, and the edge peering is added. `Plan: 1 to add, 4 to change, 0 to destroy.`

| Step | Result |
| --- | --- |
| `terraform plan -out=targets.tfplan`, as the target identity | As written: four groups updated in place, `peer-targets-to-edge` created, `this[0]` has moved to `this["peer-targets-to-platform"]`. `Plan: 1 to add, 4 to change, 0 to destroy.` |
| `terraform apply targets.tfplan` | `Apply complete! Resources: 1 added, 4 changed, 0 destroyed.` |
| `az network vnet peering show`, both halves | `Connected`, `FullyInSync`. The edge half read `Initiated`, `RemoteNotInSync` before the apply. Forwarded traffic, gateway transit, and remote gateways are off on the target half |
| `terraform plan -detailed-exitcode`, both roots | Exit 0, `No changes` |
| `az network watcher test-ip-flow` from the router to `10.50.0.4` | Port 22: `Allow`, `allow-ssh-to-targets`. Port 23: `Deny`, `deny-all-outbound` |
| `validation/platform-checks.sh` | `239 passed, 0 failed`, with `Z.24` and `Z.25` |

### The fail side of each new check

Each check's lines were run alone, with the script's `check` function, against the live system.

| Check | Pass | Fail seen |
| --- | --- | --- |
| `Z.24` | `Connected Connected` | A wrong name for the target half: `Connected ` (absence). `peeringSyncLevel` read in place of `peeringState`: `FullyInSync FullyInSync` |
| `Z.25` | The two SSH allows on each of the four groups | A resource group that does not exist: four empty lists (absence). A stub that adds `allow-http-from-orchestrator` on port 80 to the live answer for `netbox`: that group's list has three rules |

### Limits

- No target VM exists. No login through the router to a target has run, and neither flow verify nor effective rules can read the target side, because both need a network interface. `Z.25` reads the configured rules, not what Azure enforces.
- The network foundation runbook's steps 8 and 9 and its rebuild steps were changed for the second peering. They have not been run in that form.

## Monitoring

The log store of [ADR 0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md), with the changes in [ADR 0027](../decisions/0027-how-the-monitoring-is-built.md). Alert rules, flow logs, the workbook, and the measured daily cap are not part of this slice.

### What changed

| Change | Where |
| --- | --- |
| A Log Analytics workspace in Sweden Central: no public ingestion, no shared key, 31 days, a 1 GB daily cap. Three custom tables, one row per line in `RawData` | `infra/platform/monitoring.tf` |
| A Private Link Scope, ingestion `PrivateOnly`, query `Open`, with the workspace and two collection endpoints, one per region with an agent | The same |
| A private endpoint in a new subnet, `10.40.0.64/27`. Its group allows TCP 443 from the orchestrator, the edge, and the router. Each of those three gets one outbound rule to it, priority 1030 | `infra/platform/main.tf`, `edge.tf`. The module takes `private_endpoint_network_policies`, so the group applies to the endpoint |
| A system-assigned identity on the orchestrator, the edge, and the router. None on the worker | `infra/platform/compute.tf` |
| Hosts entries from the endpoint's record, written by a script through managed run command | `platform/monitoring/aisec-monitor-hosts`, linted by ShellCheck in the pipeline |
| The Azure Monitor Agent extension, `1.45`, automatic upgrades off. Three collection rules: syslog and load on all three, the two copies on the orchestrator, Squid's log on the edge | `infra/platform/monitoring.tf` |
| `Microsoft.Insights` and `Microsoft.OperationalInsights` registered | `infra/bootstrap/main.tf` |
| `O.1` to `O.13` | `validation/platform-checks.sh`, [validation](../validation/monitoring.md) |

Read on 2026-10-17 before the change: azurerm `5.10.0` is the newest release. The agent's newest Linux version in both regions is `1.45.1`, and its release notes list Ubuntu 26.04 for x64 and Arm64. A standard private endpoint is USD 0.01 an hour and USD 0.01 per GB in the retail price API.

### Tested before the apply

| Test | Result |
| --- | --- |
| The hosts script against a copy of a hosts file, with stubs for the input | Writes the block between its markers and keeps the other lines. A second run replaces the block. Refuses, and leaves the file unchanged: a public address, a name outside Azure Monitor, an address outside `10.40.0.64/27`, no input, input that is not base64, and an extra line naming `evil.com` |
| `terraform plan` | `Plan: 31 to add, 6 to change, 0 to destroy.` The changes: the three identities, and the outbound rule in three groups. Nothing replaced |
| Checkov, Trivy, ShellCheck on a clean copy | Checkov `Passed checks: 36, Failed checks: 0, Skipped checks: 8`. Trivy 0.76.0: no findings. ShellCheck 0.11.0: no findings |
| `validation/platform-checks.sh` at 22:50 UTC | `241 passed, 11 failed`. The 11 are the new checks, each on absence. `O.4` and `O.13` passed |

### The applies

Written before the apply: `O.1` to `O.3` read `1 active`, `O.5` to `O.7` match the endpoint's record, `O.8` reads `Disabled Enabled true`, `O.9` `PrivateOnly Open`, `O.10` lists all three VMs, `O.11` `yes`, `O.12` no role for any identity.

| Step | Result |
| --- | --- |
| First platform apply, from the saved plan | Stopped on four errors: `MissingSubscriptionRegistration` for `Microsoft.OperationalInsights` (the workspace) and `microsoft.insights` (the scope and both endpoints). azurerm 5 registers no provider unless told to, and the platform identity cannot register one. A new plan read `Plan: 28 to add, 0 to change, 0 to destroy.`, so the subnet, its group, the rules, and the identities were in place |
| Bootstrap plan and apply, as the operator | `Plan: 2 to add`. `Apply complete! Resources: 2 added, 0 changed, 0 destroyed.` Each registration took about three minutes. The state copy's `content_md5` equals the local file's |
| Second platform apply | `Apply complete! Resources: 28 added, 0 changed, 0 destroyed.` The agent extensions finished in 24 to 37 seconds |
| `az vm run-command show` on each VM | `Succeeded`, exit `0`, `wrote 17 entries` |
| `validation/platform-checks.sh` at 23:39 UTC | `252 passed, 0 failed` |

The run commands and the agents installed with no internet on the orchestrator. Its heartbeat arrived, and the orchestrator has no route to the internet and no DNS. So the agent needs neither Azure Resource Manager nor any public name on the private path, which ADR 0021 left open.

### What arrived

Read with the operator's sign-in, through the workspace's query API, between 23:39 and 23:45 UTC.

| Table | From | Result |
| --- | --- | --- |
| `Heartbeat` | All three | One a minute from each since 23:32 |
| `Syslog` | All three | `auth` and `authpriv` at `info`, from the checks' logins |
| `Perf` | All three | Every minute since 23:34 |
| `AisecWorkerJournal_CL` | Orchestrator | 446 rows from the pulls after 23:32. The file holds 65,142 lines: the agent starts at the end of a file, so earlier lines are on the orchestrator only. No row holds more than one line |
| `AisecSquidAccess_CL` | Edge | 11 rows by 23:41, with the checks' `TCP_DENIED` requests |
| `AisecToolAudit_CL` | Orchestrator | The line with `seq` 53, written at 23:35:01 by `T.10`, arrived about 23:43, eight minutes later: the table's first row. The line with `seq` 54, from one refused call at 23:42:10, was ingested at 23:43:22. Both rows equal the file's lines byte for byte |

The agent applies a multiline parser to text files even when no timestamp format is set. Its start rule wants a line that begins with a timestamp. Lines that begin with `{` are passed one per row, as the journal's 446 single-line rows show.

### The fail side of each new check

| Check | Pass | Fail seen |
| --- | --- | --- |
| `O.1` to `O.3` | `1 active` | `0 inactive` before the apply (absence) |
| `O.4` | `0` | `1` from the same probe on the orchestrator, where the agent is installed |
| `O.5` to `O.7` | Equal hashes | Before the apply: no record from the endpoint. After: a stub that changes one address in the endpoint's list gives a different hash from the orchestrator's block |
| `O.8`, `O.9`, `O.11` | As written | Empty before the apply (absence) |
| `O.10` | Three computers | Empty before the apply (absence). A stopped agent is the alert drill in the next slice |
| `O.12` | `0` for each | `no identity` for each before the apply |
| `O.13` | `none` | `SystemAssigned` from the same query on the orchestrator |

### A pod and the metadata service

From a new pod in `default`, with the probe from the [orchestrator hardening runbook](../runbooks/orchestrator-hardening.md): `169.254.169.254:80 timeout  10.40.0.75:443 timeout  10.40.0.4:6443 open`. The API server is the control. From the orchestrator itself both addresses open. So a pod can ask neither for the VM's token nor send to the workspace. `10.40.0.75` is the workspace's ingestion address.

### Footprint

`ps` and `free -m` at 23:41 UTC, about nine minutes after the install. One reading, not a measurement over time.

| VM | Agent processes, RSS | CPU | Memory available |
| --- | --- | --- | --- |
| Orchestrator | 199 MB | 0.3 % | 6,531 of 7,881 MB |
| Edge | 192 MB | 0.3 % | 3,092 of 3,855 MB |
| Router | 88 MB | 0.3 % | 396 of 836 MB |

### Limits

- No alert rule exists. A stopped agent, a hole in the sequence, or a refused request shows only when someone queries or runs the checks.
- The footprint is one reading. The 3a criterion asks for a measurement, and the day of volume for the cap is still to come ([ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md)).
- Lines written before the agent started are not in the workspace.
- The edge and the router can still reach the internet on TCP 443. Nothing stops root on either from sending to another workspace.
- The first boot of a VM with the agent, and the runbook's undo step, have not run.

## Alert rules and flow logs

The alert rules, the Activity Log rules, the flow logs, and the workbook of [ADR 0021](../decisions/0021-monitoring-in-azure-monitor-over-private-link.md), as built by [ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md), and one drill for each rule.

### What changed

| Change | Where |
| --- | --- |
| 13 log alert rules on the workspace, stateful, with no action group | `infra/platform/alerts.tf` |
| The workbook: tool calls, Squid requests, flows, and load | `infra/platform/workbook.tf` |
| The drill file `/var/log/aisec/alert-drill.jsonl`, collected into the audit table | `infra/platform/monitoring.tf` |
| Four Activity Log rules on the subscription, in the platform state group | `infra/bootstrap/monitoring.tf` |
| Flow logs with traffic analytics on the platform and edge networks, and their storage in the platform state group | The same |
| `O.14` to `O.17` | `validation/platform-checks.sh` |
| ADR 0027 accepted. ADR 0028 proposed | `docs/decisions/` |

### The applies

| Step | Result |
| --- | --- |
| Bootstrap, the four Activity Log rules, as the operator, at about 00:00 UTC | `Apply complete! Resources: 4 added` |
| Bootstrap, a custom role with the flow log actions on the two network watchers, assigned to the platform identity | First run: refused with `AuthorizationFailed` on `roleDefinitions/write`, because platform identity variables left in the operator's shell made Terraform sign in as the platform identity. The runbook now clears them. Second run at 07:51: `3 added`, state copy checksums equal |
| Platform, alert rules, flow logs, storage, workbook | 16 of 18 created. Both flow logs failed with `TAUserDoesNotHavePermissions`. Traffic analytics creates a collection rule and endpoint of its own, and Azure checks that permission on the workspace's subscription. Azure kept both flow logs, in state `Failed` |
| The redesign | The flow logs and their storage moved to the bootstrap root, written as the operator ([ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md)). Platform: `2 destroyed`, the empty storage accounts. Bootstrap: the role and its two assignments destroyed, two storage accounts created. The flow logs collided with the two `Failed` ones, which were deleted with `az network watcher flow-log delete`. Bootstrap again: `2 added`. State copy checksums equal |
| `terraform plan` on both roots | `No changes` |

The role's assignments and their deletion fired `role-assignments` four times, at 07:55 and 08:25.

### The drills

Run from a script with the commands in the [runbook](../runbooks/monitoring.md#alert-rules-flow-logs-and-drills), step 11. The three long drills started at 08:33:27 UTC. The script stopped at the next step: `az network nsg update --set tags.aisec-drill=1` was refused, `Expect <class 'str'>, got 1`. A second script with the value `drill` resumed at 08:47:34. Everything was put back at 08:55: the router's agent and the journal timer `active`, the edge's disk at 12 percent.

| Rule | Drill, UTC | Fired, UTC | Severity |
| --- | --- | --- | --- |
| `role-assignments` | The flow log role's two assignments, created at about 07:55 and deleted at about 08:25 | 07:55:34, 07:55:36, 08:25:33, 08:25:33 | Sev4 |
| `ssh-login-accepted` | The script's logins, from 08:33 | 08:39:38 | Sev3 |
| `disk-or-memory` | `/` on the edge at 88 percent from 08:33:27 | 08:45:27 | Sev2 |
| `heartbeat-missing` | The router's agent stopped at 08:33:27 | 08:46:03, resolved after the restart at 08:55 | Sev1 |
| `audit-sequence` | `seq` 1 and 3 of one `drill-` start, 08:47:57 | 08:49:47 | Sev1 |
| `tool-refusal-burst` | 25 calls without a token, 08:48:17 | 08:50:23 | Sev2 |
| `security-groups` | A tag written and removed, 08:47:36 and 08:47:41 | 08:50:32 twice, and 09:05:33 | Sev4 |
| `security-rules` | A description written and put back, 08:47:47 and 08:47:51 | 08:50:32 twice | Sev4 |
| `policy-assignments` | A description written and put back | 08:50:32 twice | Sev4 |
| `fetch-window-opened` | Opened for one minute and closed, 08:48:01 | 08:50:54 | Sev3 |
| `failed-unit` | `/bin/false` as a transient unit on the edge, 08:48:19 | 08:52:01 | Sev2 |
| `squid-refused-orchestrator` | A tunnel to `example.com` from the orchestrator, 08:47:59, `403` | 08:52:40 | Sev1 |
| `copy-marker` | A line with `"event":"copy"` in the drill file, 08:47:57 | 08:53:07 | Sev1 |
| `journal-missing` | The journal timer stopped at 08:33:27. The last row was collected at 08:32:51 | 08:53:57, resolved after the restart | Sev2 |
| `ssh-login-failed` | An expired certificate offered to the router, 08:48:16 | 09:00:13 | Sev2 |
| `denied-flow-to-internet` | TCP to `1.1.1.1:443` from the worker and the orchestrator, 08:48:03 | Not fired. See below | |
| `daily-cap` | Not drilled. Lowering the cap stops ingestion for the rest of the day | | |

What the drills showed beyond the firing:

- **`ssh-login-failed` came late for a reason.** The router's agent was stopped when the certificate was refused. The line was collected at 08:55:30, when the agent started again. The agent catches up on syslog after a stop instead of losing it, and the row carries the collection time, not the event's.
- **`journal-missing` fired 21 minutes after the last row**: the 15-minute window, and the rule's own delay. A rule that watches for silence, with no rows to count, did fire.
- **A third `security-groups` alert at 09:05 came from the drill.** The Activity Log holds a second `Succeeded` event for the tag removal, at 08:57:42, with the same correlation ID as the call at 08:47:41. One write can fire the rule twice.
- **Activity Log alerts show as Sev4.** They have no severity setting, as ADR 0028 expected.

### Traffic analytics

Traffic analytics wrote 206 flow rows by 09:13, every one from `fl-aisec-edge`. The platform network's flow log is enabled and `Succeeded`, and Network Watcher writes to its storage: 128 successful transactions between 08:15 and 09:15, against 271 on the edge's account. None of it has been processed. Each interval's status row says `Completed`. Traffic analytics created four `NWTA` resources in the platform group at 08:26, when the operator's apply created the flow logs: a collection rule and a collection endpoint for each flow log. The cause is not known.

The records exist. With Storage Blob Data Reader on the platform flow log's account, granted to the operator for this, the 08:00 UTC blobs, one per network interface, hold the drill's connections: 5 tuples from `10.40.0.4` and 5 from `10.40.0.36` to `1.1.1.1:443`, outbound, under `UserRule_deny-to-internet`. Recording works and processing does not. So the denied flows are not in the workspace, and `denied-flow-to-internet` has not fired. The router's denied flows, UDP that its rules do not allow, are there, from the edge flow log.

### The fail side of each new check

Each check's lines were run alone against the live system with one input changed, on 2026-10-18.

| Check | Pass | Fail seen |
| --- | --- | --- |
| `O.14` | The 13 rules, each `on stateful none` | A rule name added to the checkout: different. One rule's answer edited to `stateless`: different |
| `O.15` | The four rules in the platform state group | The same query on the platform group: 0 rules |
| `O.16` | Both flow logs, `true true 10` | A name that does not exist: an empty answer |
| `O.17` | Not yet seen | `fl-aisec-edge` alone, live, since the platform flow log is not processed |

### Checks

`validation/platform-checks.sh` at 09:07 UTC: `256 passed, 0 failed`. `O.17` then counted rows from any flow log, and passed on the edge's alone. It now names each flow log.

### Limits

- The platform network's flows are not processed through 10:00 UTC ([#111](https://github.com/sindredg/ai-security-platform/issues/111)). `denied-flow-to-internet` has never fired, and `O.17` fails on it.
- `daily-cap` and the memory half of `disk-or-memory` were not fired.
- A drill line stays in the audit table for 31 days.
- Flow records are kept 90 days, the scanners' floor (Checkov `CKV_AZURE_12`, Trivy `AZU-0049`). They were set to 31 at first.

## Open issues fixed before the review

Five open issues that fit milestone 3a, on 2026-10-18.

### What changed

| Issue | Change | Where |
| --- | --- | --- |
| [#103](https://github.com/sindredg/ai-security-platform/issues/103) | `P.19`: Squid's configuration on the edge is root's and equals the edge template, rendered by Terraform with the platform's addresses | `validation/platform-checks.sh` |
| [#104](https://github.com/sindredg/ai-security-platform/issues/104) | The job "Squid configuration": the runner's Squid parses the rendered configuration with the fetch window closed and open, and fails on a warning | `.github/workflows/checks.yml` |
| [#103](https://github.com/sindredg/ai-security-platform/issues/103), [#104](https://github.com/sindredg/ai-security-platform/issues/104) | One renderer for any file a cloud-init template writes. The first-boot renderer now calls it | `.github/scripts/render-cloud-init-file.sh`, `.github/scripts/render-first-boot.sh` |
| [#99](https://github.com/sindredg/ai-security-platform/issues/99) | The network module refuses an inbound Allow rule from any source, `Internet`, `0.0.0.0/0`, or `::/0`. `terraform test` against a mocked provider shows it, in the Terraform job | `infra/modules/network/variables.tf`, `infra/modules/network/tests/` |
| [#81](https://github.com/sindredg/ai-security-platform/issues/81) | The audit copier skips the kubelet's `.tmp` file while it compresses a rotated log | `platform/logs/aisec_audit_copy.py` |
| [#25](https://github.com/sindredg/ai-security-platform/issues/25) | Decided: service tags stay compared by name, as a documented limit | [containment](../validation/containment.md#what-z4-and-z5-compare) |

### The fail side of each new check

Run locally on 2026-10-18, against the live edge where a VM is involved.

| Check | Pass | Fail seen |
| --- | --- | --- |
| `P.19` | Live: the edge's `squid.conf` and the rendering have the same SHA-256, `a55d006b...`, and `root 644` | Live, against a copy of the template with an `http_access allow all` line added: different hashes. With `TERRAFORM=/nonexistent`: `the edge template did not render` |
| The renderer | The first-boot scripts rendered by the old and the new renderer are equal (`diff -r`) | A path the template does not write: `expected one entry for /etc/nope, found 0`, exit 1. A value with `${`: refused, exit 1 |
| The module test | `terraform test`: `6 passed, 0 failed` | With the validation removed: `allow_from_any_is_refused` fails, `2 passed, 1 failed, 3 skipped` |
| The copier test | `29` tests pass with the fix | Before the fix the new test fails with `a line without the runtime's prefix`. A first version passed on the old code: its `.tmp` held a 10-byte gzip header with no line break, so the copier read no line from it. The test now asserts the compressed data holds one |

The Squid job ran on GitHub only, since the workstation has no Squid. The runner's Squid is `7.2`, as on the edge, and both window states parsed with no warning. A commit that added `cdn-lfs.hf.co` to `edge/fetch-hosts`, under `.hf.co`, failed the job with `WARNING: Ignoring cdn-lfs.hf.co because it is already covered by .hf.co`, exit 1. The next commit reverted it. The module test passed on GitHub too: `6 passed, 0 failed`.

`terraform plan` on the platform root with the module's new validation: `No changes`. Trivy and Checkov on a clean copy of `infra/`: no finding, `Passed checks: 56, Failed checks: 0, Skipped checks: 18`.

### On the live system

The fixed copier was installed on the orchestrator from `main` at `2114890`, at about 11:22 UTC, with the install script from the [runbook](../runbooks/audit-log.md). `L.8` failed before the install, as it should with the old copier in place, and passes after it. The unit was `active`, and the installed program holds the `.tmp` skip. A refused request from the worker afterwards was copied: the file went from 138 to 139 lines, and the last line is the refusal, `seq` 85.

The whole check run after it: `255 passed, 2 failed`. `O.17` is [#111](https://github.com/sindredg/ai-security-platform/issues/111). `O.16` failed because the platform flow log was on a 60-minute interval at the time, a test for #111.

### The target root's pin

The target root pinned the module at `77803d8`, from before the refusal, so the targets did not get it. [Targets PR 6](https://github.com/sindredg/ai-security-platform-test/pull/6) moves the pin to `2114890`. `terraform plan` with the new pin: `No changes`, exit 0.

### Review

A review of these changes on 2026-10-18 found the pin above, this section's missing install result, a stale settings date on the [pipeline page](../components/pipeline.md#repository-settings), and an overstated `P.19` description: its addresses are constants in the check script, not read from Terraform. All four are fixed. It also found that the renderer took an override name no template has, and rendered the placeholder for the name meant. It now refuses one: `edge_iip=10.45.0.4` exits 1 with `no template variable named edge_iip`, and the edge's real addresses still render to the hash `P.19` passed on. `P.19` reads the file, not the configuration Squid runs ([#114](https://github.com/sindredg/ai-security-platform/issues/114)).

### Limits

- `P.19` needs `terraform` on the workstation that runs the checks.
- The Squid job parses with the runner's Squid. The edge's is the same release only while both are current.
- The module refuses four ways of writing "any source". A rule from a wide private range, or a port opened wider than needed, is still judged by Trivy alone.
- The copier fix is reasoned from the kubelet's source on `master`, as in #81. The pod's log has not rotated on the live orchestrator yet.

## The platform flow log

Traffic analytics never processed the platform network's flow log ([#111](https://github.com/sindredg/ai-security-platform/issues/111), [traffic analytics](#traffic-analytics)). Two changes on 2026-10-18 did not help, and the gap was accepted that day.

| Change | When, UTC | Result |
| --- | --- | --- |
| `fl-aisec-platform` replaced through the bootstrap root | 10:37 | No platform row by 11:25 |
| Traffic analytics interval 60 minutes instead of 10, applied from a local change to the bootstrap root that was not committed | 11:28 to about 13:45 | No platform row by 13:41, in two separate queries |

Read on the live system between 13:30 and 13:41, as the operator:

- The flow log is enabled and `Succeeded`. Its blobs are written every hour, the last one at 13:30.
- `NTANetAnalytics` status rows (`SubType == "StatusMessage"`) came every 10 minutes, each `Completed`. None came on the hour while the platform's flow log ran at 60 minutes. Status rows name no flow log, so the link to the edge's 10-minute interval is inferred from the timing. Traffic analytics records nothing for the platform's flow log, not even a failure.
- The platform network, its flow log, and its storage account are in Sweden Central, the workspace's region. The edge's are in Denmark East. Both storage accounts have the same network and authentication settings: public network access on, default action `Allow`, Azure services allowed, shared key off. Sweden Central supports traffic analytics ([supported regions](https://learn.microsoft.com/azure/network-watcher/supported-region-traffic-analytics), read on 2026-10-18). The cause is not known.

The interval went back to 10 afterwards. A bootstrap plan from the committed code showed one change, `interval_in_minutes = 60 -> 10`, and its apply ended with `1 changed`. The flow log then read `10 Succeeded`. The state copy was uploaded, and its `content_md5` equals the file's MD5.

What remains, and the trigger to look again, are in [accepted risks](../security/accepted-risks.md). `denied-flow-to-internet` stays in place.

### The fail side of the changed check

`O.17` now expects `fl-aisec-edge` alone. Its lines were run alone against the live workspace at 13:50 UTC.

| Input | Result |
| --- | --- |
| The real query | Pass: `fl-aisec-edge` |
| No answer, a workspace that does not exist | Fail: empty |
| No rows, a window of 0 seconds | Fail: empty |
| A platform row, added to the answer with `union` | Fail: `fl-aisec-edge fl-aisec-platform` |

### Checks

`validation/platform-checks.sh` from `main`, finished at about 13:54 UTC, after the interval went back: `256 passed, 1 failed`. `O.16` passed. `O.17` failed on its old expected value, both flow logs. From the branch with the changed `O.17`, at 14:00 UTC: `257 passed, 0 failed`.

## Review of the milestone

A review of the milestone's claims on 2026-10-18, against the code, the pipeline, and the live system. Read and found as the pages say: plans of the platform, bootstrap, and target roots (`No changes`), every check ID the pages cite (each exists, or is named as retired), links and anchors in every tracked page, the repository settings, the security rules, the outbound gateways, Squid's host lists, the version pins against each upstream, and the numbers the pages give for the daily cap, the certificate lifetime, the rate limit, and the fetch window.

### Fixed

| Finding | Change |
| --- | --- |
| The threat model said no alert fires on a hole in the audit sequence | `T21` names `audit-sequence`. `T35` names the spent enrollment keys of both the router and the orchestrator |
| The version table named a daily build as the newest Ubuntu image | The pin is the newest release. Rows read again on 2026-10-18 carry that date |
| Lab against production said deny by default was tested on the worker only, and that a rebuild loses the journal copy | Both rows name the orchestrator's checks and the copy in Azure Monitor |
| The architecture's threat model row stopped at 2026-10-16 | It names the revisions of 2026-10-17 and 2026-10-18 |
| Four component pages gave "Built" with no evidence | Each names its checks or worklog |
| The tool service diagram showed a mesh device stopped by "no node port on the mesh address" | It shows the device coming through the router, stopped by the mesh policy and the orchestrator's security group |
| The credential inventory said a certificate expires on 2026-10-18 | It says the certificate expired |
| Two monitoring failures had no troubleshooting entry | [08](../troubleshooting/08-monitoring-providers-not-registered.md) and [09](../troubleshooting/09-traffic-analytics-refuses-the-platform-identity.md) |
| Edge checks recorded as passing without a fail side, and host hardening `.1` to `.16` with none on any VM | Run against broken inputs, below |

Two findings became issues: [#118](https://github.com/sindredg/ai-security-platform/issues/118) and [#119](https://github.com/sindredg/ai-security-platform/issues/119).

### The fail side of the edge checks

Written before each run: the broken input, and the value the check would then read. Each check's own probe line or comparison ran on that input, read-only, on 2026-10-18.

| Check | Broken input | Read | How |
| --- | --- | --- | --- |
| `A.15` | A host name that does not exist | `no` | Live |
| `A.16` | A file with one key line | `1` | Locally |
| `A.17` | The orchestrator, where the administrator may forward to the API server | `local 127.0.0.1:6443` | Live |
| `A.18`, `P.1`, `P.2`, `U.10` | The router, which has the mesh agent and no Squid or proxy setting | `1`, `inactive`, empty, `0` | Live |
| `U.11` | The router, which runs no containerd | empty | Live, on absence |
| `P.3` | The `ssh` unit on the edge, which lacks the setting | `no` | Live |
| `U.12` | A unit name that does not exist on the edge | `not-found` | Live, on absence |
| `P.4` | The same request from the orchestrator, an allowed client | `200` | Live, request changed |
| `P.13`, `P.14` | Each check's request with the other check's host | `403`, `200` | Live, request changed |
| `M.3`, `M.8` | Each check's port swapped with the other's | `open`, `timeout` | Live, request changed |
| `Z.20` | The edge's live effective rules with one port changed | `different` | Locally, on live answers |
| `Z.23` | IP flow verify to port 3129, which no rule allows | `Deny deny-all-outbound` | Live, request changed |
| `.2` to `.6` | Ubuntu's default `sshd_config` on the edge, without its `Include` line | `prohibit-password`, `yes`, `yes`, `yes`, `6` | Live |
| `.7`, `.8`, `.10` to `.14` | The same lines on the workstation, which is not hardened | `176`, `1`, empty, `644`, empty, `755`, `4` | Locally |
| `.1`, `.9`, `.15`, `.16` | Stubbed commands that print a failed unit, redirects on, `sctp` loaded, and no time sync | `1`, `1`, `1`, `no` | Stubs |

`U.13` shares its line with `U.9`, which failed live on 2026-10-17. `.17` to `.20` failed live before the rollout of 2026-10-16 ([fail side](#the-fail-side-of-each-new-check-1)).

Two inputs needed a second try. With the `Include` line in place, Ubuntu's default configuration reads the edge's hardening drop-in, so `.2` to `.6` passed. The workstation already ignores ICMP redirects, so `.9` passed there and moved to the stubs. The expected value for `.2` was reasoned as `without-password`. OpenSSH prints `prohibit-password`, which fails the check the same way.

### Limits

- "Request changed" means the check's own probe ran with a different request, against controls that were not changed. It shows the check reads the failing value when a request meets an open path. It does not show the check failing while the control is wrong. `M.3` and `M.8` have the limit of `M.5` in [#64](https://github.com/sindredg/ai-security-platform/issues/64): changing the mesh policy is not a read-only step.
- The H checks on the workstation and with stubs ran the probe's lines outside a VM. The lines are the same on every VM.

## Before the AI part

Date: 2026-10-18. Four open issues closed before milestone 3 resumes with dispatch and the agent. Nothing on the VMs or in Azure changed.

### What changed

| Issue | Change |
| --- | --- |
| [#31](https://github.com/sindredg/ai-security-platform/issues/31) | The [agent runtime checks](../validation/agent-runtime.md), `G.1` to `G.4`: the Goose binary against a pin of its own, the fixture against the checkout, and no unit or private directory left by a finished job. `pins.env` holds the binary's SHA-256, read from the release archive on the workstation after the archive matched `artifacts.tsv` |
| [#114](https://github.com/sindredg/ai-security-platform/issues/114) | `P.20` to `P.22` on the [package proxy](../validation/package-proxy.md): Squid's running command line, its one drop-in against the template, and a configuration load later than the last change to any of its three files |
| [#118](https://github.com/sindredg/ai-security-platform/issues/118) | The ShellCheck job finds a script by a `.sh` name or by a first line that starts a shell, instead of a list of four paths |
| [#119](https://github.com/sindredg/ai-security-platform/issues/119) | The [log copies diagram](../security/audit-log.md) shows the log agent sending both files to the workspace |

### The fail side of each new check

Written down before the runs: the value each check reads on the live system, and the broken input that has to make it fail. Each probe line ran on its broken input on the live VMs at 19:04 UTC, read-only.

| Check | Broken input | Read | How |
| --- | --- | --- | --- |
| `G.1` | `/usr/bin/python3`, and a version that is not installed | `root 777 d1b87c36...`, empty | Live, input changed |
| `G.2` | None: it fails on the live worker | See below | Live |
| `G.3` | The model server's unit | `loaded` | Live, input changed |
| `G.4` | The model server's unit | `2` | Live, input changed |
| `P.20` | The `chrony` unit's main process | `/bin/sh /usr/lib/systemd/scripts/chronyd-starter.sh -n -F 1` | Live, input changed |
| `P.21` | The `ssh` unit, which has no drop-in | Empty | Live, input changed |
| `P.21` | The template with `NoNewPrivileges=no` | A different SHA-256, `3eca73f2...` | Locally |
| `P.22` | Squid's access log added to the files compared, which changes on every request | `no` | Live, input changed |
| `P.22` | A load line that never appears | `no` | Live, input changed |
| ShellCheck selection | A new script without an extension that starts with `#!/bin/sh` and has an unquoted `$1` | Selected, `SC2086`, exit `1`. A Python file next to it was not selected | Locally, ShellCheck 0.11.0 |

On today's tree the new selection lists the same 25 files as the old one, and ShellCheck passes on them.

### What `G.2` found

The fixture on the worker is the one installed on 2026-10-12, from commit `3eaa3ca`. Two of its files, `check_answer.py` and `evidence_tool.py`, were reformatted in the repository two days later by `683ee71`, which added the formatter to the pipeline. The change is layout only. Nothing installed them again, so `G.2` fails: the digest the worker reports, `c41699a2...`, equals the digest of the four files as of `3eaa3ca`, computed on the workstation.

It stays failing until the agent runtime is installed again, with the Goose update in [#83](https://github.com/sindredg/ai-security-platform/issues/83).

### Checks

`validation/platform-checks.sh` from the branch, finished at 19:03 UTC: `263 passed, 1 failed`. The failure is `G.2`, as written down before the run. `P.22` passed by a margin of 66 ms: Squid read its files at `.82` of the second in which the fetch window command wrote the window file, at `.75`. Whole seconds would have compared equal.

### Limits

- `G.3` and `G.4` assume no job runs during a check run. With dispatch, a check run can meet a job.
- `P.22` trusts Squid's journal and the files' change times, which root on the edge can change.
- The diagram change needs a look before it merges.

## The measured day and the daily cap

Date: 2026-10-19. One day of log volume and of the log agent's footprint, the cap set from that day, and `daily-cap` fired once on purpose ([ADR 0028](../decisions/0028-alert-rules-flow-logs-and-drills.md)).

### What changed

| Change | Where |
| --- | --- |
| The workspace's daily cap is 0.21 GB, three times the measured day. It was 1 GB | `infra/platform/variables.tf` |
| Steps 14 to 17: read the day, read the footprint, drill the cap, set it | [Monitoring runbook](../runbooks/monitoring.md#daily-cap) |

### The day

From 2026-10-18 10:00 to 2026-10-19 10:00 UTC, read from `Usage` with the operator's sign-in at 13:55 UTC. Nothing changed on the VMs in the window. The Activity Log holds only the checks' reads of effective security rules and two `sharedKeys` calls at 14:08 on 2026-10-18, from the operator and the platform identity. One run of the checks fell in the window, at 19:03.

| Table | MB |
| --- | --- |
| `AisecWorkerJournal_CL` | 42.66 |
| `Perf` | 24.09 |
| `Syslog` | 0.29 |
| `AisecSquidAccess_CL` | 0.02 |
| `AisecToolAudit_CL` | 0.004 |
| Billable, in all | 67.06 |

Each hour took between 2.56 and 3.87 MB. The worker's journal is two thirds of the day. About a third of `Perf` is the orchestrator's container mounts: 16 of its 31 disk instances are container root and shared memory mounts, each one row a minute. `Heartbeat` (2.31 MB) and the traffic analytics tables (1.80 MB) are not billable and not under the cap.

The same query over a day before the workspace existed returns 0, so an empty window cannot pass for a small day. Three times 67.06 MB is 201 MB, and the cap is 0.21 GB.

### Footprint

The log agent's six systemd units on each VM, read at 13:53 UTC over SSH: `azuremonitoragent`, `azuremonitor-coreagent`, `azuremonitor-agentlauncher`, `azuremonitor-astextension`, `metrics-extension`, and `metrics-sourcer`. Each started between 2026-10-17 23:32 and 2026-10-18 08:55, before the day, so its counters cover the day and up to 14 hours more. CPU is the units' CPU time over their run time. The peak column adds up each unit's own highest value, so it overstates any one moment.

| VM | CPU, of one core | Memory | Peaks, added up | Share of the VM's memory |
| --- | --- | --- | --- | --- |
| Orchestrator | 0.42 % | 290 MiB | 297 MiB | 4 % |
| Edge | 0.55 % | 253 MiB | 257 MiB | 7 % |
| Router | 0.51 % | 223 MiB | 318 MiB | 27 %, 38 % at the peaks |

The worker has no agent. Across the day, from `Perf`, the whole machine's CPU averaged 2.6 % on the orchestrator, 1.2 % on the edge, and 1.2 % on the router, with a highest minute of 10 %, 5.9 %, and 14.2 %. The least memory available in any minute: 6,399 MB on the orchestrator, 2,935 MB on the edge, and 339 MB of 836 MB on the router.

The reading on 2026-10-17, nine minutes after the install, was 199 MB on the orchestrator with `ps` ([footprint](#footprint)). The agent settles near 290 MiB.

### The drill

Written down before the apply: the workspace has taken 55.8 MB since its reset hour, 17:00 UTC, so a cap of 0.023 GB is already passed. Expected: a `_LogOperation` row in `Ingestion` with `OverQuota`, then `daily-cap`. Already seen as the fail side: no such row in the 31 days before.

| Time, UTC | Event |
| --- | --- |
| 14:05:09 | The cap goes from 1 to 0.023 GB, from a saved plan with `-var log_daily_cap_gb=0.023` that changes nothing else |
| 14:14:59 | `_LogOperation`: `Ingestion`, `Warning`, status `OverQuota`. The workspace reads `OverQuota` at 14:15:41 |
| 14:21:18 | `daily-cap` fires, Sev1: 6 minutes after the row, 16 after the apply |
| 14:22:43 | The cap goes from 0.023 to 0.21 GB, from a second saved plan. `Ingestion`, `Info`: collection started because the quota increased |
| 14:22:56 | `Warning`, `OverQuota` again |
| 14:27:27 to 14:57:34 | Eight more starts and eight more stops. Each start gives the reason as a new day and a daily limit reset |
| 14:34:00 | `journal-missing` fires, Sev2. The last journal row is from 14:10:58 |
| 15:06:20 | A last start, with no stop after it |
| 15:30:01 | `journal-missing` resolves. The first journal row after the gap is from 15:10:58 |
| 15:52:29 | `daily-cap` resolves |

The day held 53 MB through all of it, a quarter of the new cap, so the stops after 14:22 are not the cap being reached. No stop followed the start at 15:06:20, read at 16:18.

What the drill showed:

- **Rows sent while the cap holds are lost, not delayed.** The edge's agent logged `196 uploaded rows, 0 dropped` every minute through the stop, with no retries. The service took them and kept nothing. The VMs keep their own journals and log files. `Perf` has no copy anywhere else.
- **Raising the cap brought ingestion back 44 minutes later, not at once.** In between it stopped nine more times. Little landed before 15:10: a few `Perf` rows from 14:40. `Perf` has every minute again from about 15:20. The workspace has no rows from about 14:15 to 15:10 ([troubleshooting 10](../troubleshooting/10-raising-the-daily-cap-leaves-ingestion-flapping.md)).
- **Heartbeats keep arriving under the cap.** `Heartbeat` is not billable, so `heartbeat-missing` stays quiet during a cap stop. `journal-missing` does fire, and `daily-cap` is the alert that names the cause.

### Checks

Written down before the run: every check passes except `G.2`, which fails on the worker's old fixture ([What `G.2` found](#what-g2-found)). The checks that read recent rows pass, because rows arrive again from 15:10 and the traffic analytics tables are not under the cap.

`validation/platform-checks.sh` from the branch, 16:20 to 16:25 UTC: `263 passed, 1 failed`. The failure is `G.2`.

### Limits

- **One day, with no job in it.** The agent and the model server ran no investigation. The first jobs add pod logs and the model server's output to the worker's journal, and the cap has to be read again then ([#125](https://github.com/sindredg/ai-security-platform/issues/125)).
- **A cap stop cost about an hour of rows,** with the cap raised as soon as the alert fired. Raising it is not an instant way back ([T41](../security/threat-model.md)).
- **The footprint counters cover the units' whole run.** They include up to 14 hours outside the day. `MemoryPeak` is the highest since the unit started, which covers the day.
- **The login message asks Squid for `changelogs.ubuntu.com`.** The SSH login for the footprint reading at 13:53 raised `squid-refused-orchestrator`, Sev1, at 13:57. Ubuntu Pro's apt hook raised it at 02:22 the same night, for `esm.ubuntu.com` ([#124](https://github.com/sindredg/ai-security-platform/issues/124)).
