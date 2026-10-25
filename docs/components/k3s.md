# K3s

The cluster on the orchestrator. One server, no agents. It runs the tool service, the Argo controller, and the pods of each workflow.

| | |
| --- | --- |
| State | Built. The tool service runs in `tool-services`, the Argo controller in `argo`, and the workflows in `orchestration`, since 2026-10-21. Verified by the [`K` checks](../validation/cluster.md), which passed in the run on 2026-10-24 from 07:12 to 07:18 UTC ([last run](../validation/README.md#last-run)) |
| Version | `v1.36.5+k3s1`, the release the project's `stable` channel points at |
| Pinned in | `infra/platform/variables.tf`: the version, and the SHA-256 of the binary, the install script, and the archive of the system images. `infra/platform/k3s-images.txt`: the digest of each system image in that archive ([ADR 0033](../decisions/0033-k3s-system-images-from-the-release-archive.md)) |
| Datastore | SQLite behind `kine`. No etcd |
| Configuration | `/etc/rancher/k3s/config.yaml`, from cloud-init |
| Decision | [0001](../decisions/0001-k3s-for-initial-orchestration.md) |

## Configuration that matters

| Setting | Why |
| --- | --- |
| `secrets-encryption: true` | Secrets in the datastore are encrypted |
| `protect-kernel-defaults: true` | The kubelet refuses to start if the kernel settings it relies on are wrong |
| Audit log at metadata level | Who called what, without payloads. 30 days, 10 files of 100 MB |
| `traefik` and `servicelb` disabled | No ingress and no load balancer until something needs one |
| `write-kubeconfig-mode: "0600"` | The administrator kubeconfig is root only |
| `kube-proxy-arg: nodeport-addresses=` the private address | Node ports answer on the private address only, not on loopback. `T.6` checked it on the mesh address until the orchestrator left the mesh |
| Default service accounts mount no token | Applied after install, per namespace |
| Certificate files at `600` | Applied after install. K3s keeps the mode |
| `admission-control-config-file`, pod security defaults | A namespace without a label enforces `restricted`. No namespace is exempt. Checked by `K.9` |
| `kube-system` labelled `enforce=baseline` | Its pods pass `baseline` and not `restricted`. Applied after install. Checked by `K.9` and `K.10` |
| `CONTAINERD_HTTPS_PROXY` in `k3s.service.env` | containerd pulls images through Squid on the edge. K3s and the kubelet get no proxy. A pull works only while a fetch window is open. Checked by `U.11` |

The installer is not piped from the network into a shell. The script is fetched at the release tag and checked against its pinned checksum first, and so is the binary. So is the archive of the system images, which K3s imports when it starts, so that containerd pulls none of them by tag. `K.11` compares the images K3s holds with the list of digests.

## Namespaces

`tool-services` and `orchestration` exist. Both enforce the restricted pod security level by label and deny traffic by default ([tool service checks](../validation/tool-service.md)). `orchestration` holds the workflows, the `investigate` template, and the accounts of the dispatch step, the executor, and the operator. Argo's controller runs in `argo` since 2026-10-21 ([worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows)). `collection` and `change` are planned. Monitoring runs in Azure Monitor, not in the cluster, from [milestone 3a](../roadmap.md#3a-edge-network-and-monitoring). What runs in the two, and what reaches them, is in the [tool service diagram](../security/tool-service.md#deployment-controls).

| Namespace | Workloads | Responsibility |
| --- | --- | --- |
| `argo` | The Argo Workflows controller, which manages `orchestration` only ([ADR 0029](../decisions/0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md)). The UI runs on the operator's machine | Scheduling, retries, one job at a time |
| `orchestration` | Workflows from fixed templates: the dispatch step and its exit handler | Register a job, hand it to the worker, check the result, revoke the token |
| `collection` | Collectors and deterministic checks. Not created: NetBox's collector runs on the hosts, and where a collector runs for a job is an [open decision](../architecture.md#open-decisions) | Read approved sources, correlate advisories locally |
| `tool-services` | Narrow MCP servers and the policy check | Check caller, job, target, operation, and arguments on every call |
| `change` | PR broker and delivery runner | Publish permitted patches, apply approved changes |

Namespaces organize workloads. They are not a security boundary against malicious code, and nothing here relies on them as one.

## Benchmark

kube-bench 0.16.0 with the `k3s-cis-1.9` profile, on 2026-10-19: 64 pass, 2 fail, 50 warn, 14 info. One fail asks for an etcd flag, and there is no etcd. The other, 5.1.6, is not explained: the check's own audit finds every pod compliant or exempt ([#127](https://github.com/sindredg/ai-security-platform/issues/127)). Details are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#benchmarks).

The first run, on 2026-10-11, on the orchestrator that was replaced on 2026-10-13, gave 65 pass and 1 fail ([milestone 2 worklog](../worklogs/0002-platform-compute.md#kubernetes-benchmark)). The `K` checks, which hold the fixes in place, pass on the current one.

## Validation

`K` in the [validation pages](../validation/cluster.md).

## Limits

- **One server.** The cluster is down while the VM is.
- **The pin moves by hand.** Nothing proposes a new K3s release.
- **The archive of system images is trusted as the release ships it.** K3s publishes no signature or provenance for it, as for the binary ([supply chain](../security/supply-chain.md)).
- **No datastore backup.** Nothing worth restoring is in it yet.
- **The benchmark profile is older than the cluster.** It was written for K3s 1.27 to 1.29.
- **The audit log stays on the machine it audits.**

## Official documentation

- [K3s documentation](https://docs.k3s.io/)
- [CIS hardening guide](https://docs.k3s.io/security/hardening-guide)
- [Secrets encryption](https://docs.k3s.io/security/secrets-encryption)
- [The `k3s token` command](https://docs.k3s.io/cli/token)
- [Cluster datastore](https://docs.k3s.io/datastore)
- [kube-bench](https://github.com/aquasecurity/kube-bench)
