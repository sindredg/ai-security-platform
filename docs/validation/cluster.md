# Cluster

K3s on the orchestrator, one server. The tool service is its one workload, checked on [its own page](tool-service.md). The design is [ADR 0001](../decisions/0001-k3s-for-initial-orchestration.md). These checks hold the benchmark fixes in place and prove the cluster came back after a restart.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `K.1` | `k3s` is active | Nothing else runs without it | `systemctl is-active` |
| `K.2` | The node is `Ready` | Gate: K3s comes back healthy after a restart | `kubectl get nodes` |
| `K.3` | Every pod is `Running` | The system pods are the cluster's own health | `kubectl get pods -A` |
| `K.4` | Secrets encryption is enabled | Secrets in the datastore are not plain text | `k3s secrets-encrypt status` |
| `K.5` | Every certificate file is `600` | kube-bench check 1.1.20. K3s keeps the mode across restarts, and this proves it still does | `stat` on `server/tls/*.crt` |
| `K.6` | No default service account mounts a token | kube-bench check 5.1.5. A pod that names no service account gets no API credential | `automountServiceAccountToken` is `false` in every namespace |
| `K.7` | The API server refuses anonymous requests | An unauthenticated caller gets nothing | The API server's own start line |
| `K.8` | The kubelet refuses anonymous requests | Every pod reaches the kubelet's port ([ADR 0023](../decisions/0023-the-host-rule-limits-what-pods-reach-on-the-host.md)). Only authentication stands between a pod and the node's containers | The kubelet's running configuration from its `configz` endpoint: anonymous access `false`, authorization `Webhook`. Read from the kubelet, not from a file, so a later file in its configuration folder cannot change it unseen |
| `K.9` | Every namespace refuses a privileged pod | A namespace without a label, `default` or one added later, used to admit a pod that mounts the host. A cluster-wide default closes it ([#70](https://github.com/sindredg/ai-security-platform/issues/70)) | A privileged pod that mounts `/`, sent to every namespace as a server-side dry run. Each namespace has to refuse it for pod security. Admission runs and nothing is stored |
| `K.10` | Every system deployment is ready | `kube-system` enforces `baseline`. A system pod that a K3s release changes to need more is refused, never created, and `K.3` does not see it | Ready replicas against replicas, for each deployment in `kube-system` |

## Limits of these checks

- `K.6` is a patch on existing namespaces. A namespace created later starts without it, and the check then fails. That is the point of the check.
- `K.3` can fail for a minute after a restart while a pod is still starting.
- `K.9` covers the namespaces that exist when it runs. The default level is what holds a namespace created later.
- The benchmark itself is not run here. kube-bench with the `k3s-cis-1.9` profile is step 16 of the [runbook](../runbooks/platform-compute.md).
