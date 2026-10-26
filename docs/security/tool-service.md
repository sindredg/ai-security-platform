# Tool service and job identity

Status: **tested** in CI on 2026-10-14 with `python -m pytest -q`: 160 tests passed, on the image the service is built from. Deployed on the orchestrator and **tested** on the live system on 2026-10-15: the [deployment checks](../validation/tool-service.md) and one round trip from the worker ([worklog](../worklogs/0003-toolchain-integration.md#the-deployment-on-the-orchestrator)). Since 2026-10-21 the dispatch step registers and revokes a job for each workflow, and the worker's calls with its token are allowed and logged ([worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows), [ADR 0030](../decisions/0030-how-a-job-reaches-the-worker.md)). Since 2026-10-25 it stores NetBox's evidence per job, and jobs on the live system have read it ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#evidence-per-job)). See the [roadmap](../roadmap.md#3-toolchain-integration) for milestone status.

The tool service authorizes tool calls from the AI worker, on the orchestrator. This page explains how it identifies a job, rejects unauthorized requests, and records decisions. The decisions are in ADRs [0013](../decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md), [0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md), and [0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md). The code is in `tool-service/`, and its policy is in `policies/tool-service.json`.

## How a call identifies its job

The design assumes the worker can be compromised. The service identifies the job by its token and uses the permissions registered for that job. It does not trust job or target identifiers supplied in a tool call.

1. The dispatch step makes a random token for one job.
2. It registers the job with the tool service: job ID, target, tools, lifetime, and the SHA-256 digest of the token. The token itself is not sent.
3. The dispatch step authenticates with a Kubernetes service account token. The service verifies the token using a copy of the cluster's public signing keys, without contacting the Kubernetes API. The copy is the key set the API serves at `/openid/v1/jwks`. The token names its key by ID, and the key's type determines the algorithm.
4. The worker receives the job token and sends it with every tool request over TLS. It trusts only the server certificate copied to the worker and checks the server name.
5. The tool service hashes the token and looks the job up. The scope comes from that lookup. Nothing in the call can name a job or a target.
6. When the job ends, the dispatch step revokes it by job ID. The token also expires if revocation is missed.

The service can register jobs, validate tokens, authorize calls, and revoke jobs. The dispatch step issues the tokens and connects these steps, since 2026-10-21 ([worklog](../worklogs/0003-toolchain-integration.md#installed-argo-and-the-first-workflows)).

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
| Tool | The reference is one the job's target lists, and resolves to a file inside the target's directory. On a per-job target the file's name is the job's ID, a dot, and the reference, so another job on the same target finds nothing ([ADR 0040](../decisions/0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)) | An error result |
| Tool | The file is no larger than a result may be, and one JSON document, with no key twice, every field and value as the schema for its kind names them, and the call's reference in it, and on a per-job target the call's job. The model gets the parsed document, not the file's text ([#152](https://github.com/sindredg/ai-security-platform/issues/152)) | An error result |
| Handler | The result is within the size limit | An error result |
| Handler | The job has not expired or been revoked while the tool ran. A late result is discarded | An error result |

The two tool rows are Verified on the live system on 2026-10-25. A job under a name with no collection got `nothing by that reference` on each call. A document with an injected field got `evidence does not match its schema`, and its text reached no model ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-collection-and-the-jobs)). Before that the tool read `<target>/<reference>.json` and returned the file as it was. Status is in the [roadmap](../roadmap.md#4-netbox-target-and-exercise-1-investigation).

![Where a job's NetBox evidence goes: the collect command on the orchestrator, as root, reads the configured permissions from NetBox with its own token, and each account's reads through the observer account on the lab VM, which uses each account's own token. It keeps the verdicts and both reports in the job's directory, which the job never reads. It writes the verdicts into a config map that only the workflow's comparison step reads, with its own job's key and no credential, and only facts into another config map. The tool service mounts that one and hands the AI worker only the job's own documents, in the fields their schemas name](../diagrams/evidence-per-job.svg)

The diagram source is [`diagrams/evidence-per-job.html`](../diagrams/evidence-per-job.html).

Registration uses a separate listener. Its network policy admits only pods with the dispatch label in `orchestration`, and the worker's node port leads to the tool listener only. The listener checks the caller's token signature, issuer, audience, expiry, and service account. It then validates the registration schema, target, tools, and uniqueness of the job ID and token digest.

Requests rejected by the application return an error without the tool's result. An audit entry records the decision and reason. Requests rejected by the SDK are also logged. Rejections before the application runs, such as the server's concurrency limit, do not produce these audit entries.

## The audit line

One JSON object per decision, on standard output. Standard output carries nothing else.

| Field | Value |
| --- | --- |
| `ts` | The time, in UTC |
| `start` | A random identifier, made once when the service starts |
| `seq` | Counts from 1 within one `start`. A hole means a lost line ([ADR 0019](../decisions/0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)) |
| `event` | `call`, `request` for a refusal before it became a call, `register`, or `revoke` |
| `job` | The job ID, or `null` when the request cannot be associated with a job |
| `caller` | The source address |
| `tool` | The tool that was asked for |
| `args_sha256` | A SHA-256 digest of the arguments. The arguments themselves are not logged |
| `decision` | `allowed` or `refused` |
| `reason` | Why, for a refusal |
| `result_bytes` | The size of an allowed tool result. The result itself is not logged |

The pod runs the image its manifest names (`T.2`). Since 2026-10-25 that is the build from commit `91bace4`, with evidence per job ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-collection-and-the-jobs)). From 2026-10-22 it was the build from `96f91ba`, on the [fixed base image](../worklogs/0003-toolchain-integration.md#installed-the-images-on-the-fixed-base).

The service writes to standard output and opens no log file. A host service, `aisec-audit-copy`, appends them to a file that no pod mounts. It runs on the orchestrator since 2026-10-16. Storage and who can change it are on the [audit log](audit-log.md) page.

## Deployment controls

The service parses untrusted input. These controls limit what a bug in it gives an attacker. They are decided in [ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md), written in `platform/tool-service/` and `infra/platform/main.tf`, and checked in the pipeline. They are deployed, and the [tool service checks](../validation/tool-service.md) test them on the live system.

![The tool service in K3s on the orchestrator: the AI worker reaches the tool listener on 8443 only through node port 30443 on the private address, over TLS 1.3 to a pinned certificate. Two short-lived pods per workflow in orchestration register and revoke the job on 8444. The tool service pod reads its policy, key set, certificate, and key from one read-only volume and each target's evidence from a read-only volume of its own, and writes audit lines to its log, which a host service copies. Its egress to the internet, and a mesh device's connection to the tool port, are blocked](../diagrams/tool-service-cluster.svg)

The diagram source is [`diagrams/tool-service-cluster.html`](../diagrams/tool-service-cluster.html).

- The pod runs as user 65532, without a service account token, privilege escalation, capabilities, or a writable file system. Both namespaces enforce the restricted pod security level.
- Both namespaces deny all traffic by default. The tool port admits the worker subnet, the registration port admits the dispatch pods, and the tool service pod has no egress. A host rule also drops forwarded traffic from any pod to anything but pods ([ADR 0018](../decisions/0018-a-host-rule-keeps-pods-off-the-internet.md)).
- The worker reaches the tool port through node port 30443, which keeps the caller's address for the network policy and the audit line. K3s answers node ports on the orchestrator's private address only.
- A pair of network security group rules allows the worker subnet to reach TCP 30443 on the orchestrator.
- The image is pulled by digest from the repository's package registry. The package is public, so the cluster needs no pull secret and the orchestrator holds no registry token. The image holds the code in this repository and no secret. The certificate, its key, the policy, and the cluster's key set are mounted when the pod starts. Each target's evidence is a read-only volume of its own: the synthetic target's from the file `deploy.sh` puts in its config map, NetBox's from the config map the collect command writes, whose new keys reach the running pod without a restart (`T.14`).

CI enforces a 300-line limit on the server code and scans its pinned dependencies. A size-limit violation or a dependency vulnerability fails the check. The [worklog](../worklogs/0003-toolchain-integration.md#size) records the line count.

## What this does not do

- **A bearer token can be reused if stolen.** Any process that reads it can make calls with the job's permissions until it is revoked or expires. Those permissions are limited to one target and the registered tools.
- **Jobs on the synthetic target read the same evidence.** The operator writes it, and it does not change. NetBox's is stored per job since 2026-10-25 ([ADR 0040](../decisions/0040-a-jobs-evidence-is-collected-on-the-hosts-and-stored-per-job.md)).
- **Jobs live in memory.** A restart of the service ends every job. It fails closed.
- **The rate limit is shared.** Requests without a valid token, from any caller, share one count per minute. Past it they get 429, and the rest of that minute leaves one audit line, not one per request. How many were refused in that minute is not recorded. A valid token is never limited. Tested on the live system on 2026-10-16.
- **An offline check cannot see a deleted pod.** The dispatch step's token stays valid until it expires.
- **Schema validation checks structure, not meaning.** A read-only tool can still expose more data than a job needs.
- **Tool results remain untrusted text.** The service checks their size and source. It does not detect misleading content or injected instructions.

## Hostile-input tests

The tool service is the one piece of custom code that reads what a compromised worker sends ([ADR 0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)). These cases are unit tests in `tool-service/tests/`, run in the pipeline, and not drills. Every case ends the same way: the call is refused, nothing of the result goes back, and one audit line records the decision and the reason.

| Group | Case |
| --- | --- |
| Malformed arguments | A body that is not JSON, or not valid UTF-8 |
| | A missing field, a wrong type, and a field the schema does not name |
| | An evidence reference with `..`, an absolute path, or a null byte |
| | A tool name that no policy lists |
| Cross-job access | A valid token for one job asks for another job's evidence |
| | A valid token asks for a tool or a target outside its job's scope |
| | The arguments name a different job than the token. The token decides |
| Tokens | No token, a malformed token, and a token nobody issued |
| | An expired token, and a token revoked when its job ended |
| | A refusal never puts the token in the response or the log |
| Oversized requests | A body over the size limit, refused before it is parsed |
| | A result over the size limit, and one call more than the job's call limit |
| Concurrent cancellation | A job is cancelled while its call is in flight. The result is dropped, not delivered late |
| | Two calls race the revocation. None succeeds after it |
| | The same job is cancelled twice, or registered twice. Neither is an error that leaves a live token |

## Validation evidence

| Claim | Evidence | Source |
| --- | --- | --- |
| Rejection cases above | Tests in `tool-service/tests/`, grouped as in the [hostile-input tests](#hostile-input-tests) | CI on every pull request; commands and results in the worklog |
| Tests detect removed controls | Mutation testing detected 28 of 29 deliberate changes. One redundant check was not detected because another check rejected the request first | Local workstation; one recorded run |
| Goose can call the service | TLS calls before and after token revocation | Local workstation with a stub model; commands and results in the worklog |
| Deployment on the orchestrator | The [tool service checks](../validation/tool-service.md) pass, and each was seen to fail first | Live system, 2026-10-15 |
| The live service refuses a tool outside the job, a revoked or expired job token, and a registration with a wrong audience, another account, or an expired token | The round trip and the expiry runs | Live system, 2026-10-15; [runbook](../runbooks/tool-service.md#round-trip) and [worklog](../worklogs/0003-toolchain-integration.md#the-round-trip) |
| The live service refuses a job another job's evidence, and a document with a field outside its schema | Two jobs on NetBox's target: one with no collection under its name, one with an injected field | Live system, 2026-10-25; [runbook](../runbooks/evidence-collection.md) and [worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-collection-and-the-jobs) |

Commands and output are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#slice-the-tool-service).
