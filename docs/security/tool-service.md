# Tool service and job identity

Status: written and tested in the pipeline on 2026-10-13. Not deployed. Nothing on this page is tested on the running system, and the parts marked decided do not exist yet.

The tool service is the one thing on the trusted machine that the AI worker can call. This page says how a call proves which job it belongs to, what the service refuses, and what it records. The decisions are in ADRs [0013](../decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md), [0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md), and [0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md). The code is in `tool-service/`, and its rules are in `policies/tool-service.json`.

## How a call proves its job

The worker is assumed to be turned. So nothing the worker says about itself is believed, and the only thing it can present is a token it was handed.

1. The dispatch step makes a random token for one job.
2. It registers the job with the tool service: job ID, target, tools, lifetime, and the SHA-256 digest of the token. The token itself is not sent.
3. The tool service accepts the registration only from the dispatch step, which proves itself with its Kubernetes service account token. The service checks that token offline, against the cluster's public signing key.
4. The worker gets the token inside its job document, and sends it with every call, over TLS, to a certificate it has a copy of.
5. The tool service hashes the token and looks the job up. The scope comes from that lookup. Nothing in the call can name a job or a target.
6. When the job ends, the dispatch step revokes it by job ID. The lifetime catches a job nobody revoked.

Steps 1, 2, 4, and 6 need the dispatch step, which is not built. The service's side of all six is written.

## What is checked, and where

A request passes two stages. The gate stands in front of the MCP SDK and decides who is calling. The call handler stands behind it and decides what that job may do. The handler is the authority, because it works on what the SDK parsed and will act on.

| Stage | Check | Refused with |
| --- | --- | --- |
| Gate | The request is a `POST` to the tool endpoint | 404 |
| Gate | It carries a bearer token | 401 |
| Gate | The token belongs to a job that is not revoked and not expired | 401 |
| Gate | The body is within the size limit. The declared length is checked before anything is read, and the count again while reading | 413 |
| Gate | The body is JSON, and a message the policy names | 400 |
| Handler | The job is under its call limit. Refused calls count | A refused result |
| Handler | The tool is in the job's scope | A refused result |
| Handler | The arguments match the tool's schema in the policy. Fields the schema does not name are refused | A refused result |
| Tool | The reference resolves to a file inside the job's own target directory | A refused result |
| Handler | The result is within the size limit | A refused result |
| Handler | The job is still alive after the tool has run. A late result is dropped | A refused result |

Registration has its own listener, which the worker cannot reach by design. It checks the caller's token for signature, issuer, audience, expiry, and the one service account allowed. Then it checks the registration against a schema, the target and tools against the policy, and that neither the job ID nor the token digest is already known.

Every refusal ends the same way: nothing of a result goes back, and one audit line records the decision and the reason. A refusal by the SDK itself, behind the gate, gets a line too.

## The audit line

One JSON object per decision, on standard output. Standard output carries nothing else.

| Field | Holds |
| --- | --- |
| `ts` | The time, in UTC |
| `event` | `call`, `request` for a refusal before it became a call, `register`, or `revoke` |
| `job` | The job the token named. Empty when no job could be named |
| `caller` | The source address |
| `tool` | The tool that was asked for |
| `args_sha256` | A digest of the arguments. Never the arguments |
| `decision` | `allowed` or `refused` |
| `reason` | Why, for a refusal |
| `result_bytes` | The size of what went back. Never the result |

The service opens no log file. The host is meant to capture the lines and append them to a file that no pod mounts. That half is decided and not built, so today the lines go nowhere.

## What stands behind the code

The service is custom code that parses hostile input. When it is wrong, these are meant to hold. All are decided in ADR 0014, and none exists yet.

- The pod runs without root, capabilities, a writable file system, or a service account token.
- Network policy admits the worker subnet on the tool port and the workflow's pods on the registration port. Egress is denied.
- One rule pair opens one port from the worker subnet.

What exists is the size of the thing: 292 lines of code against a limit of 300, counted in the pipeline, and a scan of its 28 pinned packages that blocks a pull request.

## What this does not do

- **A token is a bearer token.** Anything on the worker that reads it is the job until the job ends. The scope is what limits that: one target, the listed tools, minutes.
- **Two jobs on one target read the same evidence.** Evidence is stored per target. That is enough while evidence is synthetic and fixed.
- **Jobs live in memory.** A restart of the service ends every job. It fails closed.
- **Nothing slows a caller without a token.** Each request is refused, and each refusal is a line. Sixteen connections at a time is the only limit.
- **An offline check cannot see a deleted pod.** The dispatch step's token stays valid until it expires.
- **A schema proves shape.** A tool that reads too much is still allowed to read it.
- **The result that goes back to the model is untrusted text.** The service bounds its size and says where it came from. It does not read it.

## Where the proof is

| Claim | Proof | From |
| --- | --- | --- |
| Each refusal above | 153 tests in `tool-service/tests/`, grouped like the roadmap's [hostile-input table](../roadmap.md#hostile-input-tests-for-the-tool-service) | The pipeline, on every pull request |
| The tests can fail | Each control removed in turn: 26 of 27 changes caught. The one left is a second layer behind another check | A workstation, once |
| The agent runtime can use it | The pinned Goose against the service over TLS, before and after a revocation | A workstation, with a stub model |
| Any of it on the orchestrator | None yet | |

Commands and output are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#slice-the-tool-service).
