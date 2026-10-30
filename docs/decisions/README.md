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
| [0024](0024-the-targets-in-their-own-repository-and-signed-commits.md) | The targets in their own public repository, and commits to the platform repository signed by the operator's key, checked in the pipeline. Extends 0002. Its broker was never made: see 0045 | Accepted |
| [0025](0025-the-mesh-node-on-its-own-vm.md) | The mesh node on its own router VM, which no subnet can reach, with the agent's updates and log upload off. Replaces the mesh node in 0020 | Accepted |
| [0026](0026-the-feed-key-gets-its-own-account-on-the-worker.md) | The feed key logs in to an account of its own on the worker, with no sudo and a command that only unpacks the staged files. The scripts come from the operator. Changes two parts of 0022 | Accepted |
| [0027](0027-how-the-monitoring-is-built.md) | How the monitoring is built: a collection endpoint in each region with an agent, the login facilities from info, and hosts entries written through the VM agent. Changes three parts of 0021 | Accepted |
| [0028](0028-alert-rules-flow-logs-and-drills.md) | Alert rules that fire once and resolve, flow logs written by the bootstrap root as the operator, Activity Log rules where no deployment identity reaches, and a drill file for firing the audit alerts on purpose. Adds to 0021 and 0027 | Accepted |
| [0029](0029-argo-workflows-in-its-own-namespace-and-the-ui-on-the-operators-machine.md) | Argo Workflows: the controller in its own namespace, managing `orchestration` only, images pinned by digest after a signature check, and the UI run by the operator on the workstation | Accepted |
| [0030](0030-how-a-job-reaches-the-worker.md) | How a job reaches the worker: one host rule exception for the worker's SSH port, a dispatch image of its own, and a socket on the worker that starts the job's sandboxed unit. Changes three parts of 0012, adds to 0018 | Accepted |
| [0031](0031-qwen3-5-4b-stays-the-workers-model.md) | Qwen3.5-4B stays the worker's model, by a rule written before it was compared with Granite 4.2 3B and Qwen3.5-2B | Accepted |
| [0032](0032-erase-the-slot-before-each-job-and-refuse-on-failure.md) | The model server's slot is erased before each job as well as after, a job is refused when the first erase fails, and a failed second erase fails its workflow. Changes step 4 of 0030 | Accepted |
| [0033](0033-k3s-system-images-from-the-release-archive.md) | K3s's system images come from the release's archive, pinned by checksum, and Docker Hub leaves the edge's list | Accepted |
| [0034](0034-no-model-gateway-while-there-is-one-backend.md) | No model gateway while there is one model backend | Accepted |
| [0035](0035-netbox-from-its-image-with-the-database-from-ubuntu.md) | NetBox from its image under Podman, pinned by digest, with PostgreSQL and Valkey from Ubuntu | Accepted |
| [0036](0036-target-packages-through-a-port-the-orchestrator-forwards.md) | The targets get packages through a port the orchestrator forwards over SSH, to a Squid port that serves only the package mirror | Accepted |
| [0037](0037-an-unscoped-copy-of-the-consumers-permission.md) | The seeded finding is an unscoped copy of the consumer's permission, confirmed by configuration and by what the token returns. The contract is a file in the targets repository | Accepted |
| [0038](0038-netboxs-tls-key-made-on-the-netbox-vm.md) | NetBox's TLS key is made on the NetBox VM and served by Granian. The orchestrator and the consumer pin the certificate | Accepted |
| [0039](0039-netbox-takes-a-clients-address-from-the-connection.md) | NetBox takes a client's address from the connection and never from a header, on an IPv4 socket, so that a token's address limit holds | Accepted |
| [0040](0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md) | A job's evidence is collected on the hosts, on request, and stored per job in the tool service, which hands the model only the fields its schema names | Accepted |
| [0041](0041-the-workflow-compares-the-models-verdict-with-the-checks.md) | The workflow compares a NetBox job's verdict per account with the deterministic checks, and a failed step stops it on anything but a match | Accepted |
| [0042](0042-held-out-cases-and-the-baseline-without-the-agent.md) | The investigation is scored on held-out variants of the consumer contract against the same seed, by rules written before the runs, beside the same run without the agent | Accepted |
| [0043](0043-proposals-are-remove-only-and-a-policy-check-decides.md) | A fix is proposed in the same answer as the verdicts, removes one permission from one account, and a policy check on the orchestrator host decides | Accepted |
| [0044](0044-the-rehearsal-copy-is-a-second-netbox-on-the-lab-vm.md) | The rehearsal copy is a second NetBox on the lab VM, with its own interface in the rehearsal subnet, reset from a dump before each rehearsal | Accepted |
| [0045](0045-the-operator-publishes-a-checked-proposal.md) | No repository credential on the platform: it prepares a proposal of checked fields, and the operator's machine commits and opens it | Accepted |
| [0046](0046-a-signed-tag-approves-and-delivery-checks-before-the-merge.md) | A tag signed with a separate approval key approves one commit once, delivery checks the target after applying it, and the merge comes last | Accepted |
| [0047](0047-a-delivery-token-for-each-delivery.md) | Each delivery gets its own token, made on the NetBox VM and piped into the delivery, and none is kept on the orchestrator | Accepted |
| [0048](0048-the-workflows-steps-are-inline-so-no-workflow-runs-one-alone.md) | The workflow's dispatch and comparison are inline steps, so a workflow can name neither as its entrypoint and run it alone | Accepted |
| [0049](0049-a-netbox-jobs-answer-is-a-final-output-checked-against-a-schema.md) | A NetBox job answers through Goose's final output, checked against a schema, and the job program writes the lines the comparison reads | Accepted |
| [0050](0050-a-guarded-change-merges-only-with-an-approval-on-its-head.md) | A pull request that changes NetBox's seed or the approvers merges only with an approval tag on its head commit, checked from the default branch | Accepted |
| [0051](0051-a-netbox-jobs-schema-names-each-account-of-the-job.md) | A NetBox job's schema requires a verdict under the name of each of the job's accounts, which the dispatch step reads from the checks' verdicts and names in the job line. Changes the schema of 0049 and the job line of 0030 | Accepted |
| [0052](0052-a-smaller-prompt-batch-so-a-cancel-reaches-the-model-server-in-time.md) | The model server's prompt batch is 512 tokens, so a cancel reaches it inside the job program's erase wait, and the waits stay | Accepted |
| [0053](0053-a-fix-is-proposed-once-until-it-is-delivered.md) | A fix an earlier allowed and rehearsed bundle holds is refused until that bundle's delivery passed, and the operator's machine reads the open pull requests before publishing | Proposed |

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
