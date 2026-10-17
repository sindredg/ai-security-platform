# K3s

The cluster on the orchestrator. One server, no agents. The tool service is the one workload.

| | |
| --- | --- |
| State | Built. The tool service runs in `tool-services` |
| Version | `v1.36.5+k3s1`, the release the project's `stable` channel points at |
| Pinned in | `infra/platform/variables.tf`: the version, the binary's SHA-256, and the install script's SHA-256 |
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

The installer is not piped from the network into a shell. The script is fetched at the release tag and checked against its pinned checksum first, and so is the binary.

## Namespaces

`tool-services` and `orchestration` exist. Both enforce the restricted pod security level by label and deny traffic by default ([tool service checks](../validation/tool-service.md)). `orchestration` holds only the `dispatch` service account so far: Argo Workflows is not installed. `collection` and `change` are planned. Monitoring runs in Azure Monitor, not in the cluster, from [milestone 3a](../roadmap.md#3a-edge-network-and-monitoring). What runs in the two, and what reaches them, is in the [tool service diagram](../security/tool-service.md#deployment-controls).

| Namespace | Workloads | Responsibility |
| --- | --- | --- |
| `orchestration` | Argo Workflows controller and server, fixed workflow templates | Scheduling, retries, concurrency limits, operator UI |
| `collection` | Collectors and deterministic checks | Read approved sources, correlate advisories locally |
| `tool-services` | Narrow MCP servers and the policy check | Check caller, job, target, operation, and arguments on every call |
| `change` | PR broker and delivery runner | Publish permitted patches, apply approved changes |

Namespaces organize workloads. They are not a security boundary against malicious code, and nothing here relies on them as one.

## Benchmark

kube-bench 0.16.0 with the `k3s-cis-1.9` profile: 65 pass, 1 fail, 50 warn, 14 info. The one fail asks for an etcd flag, and there is no etcd. Details are in the [milestone 2 worklog](../worklogs/0002-platform-compute.md#kubernetes-benchmark).

That run was on 2026-10-11, on the orchestrator that was replaced on 2026-10-13. It has not been repeated on the new one. The `K` checks, which hold the fixes in place, passed there.

## Validation

`K` in the [validation pages](../validation/cluster.md).

## Limits

- **One server.** The cluster is down while the VM is.
- **The pin moves by hand.** Nothing proposes a new K3s release.
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
