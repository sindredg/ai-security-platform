# 0005. AI workers on a separate VM outside the cluster

Status: Accepted
Date: 2026-10-10

## Context

AI workers process untrusted input: advisories, target evidence, and tool results. The design assumes a worker can be compromised through that input. A compromised worker must not reach delivery credentials, workflow definitions, other jobs' evidence, or the target network.

The orchestrator holds exactly those things. Namespaces, pod security settings, and network policies reduce exposure inside one cluster, but they share a kernel and a node, and the project does not treat them as a boundary against malicious code.

Model inference is also the largest CPU and memory consumer. On a shared 2-vCPU node it would compete with the Kubernetes control plane.

## Options

| Option | Boundary | Cost |
| --- | --- | --- |
| Worker pods on the K3s server node | Shared kernel and node with trusted services | No extra VM. Inference competes with the control plane |
| Worker VM joined as a K3s agent node | Separate kernel, but the node holds kubelet credentials and receives cluster networking | Simple dispatch. A compromised node has a foothold in the cluster |
| Sandboxed container runtime on the server node | Stronger than plain pods | Extra runtime to operate. Still shares the node's capacity |
| Separate VM, not a cluster member | Separate kernel, network interface, and credentials. No cluster identity | Argo cannot schedule onto it directly. A dispatch mechanism is needed |

## Decision

Run the agent runtime and the model server on a separate VM that is not a Kubernetes node.

- The worker VM has no cluster credentials and no privileged cloud identity.
- Network rules allow it to reach tool services on the orchestrator and nothing else.
- Jobs arrive through a narrow, authenticated dispatch interface that carries a job scope and returns a schema-checked result.
- One job runs at a time, with one loaded model.

## Trade-offs

- **Dispatch is custom integration risk.** Argo runs pods, not remote processes. The mechanism must be a maintained integration or a small bounded adapter with defined authentication, cancellation, and cleanup. This is the first thing the toolchain milestone proves.
- **Separation between jobs is weaker than between worker and platform.** Consecutive jobs share the VM. Session, cache, and workspace cleanup between jobs must be tested, not assumed.
- **It uses half the region's compute.** The orchestrator and the worker each get 2 vCPUs, with no room for a second worker.
- **A VM boundary is not confidential computing.** The provider and the platform administrator remain trusted.
