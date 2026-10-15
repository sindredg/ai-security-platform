# Tool service

The tool service runs in K3s on the orchestrator and is the one place the worker can send a tool call. These checks test the deployment: the pod, its namespaces, its network paths, and its certificate. The service's own rejection cases are unit tests in the pipeline. The design is [ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) and [ADR 0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md). The controls are on the [tool service page](../security/tool-service.md#deployment-controls).

Status: **configured, not tested.** The checks are in `validation/platform-checks.sh`. The service is not deployed, so none has run against the system, and none has been run against a broken input. Every expected value below is reasoned from the manifests and the tools, not observed.

## On the orchestrator

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `T.1` | The tool service pod is ready | No service, no tool calls | The deployment's ready replicas is `1` |
| `T.2` | The pod runs the image its manifest names | The orchestrator runs what a reviewed commit names, not what the registry holds | The image digest of the running container equals the digest in `platform/tool-service/tool-service.yaml`. An empty digest in the manifest is a failure, not a match |
| `T.3` | The pod has no service account token, no root, and nothing writable | These limit what a bug in the parser gives an attacker | `automountServiceAccountToken`, `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation`, and the dropped capabilities, read from the running pod |
| `T.4` | Both namespaces enforce the restricted pod security level | A pod that asks for more is refused at admission | The `pod-security.kubernetes.io/enforce` label on `tool-services` and `orchestration` |
| `T.5` | Both namespaces deny by default | A pod with no policy of its own gets no traffic | A `default-deny` network policy exists in each |
| `T.6` | The tool port does not answer on the mesh address | Node ports are held to the private address. A mesh device has no business on the tool port | TCP to port 30443 on the orchestrator's mesh address is `refused`. Nothing listens there, and the mesh policy does not apply to a local address |
| `T.7` | The certificate has more than 14 days left | An expired certificate stops every job | `openssl x509 -checkend` on the certificate the pod mounts |
| `T.8` | The pod cannot reach the internet | The orchestrator's outbound access is not the pod's | A TCP connection from inside the pod to `1.1.1.1:443` is `refused`. K3s enforces network policies with kube-router, which rejects instead of dropping. Without the policy the connection is `open`, because the orchestrator reaches 443 (`E.1`). Any other end is a failure |

## From the worker

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `T.9` | The worker reaches the tool port | The path the job uses | TCP to the orchestrator on 30443 is `open` |
| `T.10` | The service refuses a call without a token | The service answers, and wants a token | An HTTPS request with the pinned certificate and the name in it returns 401 |
| `T.11` | The system's trust store does not trust the service | Only the pinned copy is trusted | The same request without the pinned certificate gets no HTTP answer (`000`) |
| `T.12` | The certificate does not cover the bare address | The name is the check | The request to the IP address, with the pinned certificate, gets no HTTP answer |
| `T.13` | The service refuses TLS 1.2 | It accepts TLS 1.3 only | The request with TLS 1.2 as the maximum gets no HTTP answer |

## Elsewhere

These check the same deployment and sit with their own groups:

- `E.5` on [containment](containment.md#the-orchestrators-side): the orchestrator sends no UDP to the internet.
- `Z.13` on [containment](containment.md#from-azures-side): the worker's rule for the tool port is what allows it.
- `M.5` on [access](access.md): the mesh policy drops the tool port.

## Not checked

- **The round trip.** Registering a job, calling a tool with its token, and the refusal after revocation are steps in the deployment procedure, not checks in the script.
- **The audit log.** The service prints audit lines. Nothing stores them yet.
