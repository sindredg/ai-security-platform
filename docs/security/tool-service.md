# Tool service and job identity

Status: **tested** in CI on 2026-10-14 with `python -m pytest -q`: 160 tests passed, on the image the service is built from. The service has not been deployed. Live validation and deployment controls remain part of milestone 3. See the [roadmap](../roadmap.md#3-toolchain-integration) for milestone status.

The tool service will authorize tool calls from the AI worker on the orchestrator. This page explains how it identifies a job, rejects unauthorized requests, and records decisions. The decisions are in ADRs [0013](../decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md), [0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md), and [0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md). The code is in `tool-service/`, and its policy is in `policies/tool-service.json`.

## How a call identifies its job

The design assumes the worker can be compromised. The service identifies the job by its token and uses the permissions registered for that job. It does not trust job or target identifiers supplied in a tool call.

1. The dispatch step makes a random token for one job.
2. It registers the job with the tool service: job ID, target, tools, lifetime, and the SHA-256 digest of the token. The token itself is not sent.
3. The dispatch step authenticates with a Kubernetes service account token. The service verifies the token using a copy of the cluster's public signing keys, without contacting the Kubernetes API. The copy is the key set the API serves at `/openid/v1/jwks`. The token names its key by ID, and the key's type determines the algorithm.
4. The worker receives the job token and sends it with every tool request over TLS. It trusts only the server certificate copied to the worker and checks the server name.
5. The tool service hashes the token and looks the job up. The scope comes from that lookup. Nothing in the call can name a job or a target.
6. When the job ends, the dispatch step revokes it by job ID. The token also expires if revocation is missed.

The service can register jobs, validate tokens, authorize calls, and revoke jobs. The dispatch step that issues tokens and connects these steps has not been built.

ADR 0013 requires the service account token but does not say how the service verifies it. ADR 0014 gives the pod no credential and no outbound access, which rules out asking the API server. Offline verification satisfies both. [ADR 0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md) describes the two records as contradictory. They do not conflict: neither specifies the verification method, and ADR 0016 chooses it.

## What is checked, and where

A request passes two stages. Before the Model Context Protocol (MCP) SDK parses the message, the request gate checks the endpoint, token, body size, and allowed message type. The call handler then checks the requested operation and arguments parsed by the SDK. Authorization happens in the handler, using the values the tool will receive.

| Stage | Check | Refused with |
| --- | --- | --- |
| Gate | The request is a `POST` to the tool endpoint | 404 |
| Gate | It carries a bearer token | 401 |
| Gate | The token belongs to a job that has not expired or been revoked | 401 |
| Gate | The body is within the size limit. The declared length is checked before anything is read, and the count again while reading | 413 |
| Gate | The body is JSON and uses an allowed message type | 400 |
| Handler | The job is under its tool call limit. Rejected tool calls count | An error result |
| Handler | The tool is in the job's scope | An error result |
| Handler | The arguments match the tool's schema in the policy. Extra fields are rejected | An error result |
| Tool | The reference resolves to a file inside the job's target directory | An error result |
| Handler | The result is within the size limit | An error result |
| Handler | The job has not expired or been revoked while the tool ran. A late result is discarded | An error result |

Registration uses a separate listener. The planned network rules will block worker access to it. The listener checks the caller's token signature, issuer, audience, expiry, and service account. It then validates the registration schema, target, tools, and uniqueness of the job ID and token digest.

Requests rejected by the application return an error without the tool's result. An audit entry records the decision and reason. Requests rejected by the SDK are also logged. Rejections before the application runs, such as the server's concurrency limit, do not produce these audit entries.

## The audit line

One JSON object per decision, on standard output. Standard output carries nothing else.

| Field | Value |
| --- | --- |
| `ts` | The time, in UTC |
| `event` | `call`, `request` for a refusal before it became a call, `register`, or `revoke` |
| `job` | The job ID, or `null` when the request cannot be associated with a job |
| `caller` | The source address |
| `tool` | The tool that was asked for |
| `args_sha256` | A SHA-256 digest of the arguments. The arguments themselves are not logged |
| `decision` | `allowed` or `refused` |
| `reason` | Why, for a refusal |
| `result_bytes` | The size of an allowed tool result. The result itself is not logged |

The service writes to standard output and opens no log file. A planned host service will append the entries to a file that no pod mounts. Persistent log storage has not been implemented.

## Planned deployment controls

The service parses untrusted input. The following controls will limit the impact of a service vulnerability. They are decided in ADR 0014 and have not been implemented.

- The pod runs without root, capabilities, a writable file system, or a service account token.
- Network policy admits the worker subnet on the tool port and the workflow's pods on the registration port. Egress is denied.
- A pair of network security group rules allows the worker subnet to reach the tool port on the orchestrator.

CI enforces a 300-line limit on the server code and scans its pinned dependencies. A size-limit violation or a dependency vulnerability fails the check. The [worklog](../worklogs/0003-toolchain-integration.md#size) records the line count.

## What this does not do

- **A bearer token can be reused if stolen.** Any process that reads it can make calls with the job's permissions until it is revoked or expires. Those permissions are limited to one target and the registered tools.
- **Two jobs on one target read the same evidence.** Evidence is stored per target. That is enough while evidence is synthetic and fixed.
- **Jobs live in memory.** A restart of the service ends every job. It fails closed.
- **Unauthenticated requests have no rate limit.** Requests that reach the application without a valid token are rejected and logged. The server limits concurrent requests, but does not limit how often a caller can retry.
- **An offline check cannot see a deleted pod.** The dispatch step's token stays valid until it expires.
- **Schema validation checks structure, not meaning.** A read-only tool can still expose more data than a job needs.
- **Tool results remain untrusted text.** The service checks their size and source. It does not detect misleading content or injected instructions.

## Validation evidence

| Claim | Evidence | Source |
| --- | --- | --- |
| Rejection cases above | Tests in `tool-service/tests/`, grouped by the roadmap's [hostile-input table](../roadmap.md#hostile-input-tests-for-the-tool-service) | CI on every pull request; commands and results in the worklog |
| Tests detect removed controls | Mutation testing detected 28 of 29 deliberate changes. One redundant check was not detected because another check rejected the request first | Local workstation; one recorded run |
| Goose can call the service | TLS calls before and after token revocation | Local workstation with a stub model; commands and results in the worklog |
| Deployment on the orchestrator | No evidence yet. The service has not been deployed | Not tested on the live system |

Commands and output are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#slice-the-tool-service).
