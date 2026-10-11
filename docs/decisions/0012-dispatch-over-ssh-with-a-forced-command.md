# 0012. Dispatch to the worker over SSH, with a forced command

Status: Accepted
Date: 2026-10-11

## Context

[0005](0005-ai-workers-on-a-separate-vm.md) put the AI worker on a VM that is not a cluster node, and named the price: Argo runs pods, not processes on another machine. Something has to carry a job from a workflow to the worker and bring a result back, with authentication, cancellation, and cleanup.

The network as built already says which direction that should go. The orchestrator can open SSH to the worker. The worker can open one connection to the orchestrator, to the package proxy on port 3128, and nothing else. A worker that is assumed to be turned should not be the side that starts things.

The roadmap adds a limit: if a candidate needs a substantial custom service to pass the milestone 3 gate, replace it or simplify the design.

## Options

| Option | New listener | New network rule | Custom code | Notes |
| --- | --- | --- | --- | --- |
| SSH from a workflow step, with a key that can only run a job runner | None. The worker's SSH daemon exists | None | A runner script on the worker | Cancelling is closing the session. The result has to fit on standard output |
| HTTP job agent on the worker | One, on the untrusted machine | One, orchestrator to worker | A service, or an agent found and vetted | A proper API for status and cancel. A second daemon to patch on the worker |
| The worker pulls jobs from a queue on the orchestrator | One, on the trusted machine | One, worker to orchestrator | A queue client, and a queue to run on 2 vCPUs | The worker starts the conversation. Cancelling becomes a message the worker may ignore |
| Join the worker to the cluster as an agent node | None | Several | None | Rejected in 0005. The node would hold cluster credentials |

## Decision

A workflow step opens an SSH session from the orchestrator to the worker. The session runs one fixed command, the job runner. The job goes in on standard input and the result comes back on standard output.

- **The key.** A dispatch key pair of its own, separate from the feed key. The private half is a Kubernetes secret in the `orchestration` namespace, mounted into the dispatch step and nothing else. The worker's host key is pinned next to it.
- **The account.** A dedicated unprivileged account on the worker, with no `sudo`. Its `authorized_keys` entry carries `restrict` and `command=`, so the key gets no terminal, no forwarding, and no choice of command.
- **The job.** One JSON document on standard input: job ID, limits, the address of the tool service, the job's token ([0013](0013-a-token-per-job-and-no-cloud-identity-yet.md)), and the task. Nothing is passed as a command-line argument, where another process on the worker could read it.
- **The run.** The runner starts the agent inside a transient systemd unit with a hard time limit and a session directory of its own. The agent talks to the model server on localhost and to the tool service on the orchestrator.
- **The result.** One JSON document on standard output. The workflow checks it against a schema and a size limit. Anything else fails the step. Standard error is the runner's log.
- **Cancel.** Stopping the workflow ends the step, which closes the session. The runner treats a closed session as a cancel: it stops the unit and deletes the session directory. The time limit on the unit catches a runner that misses it.
- **One at a time.** The workflow holds a mutex, and the runner refuses to start while a job's unit exists.

The existing rule for TCP 22 from the orchestrator subnet to the worker subnet covers this. No rule is added for dispatch.

## Trade-offs

- **A key that reaches the worker now lives in the cluster.** Whoever reads that secret can run jobs on the worker. That is all it buys: the worker holds nothing, and the key runs one command as an account without privileges.
- **The SSH daemon is the dispatch interface.** It was not designed as one. There is no status call and no progress. A workflow knows a job is running because the session is open.
- **Cancel depends on the runner noticing a closed session.** A session without a terminal does not signal its command reliably when it ends. The runner has to watch for it, and the gate has to prove it does. The unit's time limit is the backstop, not the mechanism.
- **The result is whatever the worker prints.** A turned worker can print a well-formed lie. The schema check proves shape, not truth. The result stays untrusted input, as the architecture already says.
- **The runner is custom code on the untrusted side.** It is small, and nothing trusts it. A worker that rewrites its own runner gains what it already had.
- **Jobs share an account and a kernel.** The session directory is deleted, not the machine. That is T19, and cleanup has to be tested, not assumed.
- **Standard output is a narrow pipe.** A result that outgrows it means the design of the result is wrong. Evidence and large artifacts go through the tool service, by reference.
