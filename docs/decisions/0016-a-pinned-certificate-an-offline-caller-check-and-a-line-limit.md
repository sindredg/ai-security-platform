# 0016. A pinned certificate, an offline caller check, and a line limit for the tool service

Status: Accepted
Date: 2026-10-13

## Context

[0013](0013-a-token-per-job-and-no-cloud-identity-yet.md) and [0014](0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md) designed the tool service before any of it existed. Writing it turned up three things those records got wrong or left loose.

**The two records contradict each other.** 0013 has the registration caller prove itself with its Kubernetes service account token. 0014 gives the tool service pod no service account token and denies it all egress. A pod with no credential and no path to the API server cannot ask the cluster whether a token is good.

**The private authority is more than the job needs.** 0013 has a private authority sign the server certificate. The authority's key is a second secret that can mint a certificate the worker would trust, and it exists to sign exactly one certificate. Whether the agent runtime would accept anything simpler was not known when 0013 was written.

**"A few hundred lines" cannot fail.** 0014 says small has a number and then does not give one. A limit nobody can measure is a hope.

A trial on a workstation on 2026-10-13 answered the open question. The pinned Goose release takes its trust from one file, and accepts a self-signed server certificate from that file as long as the certificate is not marked as an authority. The cases and results are in the [milestone 3 worklog](../worklogs/0003-toolchain-integration.md#what-goose-needs-found-before-the-service-was-written).

## Options

How the registration listener checks its caller:

| Option | What the pod needs | Notes |
| --- | --- | --- |
| Ask the API server to review the token | A service account of its own and egress to the API server | The least code. It gives the pod that reads hostile input a cluster credential and a way out, which 0014 takes away on purpose |
| Check the token offline, against the cluster's public signing key | A copy of a public key | No credential and no connection. Cannot see that a pod was deleted. The copy has to follow the cluster's key |
| A shared secret between the dispatch step and the service | One long-lived secret in two namespaces | The simplest. A secret that never expires, for a listener that decides which tokens are valid |

How the worker trusts the server:

| Option | Secrets on the orchestrator | Rotation | Notes |
| --- | --- | --- | --- |
| A private authority signs the server certificate | The authority's key and the server's key | New server certificate. The worker's copy of the authority stays | Whoever takes the authority's key can make a certificate for any name the worker trusts |
| One self-signed certificate, copied to the worker | The server's key | New certificate, and a new copy on the worker | Nothing can mint a second certificate. Goose accepts it only when it is not marked as an authority |
| The system's public authorities | The server's key | Whatever the issuer does | The worker has no internet and the name is private. No public authority issues for it |

What small means:

| Option | Can it fail | Notes |
| --- | --- | --- |
| A judgment, reported in the worklog | No | Every review finds a reason why this one feature is worth it |
| 300 lines of code, counted in the pipeline | Yes | Tight enough to force rules out of the code and into data |
| 500 lines, counted in the pipeline | Yes | Room to grow a second service inside the first |

## Decision

**The registration caller is checked offline.**

- The dispatch step presents a projected service account token, made for the tool service as its audience, with a short lifetime.
- The tool service checks the signature against the public half of the cluster's signing key, then the issuer, the audience, the expiry, and the subject. One service account may register.
- The type of the key picks the algorithm. The token's header does not.
- The pod keeps what 0014 gave it: no service account token and no egress.

**The server has one self-signed certificate, and the worker has a copy.**

- No authority exists. The certificate is not marked as one.
- The agent trusts that certificate and nothing else, and checks the name.
- Both listeners use it. TLS 1.3 is the minimum.
- This replaces the private authority in 0013.

**Small is 300.**

- Lines that hold code, in the server without its tools. Blank lines, comments, and docstrings do not count.
- The pipeline counts on every pull request and fails past the limit.
- A server over the limit is simplified. The limit is not raised to fit it.

**Three smaller points, settled in the same build.**

- Registration carries the SHA-256 digest of the job token. The token itself reaches the tool service only when the worker presents it.
- The rules are one file, `policies/tool-service.json`: targets, tools and their argument schemas, limits, the messages the service answers, and who may register.
- The audit line has an `event` field, because a registration, a revocation, and a request refused before it became a call are decisions too.

## Trade-offs

- **An offline check cannot see a deleted pod.** A service account token stays valid until it expires. The short lifetime and the audience are what limit a stolen one: minutes, and one listener.
- **The public key is a copy.** If the cluster's signing key is rotated and the copy is not, every registration is refused. It fails closed, and it stops all work until someone notices.
- **The offline check is not tested against the cluster.** The tests sign with keys made for the test. Which algorithm K3s signs with, and what its issuer is called, were reasoned and not read.
- **A pinned certificate has no revocation.** A stolen key is answered with a new certificate and a new copy on the worker. Until the copy arrives, no job can call a tool.
- **Every rotation touches the worker.** An authority would have spared that. One file copy is the price of not having its key.
- **300 is tight on purpose.** The first version of the server was 342 lines and had to lose rules to data to pass. The server is at 292. The next feature has eight lines, so the next feature starts with a simplification or with a new record that argues for a higher number.
- **A line count can be gamed.** Long lines, and logic moved into a schema nobody reviews as carefully as code. The formatter fixes the line length, and the policy file has its own tests.
- **Rules as data move the risk to the data.** A wrong pattern in the policy file is as bad as a wrong branch. It is shorter to read, and it is still custom.
