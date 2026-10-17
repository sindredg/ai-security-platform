# 0004. Edge network and monitoring

Date: 2026-10-16, in progress
Milestone: 3a, edge network and monitoring

## Summary

The milestone is built in slices. The first, orchestrator hardening, is on the system: pods reach the host only on the API server and kubelet ports, and every namespace refuses a privileged pod. The tool service limits requests without a valid token. The second is on the system too: the administrator account on both VMs takes only a certificate that expires within 12 hours, and the feed key logs in to an account of its own on the worker. The edge, the router, the targets' move, and monitoring are not built. The gate is not met.

| Criterion | Result |
| --- | --- |
| The orchestrator reaches the internet only through the edge proxy, and only the hosts on its list | Open |
| Only the edge resolves public names | Open |
| The orchestrator is not on the mesh VPN | Open |
| The mesh agent runs only on the router, with its own updates and its log upload off | Open |
| A check fails when the mesh agent is behind the current stable release | **Tested** with `U.7`: passes on the live orchestrator at 1.104.1, and fails locally on an older version and on no answer from the package site ([fail side](#the-fail-side-of-each-new-check)) |
| The router cannot open a connection to an operator device | Open |
| The Kubernetes API is not reachable over the mesh VPN | Open |
| Operator SSH logins use certificates that expire within a day | **Tested** on the live system: a login with a 12-hour certificate works on both VMs, and the plain key, an expired certificate, one from another address, and one for another principal are refused, each with its reason in sshd's log ([slice (b)](#rollout-1)). `HO.17` to `HO.20` and `HW.17` to `HW.20` pass |
| A pod reaches the host only on the ports the host rule lists, from its first packet | **Tested** on the live system: a new pod reached SSH before the change and timed out after it, while 6443 and 10250 stayed open, and `E.8` passes ([rollout](#rollout)). The rule loads before K3s, so it holds from the first packet. That ordering is read from the unit, not observed on a boot |
| Every namespace rejects a privileged pod, whether or not it has a pod security label | **Tested** on the live system: `K.9` failed on `default`, `kube-node-lease`, `kube-public`, and `kube-system` before the change and passes after it ([rollout](#rollout)) |
| Requests to the tool service without a valid token are rate-limited | **Tested** on the live system: 33 requests without a token from the worker got 30 × 401 and 3 × 429, with 31 audit lines, one of them for the limit ([the rate limit](#on-the-live-system)) |
| The audit lines, the worker's journal, and the edge's and the router's logs reach a log store that no VM can delete from | Open |
| Alerts for a stopped agent, an audit gap, a missed pull, a refused request, and a security group or role change | Open |
| Flow logs are recorded for the platform subnets | Open |
| The target network is in Poland Central, in its own repository. An unsigned commit fails a required check | Open |
| Log volume per day is measured, and a daily cap is set from it | Open |
| The orchestrator's memory and CPU use with the log agent are measured | Open |

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

