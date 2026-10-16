# Decision records

One record per consequential architecture choice. A record states the context, the options considered, the decision, and its trade-offs. A decision that changes gets a new record, and the old one is marked superseded. When a later record changes one part of an earlier one, the earlier record keeps its text and gets a sentence that points to the later one.

| Record | Decision | Status |
| --- | --- | --- |
| [0001](0001-k3s-for-initial-orchestration.md) | K3s on one VM for initial orchestration | Accepted |
| [0002](0002-separate-platform-and-target-infrastructure.md) | Separate platform and target infrastructure | Accepted |
| [0003](0003-region-pair.md) | Sweden Central for the platform, Denmark East for targets | Accepted |
| [0004](0004-netbox-as-first-target.md) | NetBox as the first target, three ordered exercises | Accepted |
| [0005](0005-ai-workers-on-a-separate-vm.md) | AI workers on a separate VM outside the cluster | Accepted |
| [0006](0006-terraform-state-in-azure-storage.md) | Terraform state in Azure Storage, one account per root | Accepted |
| [0007](0007-mesh-vpn-for-administrative-access.md) | Mesh VPN for administrative access | Accepted |
| [0008](0008-deployment-identities-and-bootstrap-scope.md) | Certificate-based deployment identities, created by the bootstrap root | Accepted |
| [0009](0009-one-egress-point-on-the-orchestrator-subnet.md) | One egress point, on the orchestrator subnet | Accepted |
| [0010](0010-threat-model-and-security-checks-per-milestone.md) | A threat model, with security checks tied to milestone gates | Accepted |
| [0011](0011-package-proxy-for-the-worker.md) | A package proxy for the worker, on the orchestrator | Accepted |
| [0012](0012-dispatch-over-ssh-with-a-forced-command.md) | Dispatch to the worker over SSH, with a forced command | Accepted |
| [0013](0013-a-token-per-job-and-no-cloud-identity-yet.md) | A token per job for tool calls, and no cloud identity for workloads yet | Accepted |
| [0014](0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) | A small custom tool service, and an audit log on the orchestrator | Accepted |
| [0015](0015-build-the-model-file-on-the-worker.md) | Build the model file on the worker, from the publisher's weights | Accepted |
| [0016](0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md) | A pinned certificate, an offline caller check, and a line limit for the tool service. Replaces the private authority in 0013 | Accepted |
| [0017](0017-no-udp-from-the-orchestrator.md) | No UDP from the orchestrator to the internet. Replaces the mesh agent's UDP rules in 0009 | Accepted |
| [0018](0018-a-host-rule-keeps-pods-off-the-internet.md) | A host rule keeps pods off the internet, including the seconds before a pod's network policy is written. Adds to 0014 | Accepted |
| [0019](0019-how-the-audit-lines-and-the-worker-journal-are-copied.md) | How the audit lines and the worker's journal are copied: a follower and a pull, each as its own user, into capped append-only files, with a sequence in every audit line. Adds to 0014 | Accepted |
| [0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md) | An edge VM in Denmark East for the way out, the mesh VPN node, and the package proxy, with a fetch window for upload hosts. The targets move to Poland Central. Replaces parts of 0003, 0007, 0009, and 0011 | Accepted |
| [0021](0021-monitoring-in-azure-monitor-over-private-link.md) | Monitoring in Azure Monitor: an agent on the orchestrator, the edge, and the router over Private Link, none on the worker, and alert rules shown in the portal without notifications. Adds to 0019 | Accepted |
| [0022](0022-short-lived-ssh-certificates-for-the-operator.md) | Short-lived SSH certificates for the operator, signed by an OpenSSH certificate authority the operator keeps, and a tunnel to the Kubernetes API for that account only | Accepted |
| [0023](0023-the-host-rule-limits-what-pods-reach-on-the-host.md) | The host rule also limits what pods reach on the host: the API server and the kubelet, nothing else. Adds to 0018 | Accepted |
| [0024](0024-the-targets-in-their-own-repository-and-signed-commits.md) | The targets in their own public repository, where the broker writes, and commits to the platform repository signed by the operator's key, checked in the pipeline. Extends 0002 | Accepted |
| [0025](0025-the-mesh-node-on-its-own-vm.md) | The mesh node on its own router VM, which no subnet can reach, with the agent's updates and log upload off. Replaces the mesh node in 0020 | Accepted |

## Format

```text
# NNNN. Title

Status: Proposed | Accepted | Superseded by NNNN
Date: YYYY-MM-DD

## Context
## Options
## Decision
## Trade-offs
```
