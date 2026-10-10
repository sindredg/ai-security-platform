# 0005. AI workers on a separate VM outside the cluster

Status: Accepted
Date: 2026-10-10

## Context

AI workers read advisories, target evidence, and tool results. All of it is untrusted, and any of it can carry instructions. The safe assumption is that a worker will eventually be turned by something it reads.

When that happens, it must not find delivery credentials, workflow definitions, other jobs' evidence, or a route to the target. The orchestrator holds exactly those things.

Namespaces, pod security settings, and network policies help inside one cluster. But they share a kernel and a node with everything else, and this project does not treat them as a wall against malicious code.

There is a practical reason too. Inference is the biggest CPU and memory consumer in the system. On a shared 2-vCPU node it would fight the Kubernetes control plane for both.

## Options

| Option | Boundary | Cost |
| --- | --- | --- |
| Worker pods on the K3s server node | Shared kernel and node with trusted services | No extra VM. Inference competes with the control plane |
| Worker VM joined as a K3s agent node | Separate kernel, but the node holds kubelet credentials and sits on the cluster network | Simple dispatch. A compromised node has a foothold in the cluster |
| Sandboxed container runtime on the server node | Stronger than plain pods | Another runtime to operate. Still shares the node's capacity |
| Separate VM, not a cluster member | Separate kernel, network interface, and credentials. No cluster identity | Argo cannot schedule onto it. Dispatch has to be built or found |

## Decision

Run the agent runtime and the model server on a separate VM that is not a Kubernetes node.

- The worker VM has no cluster credentials and no privileged cloud identity.
- Network rules let it reach the tool services on the orchestrator and nothing else.
- Jobs arrive through a narrow, authenticated dispatch interface that carries a job scope and returns a schema-checked result.
- One job at a time, one loaded model.

## Trade-offs

- **Dispatch is the price.** Argo runs pods, not remote processes. The mechanism has to be a maintained integration or a small adapter with defined authentication, cancellation, and cleanup. It is the first thing the toolchain milestone has to prove.
- **Jobs are separated less well than worker and platform are.** Consecutive jobs share the VM. Session, cache, and workspace cleanup between them has to be tested, not assumed.
- **It takes half the region's compute.** Orchestrator and worker get 2 vCPUs each. There is no room for a second worker.
- **A VM boundary is not confidential computing.** The provider and the platform administrator are still trusted.
