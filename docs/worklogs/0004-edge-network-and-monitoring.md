# 0004. Edge network and monitoring

Date: 2026-10-16, in progress
Milestone: 3a, edge network and monitoring

## Summary

The milestone is built in slices. The first, orchestrator hardening, is on the system: pods reach the host only on the API server and kubelet ports, and every namespace refuses a privileged pod. The rate limit for the tool service is written and tested in the pipeline, not deployed. The edge, the router, SSH certificates, the targets' move, and monitoring are not built. The gate is not met.

| Criterion | Result |
| --- | --- |
| The orchestrator reaches the internet only through the edge proxy, and only the hosts on its list | Open |
| Only the edge resolves public names | Open |
| The orchestrator is not on the mesh VPN | Open |
| The mesh agent runs only on the router, with its own updates and its log upload off | Open |
| A check fails when the mesh agent is behind the current stable release | **Tested** with `U.7`: passes on the live orchestrator at 1.104.1, and fails locally on an older version and on no answer from the package site ([fail side](#the-fail-side-of-each-new-check)) |
| The router cannot open a connection to an operator device | Open |
| The Kubernetes API is not reachable over the mesh VPN | Open |
| Operator SSH logins use certificates that expire within a day | Open |
| A pod reaches the host only on the ports the host rule lists, from its first packet | **Tested** on the live system: a new pod reached SSH before the change and timed out after it, while 6443 and 10250 stayed open, and `E.8` passes ([rollout](#rollout)). The rule loads before K3s, so it holds from the first packet. That ordering is read from the unit, not observed on a boot |
| Every namespace rejects a privileged pod, whether or not it has a pod security label | **Tested** on the live system: `K.9` failed on `default`, `kube-node-lease`, `kube-public`, and `kube-system` before the change and passes after it ([rollout](#rollout)) |
| Requests to the tool service without a valid token are rate-limited | **Tested** in the service's own tests, locally. Not deployed: the image is built from `main` after merge ([the rate limit](#the-rate-limit)) |
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

Not tested on the live system. The image is built and pushed only from `main`. After merge, a change moves the manifest's digest and the tool service is deployed again with `deploy.sh`.

### Version moves

Read from the official sources on 2026-10-16. The Terraform checksum is from the release's `SHA256SUMS`, whose signature checked against HashiCorp's key `C874 011F 0AB4 0511 0D02 1055 3436 5D94 72D7 468F`. Each image digest is the multi-platform index of the release tag, the same kind as the pins it replaces.

| Tool | From | To |
| --- | --- | --- |
| Terraform | 1.16.5 | 1.16.6 |
| `hashicorp/azurerm` | 5.9.0 | 5.10.0, lock files with hashes for `linux_amd64` and `linux_arm64` |
| Checkov | 3.3.27 | 3.3.29 |
| Trivy | 0.75.0 | 0.76.0 ([#56](https://github.com/sindredg/ai-security-platform/issues/56)) |
| Ruff | 0.17.0 | 0.17.1 |

`terraform validate` passes for all three roots with Terraform 1.16.6 and the read-only lock files, run locally on a copy of the tracked files. No plan has run against the live state with the new versions.

The pipeline passed with every new version on the pull request. Each Trivy step, read from the job logs of the last `main` run with 0.75.0 and the pull request's run with 0.76.0:

| Step | 0.75.0 | 0.76.0 |
| --- | --- | --- |
| Configuration: Terraform, manifests, Dockerfile | No finding in any file. Six suppressed findings on the state storage accounts | The same, in another order |
| Dependency scan | 8 advisories on the converter's packages, report only. None on the tool service's | The same 8 advisory IDs |
| Image scan | 0 in the Alpine packages and in each of 55 Python packages | The same |

### Limits

- First boot from the template with these changes has not run. The running orchestrator got them by hand, through the runbook's steps.
- The `input` chain cannot tell one pod from another. Every pod still reaches the API server and the kubelet, and both rely on authentication.
- `K.9` covers the namespaces that exist when it runs. The default level is what holds a namespace created later.
- The rate limit is shared by every caller and counts nothing per caller. How many requests were refused past the limit in a minute is not recorded.
