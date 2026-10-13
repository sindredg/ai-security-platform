# 0013. A token per job for tool calls, and no cloud identity for workloads yet

Status: Accepted
Date: 2026-10-11
Amended: 2026-10-13. One pinned server certificate replaces the private authority, registration carries the token's digest, and the caller's service account token is checked offline. The reasons are in the decision below.

## Context

Two identity questions were open before milestone 3, and they are different questions.

**Which job is calling?** Every tool call from the worker arrives from the same address. The tool service has to refuse a call for another job or another target ([T18](../security/threat-model.md)), so something in the call has to say which job it belongs to, and the worker must not be able to make that up.

**How does a cluster workload reach Azure?** The architecture left this open, with the two obvious answers and what is wrong with each. Workload identity federation on a self-managed cluster needs publicly reachable OIDC issuer metadata and public signing keys. Those documents can be hosted separately from the cluster, as described in the [official setup guide](https://azure.github.io/azure-workload-identity/docs/installation/self-managed-clusters/oidc-issuer.html); this project has not chosen a hosting arrangement. A VM managed identity needs nothing public, and is available to every process on the VM.

Milestone 3 runs on synthetic evidence. Nothing in it calls an Azure API.

## Options

For job identity:

| Option | What the worker holds | Notes |
| --- | --- | --- |
| A random token per job, sent as a bearer token over TLS | One secret that names one job | Simple to issue, check, and revoke. Whoever holds it is the job |
| A client certificate per job, from a small authority on the orchestrator | A key and a certificate | Stronger on the wire. An authority to run and protect, for a credential that lives minutes |
| A Kubernetes service account token | A cluster credential | The worker is not in the cluster, and 0005 exists to keep cluster credentials off it |
| The source address | Nothing | Every job shares one address |

For cloud access from the cluster:

| Option | Public endpoint | Scope of the credential | Notes |
| --- | --- | --- | --- |
| No cloud identity for any workload | None | None | Possible only while nothing needs Azure |
| VM managed identity on the orchestrator | None | Every process on the VM | One identity for collector, broker, and anything that lands there |
| Workload identity federation | Issuer metadata and public signing keys | One workload each | Needs a public endpoint for these documents, not a public IP on a cluster VM. Hosting is not decided |
| A stored service principal secret per workload | None | One workload each | A long-lived secret in the cluster, to rotate and to lose |

## Decision

**Job identity is a random token, issued per job and dead when the job ends.**

- **Issued by the dispatch step.** The step that opens the SSH session creates a 256-bit random token, registers its SHA-256 digest with the tool service together with the job's scope, and writes the token into the job document. Registration never carries the token itself. It exists in that step's memory, in the tool service as a SHA-256 digest, and on the worker for the length of the job.
- **Never a workflow parameter.** Argo stores parameters in the workflow object and shows them in its interface. The token is not one.
- **Scope is fixed at registration.** Job ID, target, the tools the job may call, and an expiry. The worker cannot widen it, because the tool service looks the scope up by the token and takes nothing about scope from the call.
- **Sent over TLS.** The tool service has one self-signed server certificate, made on the orchestrator. The worker gets a copy and trusts that certificate and no other, and checks the name. The first version of this record had a private authority sign it. An authority is a second key that can mint a certificate the worker would trust, kept to save one file copy per rotation. The agent runtime accepts a pinned certificate when it is not marked as an authority, so the authority is gone.
- **Revoked at the end.** The workflow's exit handler revokes by job ID, on success, failure, or cancel. The expiry catches a workflow that dies before its exit handler.
- **Registration is not reachable from the worker.** It has its own listener inside the cluster. A network policy admits the workflow's pods only, and the caller proves itself with its service account token. The tool service checks that token offline, against the public half of the cluster's signing key: signature, issuer, audience, expiry, and the one service account allowed to register. Asking the API server would be simpler, and it would give the pod a cluster credential and a path out, which [0014](0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) takes away.

**No workload gets a cloud identity in milestone 3.** The cluster holds no Azure credential of any kind. The mechanism is decided in its own record before milestone 4, when a collector first has to read something in Azure.

## Trade-offs

- **A bearer token is the job.** Anything on the worker that reads it can call tools as that job until it ends. The worker is assumed to be turned, so this is expected, and the scope is what limits the damage: one target, the listed tools, a few minutes.
- **The next job can find the last job's token.** They share a machine. By then the token is revoked, and the gate has to show that a revoked token is refused.
- **The dispatch step holds two things that matter:** the dispatch key and, briefly, the token. It is trusted code on the trusted machine. It is also the one place where a mistake leaks both.
- **A pinned certificate has to be copied to the worker at every rotation.** A new certificate that has not reached the worker stops every job. The copy goes in the rotation procedure, and the certificate in the credential inventory.
- **An offline check cannot see a deleted pod.** A service account token stays valid until it expires, even after its pod is gone. The dispatch step asks for a short-lived token with the tool service as its audience, so a stolen one is good for minutes and for one listener.
- **The public signing key is one more file to keep current.** If the cluster's signing key is rotated and the copy is not, registration stops. It fails closed.
- **The registration listener is protected by a network policy and a service account token.** Namespaces are not a wall, and this project says so. The token check is the control. The policy is the second layer.
- **The cloud question is postponed, not answered.** Federation needs a hosting and key-rotation arrangement; a VM managed identity shares its permissions across processes on the VM. Choosing between them without a workload that needs one would be guessing. The cost is that milestone 4 starts with a decision.
