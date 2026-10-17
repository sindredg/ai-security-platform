# 0004. Edge network and monitoring

Date: 2026-10-16, in progress
Milestone: 3a, edge network and monitoring

## Summary

The milestone is built in slices. The first, orchestrator hardening, is on the system: pods reach the host only on the API server and kubelet ports, and every namespace refuses a privileged pod. The tool service limits requests without a valid token. The second is on the system too: the administrator account on both VMs takes only a certificate that expires within 12 hours, and the feed key logs in to an account of its own on the worker. The check that every commit in a pull request is signed by the operator's key is required, and on GitHub it blocks a pull request with a commit GitHub signed. The target network is in Poland Central, defined in its own repository. The edge, the router, and monitoring are not built. The gate is not met.

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
| The target network is in Poland Central, in its own repository. An unsigned commit fails a required check | **Tested** for the targets on the live system: `Z.14` reads `polandcentral`, after it read `denmarkeast` before the move, and the target root is in [its own repository](https://github.com/sindredg/ai-security-platform-test) ([the move](#the-targets-in-poland-central)). **Tested** for the signature check on GitHub: a pull request with a commit GitHub signed is blocked, also next to a passing job of the same name, and an unsigned push is refused ([fail side](#the-fail-side-on-github)) |
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

