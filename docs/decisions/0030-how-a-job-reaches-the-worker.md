# 0030. How a job reaches the worker: a host rule exception, a dispatch image, and a socket-started job unit

Status: Accepted
Date: 2026-10-19

Changes three parts of [0012](0012-dispatch-over-ssh-with-a-forced-command.md): which image opens the session, that no network rule is added, and that the runner starts the agent's unit itself. Adds one rule to the host rule of [0018](0018-a-host-rule-keeps-pods-off-the-internet.md). The rest of 0012 stands: SSH from a workflow step, a key that runs one command as an account without sudo, the job on standard input, the result on standard output, a closed session as the cancel, and one job at a time.

## Context

0012 was decided on 2026-10-11, before three things that now stand in its way:

- **The host rule drops a pod's traffic to the worker.** [0018](0018-a-host-rule-keeps-pods-off-the-internet.md) drops everything forwarded from the pod network to an address outside it, and [0023](0023-the-host-rule-limits-what-pods-reach-on-the-host.md) does the same for the host's own ports but two. A workflow step is a pod, so its SSH session to `10.40.0.36:22` is dropped on the orchestrator before the security groups see it. 0012's "no rule is added" counted only the security groups.
- **An account without sudo cannot start a system unit.** 0012 has the runner start the agent "inside a transient systemd unit", and gives the runner an account with no sudo. `systemd-run` for a system unit needs root. Today `run-agent.sh` runs as root, from the operator's shell.
- **No image has both Python and an SSH client.** The dispatch step makes the job token, registers it, opens the session, and checks the result against a schema. The tool service image has Python and no SSH client, and it should not get one: it is the image that parses what the worker sends.

Two open issues fit here. The model server keeps the last job's prompt in its slot until the next job ([#32](https://github.com/sindredg/ai-security-platform/issues/32)), and its own plan says to clear it in a per-job step on the worker if dispatch adds one.

## Options

**Reaching the worker from a pod**

| Option | What changes | Cost |
| --- | --- | --- |
| A line in the host rule for `10.40.0.36:22`, and a network policy that lets only dispatch pods use it | One rule, one policy | The rule cannot tell pods apart. In its first seconds, before kube-router writes its policy, any pod can open a connection to the worker's SSH port ([0018](0018-a-host-rule-keeps-pods-off-the-internet.md)) |
| A pod on the host network | Nothing on the host | Refused by pod security in every namespace, which is the point of `K.9` |
| A service on the host that opens the session when a workflow asks | No rule | A second dispatch channel, custom, and root |

**Starting the agent's unit without root**

| Option | What the job account can do | Cost |
| --- | --- | --- |
| A socket unit owned by root that starts one sandboxed service per connection | Connect to one socket | Two unit files. systemd does the privileged part |
| A sudo rule for one command | Run that command as root | Contradicts 0012. A sudo rule is only as narrow as the command's own argument handling |
| A polkit rule for one unit name | Start and stop that unit | JavaScript rules, and transient unit names that the rule has to match |

**The dispatch image**

| Option | Cost |
| --- | --- |
| A small image of its own: the same pinned Python base, OpenSSH's client, and the dispatch script, built and scanned by the pipeline | One more image to keep current |
| The tool service image with an SSH client added | One image with two roles, one of them parsing hostile input |
| A public image with Python and SSH | Another publisher to trust, for a few hundred lines of work |

## Decision

**The host rule lets pods reach the worker's SSH port, and a policy decides which pods.** The `forward` chain of `inet aisec_pod_egress` gets one rule before its drop:

```text
ip saddr 10.42.0.0/16 ip daddr 10.40.0.36 tcp dport 22 accept
```

`dispatch-egress` in `orchestration` adds egress to `10.40.0.36/32` on TCP 22. No other pod's policy allows it. The security groups already allow TCP 22 from the orchestrator subnet to the worker, and the pod's traffic leaves with the orchestrator's address.

**A dispatch image of its own.** Built from `platform/dispatch/` by the pipeline, from the Python base the tool service uses, with OpenSSH's client from Alpine's signed index and the dispatch script, standard library only. Scanned like the tool service image, pushed from `main` only, pulled by digest. The workflow uses it for two steps:

- **dispatch:** makes a 256-bit token, registers the job with its digest ([0013](0013-a-token-per-job-and-no-cloud-identity-yet.md)), opens the session with the dispatch key and the pinned host key, writes one JSON line, keeps standard input open, and reads one JSON line back. It checks the result's size and schema, and prints it as the step's output. A missing or malformed result fails the step. It prints the agent's transcript and answer to the step's log, with control and format characters replaced, so text the model shaped cannot send escape sequences to the operator's terminal.
- **revoke:** the workflow's exit handler. It revokes the job by ID on success, failure, and stop.

The key and the host key are one secret in `orchestration`, mounted by the dispatch step and nothing else.

**On the worker, the job account only connects to a socket.** `aisec-job` is a system account with a locked password, no sudo, and a root-owned home. Its key line is root's: `from="10.40.0.4",restrict,command="/usr/local/sbin/aisec-job-runner"`. The runner checks the request and the job line's size, connects to `/run/aisec-job/agent.sock`, and relays: standard input to the socket, the socket to standard output. When the session's standard input closes, it closes its side of the socket. That is the cancel.

`aisec-agent-job.socket`, owned by root, accepts each connection itself (`Accept=yes`), allows one at a time (`MaxConnections=1`), and lets only the group `aisec-job` connect. Each connection starts one `aisec-agent-job@.service`, with the sandbox `run-agent.sh` has today: a throwaway account, a read-only file system, a private `/tmp`, a memory limit, and a time limit. Its address allow list adds the orchestrator's address to localhost. The security groups let the worker reach only the tool service's port there. The job program inside it:

1. Reads the job line from the socket and checks it: job ID, token, task, and limits. It refuses a task that Goose would read as more than text: one with template syntax, which Goose renders into the recipe before parsing it, and one that starts with `!` or `/`, a shell or slash command. The tool service's address and certificate are fixed on the worker, not taken from the job line.
2. Writes the agent's recipe, with the token, into the private `/tmp`, and starts Goose with the tool service as its one extension.
3. Watches the socket while Goose runs. An end of input before Goose ends is a cancel: it stops Goose and exits.
4. Asks the model server to erase its slot, so the next job starts with nothing of this one ([#32](https://github.com/sindredg/ai-security-platform/issues/32)).
5. Writes one JSON line with the result and exits. systemd deletes the private `/tmp` when the unit stops.

[0032](0032-erase-the-slot-before-each-job-and-refuse-on-failure.md) changes step 4: the slot is erased before the job as well, the job is refused when that fails, and the result says whether the erase after it worked.

The result carries the agent's transcript: the recipe's instructions, then each part of each message as role, type, and text, with the token taken out. Without it, a run shows counts and the last answer, and nobody can see what the agent asked for or read. The text fields are cut by the size of their JSON form, so the line stays within 64 KiB, and a last part says how many parts did not fit. The transcript goes to the socket only. The job program's standard error goes to the worker's journal, which the journal pull copies to the workspace ([0019](0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)), so nothing from the transcript is written there.

The unit's time limit is the backstop for a job that misses the cancel, as in 0012. The workflow's own deadline is shorter than the unit's and the token's.

**Checks.** `E.6` takes the new rule. New checks read the job account's key line, the socket's owner, group, and mode, and that the runner and the job program on the worker are the ones in the checkout. The worker's `G.3` and `G.4` follow the template unit's name. A procedure step shows that a pod outside dispatch is refused at the worker's port once its policy is written, and a cancel during a run, with the unit, its private `/tmp`, and the token gone afterwards.

## Trade-offs

- **Any pod can reach the worker's SSH port for its first seconds.** The host rule cannot tell a dispatch pod from another, and kube-router writes a pod's policy after the pod starts. Such a pod still needs a key that only the dispatch secret holds, and the key runs one command as an account without privileges. The worker is the untrusted side, so the reach goes toward the machine that is assumed compromised.
- **One more image to keep current.** Its Python base moves with the tool service's. Its SSH client comes from Alpine's index, unpinned, as Squid comes from Ubuntu's.
- **The socket is the dispatch interface on the worker.** Any process in the group `aisec-job` can start a job. The group has one member, and a job is a run of the agent against the tool service, which still needs a live token.
- **The job program is custom code on the untrusted side.** It parses the job line, which comes from the trusted side, and Goose's output, which it passes on as untrusted. A worker that rewrites it gains what it already had.
- **The task is written into the recipe, not passed as a recipe parameter.** Goose substitutes a recipe's parameter values into the recipe text before it parses the file, the same render that would interpret template syntax in the task. A parameter is therefore not a safer channel for untrusted text than a field is. The job writes the task into the recipe as a field and refuses template syntax in it (step 1).
- **Cancel rests on an end of input crossing two hops**: the session, then the socket. The unit's time limit and the token's expiry catch what that misses. `argo terminate`, unlike `argo stop`, skips the exit handler, and then only the expiry ends the token.
- **The transcript keeps the evidence the agent read.** It sits in the workflow's output and the dispatch pod's log on the orchestrator for the 24 hours the template keeps a workflow, readable by the operator's Argo account. That is fine for synthetic evidence. Real targets need a rule for how long it is kept first ([open items](../security/accepted-risks.md#open-items)). Goose's own system prompt and the tool list it sends the model are not in it.
- **The slot erase costs the next job its warm prompt.** On 2026-10-12 a run reused 666 of 670 prompt tokens from the run before. The first turn of each job now pays for its whole prompt, about 35 seconds at 19 tokens per second. On 2026-10-20 a job's first turn read 1004 tokens in 57.5 seconds. The erase needs the server's slot save path, which also turns on save and restore. The path is an empty directory the server cannot write, so a save fails and there is nothing to restore ([troubleshooting 12](../troubleshooting/12-slot-erase-needs-a-save-path.md)).
