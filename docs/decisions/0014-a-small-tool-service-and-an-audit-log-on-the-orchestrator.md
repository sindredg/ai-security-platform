# 0014. A small custom tool service, and an audit log on the orchestrator

Status: Accepted
Date: 2026-10-11

## Context

The threat model's first finding is that the tool services are the wall. Every limit on the AI worker ends at one service on the trusted machine that reads hostile input, and that service was not designed.

Four open items point at it:

| Item | Threats |
| --- | --- |
| A turned worker calls a tool outside its job | T16 |
| The worker exploits a bug in the service and lands on the orchestrator | T22, T36 |
| The worker edits or deletes the record of its own calls | T21 |
| Nothing records what ran on a machine, and logs stay on the machine they describe | [Hardening, open](../security/hardening.md#open) |

The milestone 3 gate asks for one authorized tool call, a refused call for another job or target, and a log of every call with caller, job, and decision, where the worker cannot write to it or delete it.

The roadmap also says: if a candidate needs a substantial custom service to pass the gate, replace it or simplify the design. The authorization check is this project's own rule set. No product ships it. So the question is not whether there is custom code, but how little.

## Options

| Option | Custom code | Components on the orchestrator | Notes |
| --- | --- | --- | --- |
| One small MCP server that checks every call itself | The server: authentication, the policy check, the log line, and each tool | One | The wall can be read end to end |
| An MCP gateway with a policy engine, in front of stock tool servers | Policy rules and glue | Three or more | Less code written here. The wall is spread over software nobody here wrote, on a 2-vCPU machine |
| No tool protocol: give the agent a shell or an HTTP tool and a plain API | The API | One | The agent needs a general-purpose tool, which is the thing the restricted tool set exists to avoid ([A8](../security/ai-threats.md)) |

For the log:

| Option | Who can change a written line | Notes |
| --- | --- | --- |
| The service writes its own log file | The service | A bug in the service rewrites the record of the attack that used it |
| The service prints lines, and the host stores them | Root on the orchestrator | The service can add and never change |
| A store outside the platform | Its own administrator | The production answer. There is no second trusted machine here |

## Decision

**One small MCP server on the orchestrator, written for this project.**

- **Language and protocol.** Python, with the official MCP SDK, over HTTP with TLS. Dependencies are pinned with hashes.
- **One port for the worker.** The service listens on the orchestrator's private address. One rule pair lets the worker subnet reach that port, next to the package proxy rule. The architecture already plans this flow.
- **Every call is checked on the server.** The token names the job ([0013](0013-a-token-per-job-and-no-cloud-identity-yet.md)). The job's scope names the target and the tools. Arguments are checked against a schema. Anything not allowed is refused. The rules are data in `policies/`, not branches in the code.
- **Output is bounded.** A size limit per call and a call limit per job.
- **Milestone 3 has one tool.** It returns a piece of synthetic evidence by reference, read-only. That is enough for the gate, and it keeps the first version of the wall short.
- **Small has a number.** If the server passes a few hundred lines without its tools, the design is wrong and gets simplified before it grows. [0016](0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md) set the number at 300 on 2026-10-13.

**The pod is treated as the next thing to fall.**

- Its own namespace, `tool-services`. No service account token. Not root, read-only root filesystem, no capabilities, the default seccomp profile.
- Ingress by network policy: the worker subnet on the tool port, the workflow's pods on the registration port.
- Egress denied by default. In milestone 3 the service has nowhere to call.
- The same default-deny egress goes on every workload namespace. A pod that is taken cannot use the orchestrator's open ports 443 and 80. That narrows [T05](../security/threat-model.md) from "anything on the orchestrator" to "root on the orchestrator". [0018](0018-a-host-rule-keeps-pods-off-the-internet.md) adds a host rule for the seconds before a new pod's policy is written, and for DNS.

**The image is built by the repository's pipeline** on `main`, pushed to the repository's container registry, and pulled by digest. The pipeline gets permission to write packages, and still holds no cloud credential.

**The audit log is written by the host, not by the service.**

- The service prints one JSON line per call: time, job, caller address, tool, a digest of the arguments, the decision, the reason for a refusal, and the result size. Allowed and refused calls both.
- The container runtime captures the lines. A unit on the orchestrator appends them to a root-owned file that has the append-only attribute. No pod mounts that file.
- No payloads. Arguments are logged as a digest, results as a size.

**Host logging is split.**

- In milestone 3, the orchestrator pulls the worker's journal over SSH on a timer, with a key that can only run that export. A worker that is taken can no longer erase what was already pulled.
- An audit daemon and file integrity monitoring move to milestone 6, with the drills that would use them.

## Trade-offs

- **Custom code that parses hostile input, on the trusted machine.** This is the risk the roadmap warned about, taken on purpose and kept small. A parsing bug here is a path to the trusted side. The pod limits are what stand behind it, and a container is not a strong wall.
- **A Python runtime and its dependencies sit in that image.** More to pin and scan than a static binary. The MCP SDK is young and moves fast.
- **The service depends on the agent runtime speaking this protocol with a bearer token and a restricted tool set.** That is not proven yet. It is the first thing the build has to show. If it fails, the transport changes, not the wall. [0016](0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md) records what the build showed.
- **The log sits on the machine it audits.** Root on the orchestrator can remove the append-only attribute and edit it. This is the lab compromise already listed in [lab against production](../security/lab-vs-production.md).
- **Runtime log rotation can drop lines** if the unit that copies them is down for long enough. It has to be watched, and nothing watches yet.
- **The worker's journal is pulled, not pushed.** Whatever happened since the last pull can still be erased by a worker that was taken as root. Pushing would need another port from the worker to the orchestrator.
- **Default-deny egress binds pods, not host processes.** The mesh agent, K3s, and the proxy keep the host's rules.
- **The pipeline can now publish an image that the orchestrator runs.** The digest pin is the check: the orchestrator runs what a reviewed commit names, not what the registry holds.
- **Operator sessions to targets ([T04](../security/threat-model.md)) are not in this log yet.** No target exists. Milestone 4 adds them.
