# 0026. The feed key gets its own account on the worker

Status: Proposed
Date: 2026-10-16

Supersedes two parts of [0022](0022-short-lived-ssh-certificates-for-the-operator.md): that the feed key is left as it is, and the `source-address` of a certificate until the router exists. The rest of 0022 stands.

## Context

[0022](0022-short-lived-ssh-certificates-for-the-operator.md) sets `AuthorizedKeysFile none` for the administrator account on every VM. It describes the machine keys as "each limited on the worker by its account or a forced command", and leaves them out. The feed key does not fit that description. Read on the live worker on 2026-10-16:

- The feed key is a plain line in the administrator account's `authorized_keys`, beside the operator key. No `restrict`, no `from=`, no forced command.
- The administrator account has `NOPASSWD: ALL` in sudo.

So the key that first boot makes on the orchestrator is root on the worker. Whoever is root on the orchestrator is root on the worker too, with nothing in the worker's log to tell that login from the operator's. 0022 would also cut it off: with `AuthorizedKeysFile none`, the feed key is refused, and `push.sh` for the model server and the agent runtime stops working.

The feed carries two kinds of content. The staged downloads are large (about 9 GB for the model server) and come from the orchestrator, the one machine that downloads. The scripts and the pin lists come from the repository. Today both go through the orchestrator, so `build-model.sh` says in its own comment that its check on the worker "does not catch an orchestrator that changed a file and its checksum together".

The other gap is about the order of the work. 0022 names the router subnet in each certificate's `source-address`, and the router does not exist until the edge and router slice of milestone 3a. Until then, routed sessions reach the worker from the orchestrator's address, `10.40.0.4`, after the mesh node translates them.

## Options

| Option | What the feed key can do on the worker | Changes | Cost |
| --- | --- | --- | --- |
| Keep the key in the administrator account, read from a root-owned file with `restrict` and `from=` | Anything, as root, through sudo | One `AuthorizedKeysFile` line | Contradicts 0022's own premise. A compromised orchestrator stays root on the worker |
| The same, with a forced command | Only the command, but run by an account with sudo. A flaw in the command is root | A command and a key line | The command is the whole limit |
| An account of its own, with no sudo and a forced command that only unpacks into its own directory | Write files into one directory, as an account that owns nothing else | A command, an install script, two scripts, the runbooks | The scripts reach the worker another way. Below |
| Drop the feed and copy everything from the workstation | Nothing | The runbooks | 9 GB through the mesh for every rebuild, from a machine this project does not manage |

## Decision

The feed key logs in only to `aisec-feed`, an account of its own on the worker, and only runs `aisec-feed-receive`.

**The account**

- A system account with a locked password and no sudo. Its shell is `bash`, because sshd runs a forced command through it.
- Its home is root-owned, `0755`. The account writes only to one directory per component: `/home/aisec-feed/model-server` and `/home/aisec-feed/agent-runtime`. Nothing it writes is read by the account's shell at login.
- The key line is root-owned, `0644`: `from="10.40.0.4",restrict,command="/usr/local/sbin/aisec-feed-receive"`, as the log export key has ([0019](0019-how-the-audit-lines-and-the-worker-journal-are-copied.md)).

**The command**

It accepts two requests and nothing else:

- `receive <component>` unpacks a tar stream from standard input into `<component>/stage`, without owners or permissions from the archive.
- `size <component>` prints the size of that directory.

`<component>` is `model-server` or `agent-runtime`, matched whole. Any other request is refused with exit status 2.

**The scripts come from the operator**

The operator copies the component's scripts and pin list from a checkout straight to the worker, with a certificate login, as the other runbook steps already do. The feed brings only the staged downloads. `build-model.sh` and `install-agent.sh` check every staged file against the pin list before they use it, so that check is now against the repository's pins, not against a list the orchestrator sent with the files.

**Until the router exists**

Certificates are signed with `source-address=100.64.0.0/10,10.40.0.4/32`: the tailnet range for logins to the orchestrator, and the orchestrator's address for routed logins to the worker. The edge and router slice of milestone 3a changes the signing command to the router subnet that 0022 names, and the old certificates expire within 12 hours. No VM setting changes with it.

## Trade-offs

- **A compromised orchestrator still supplies the bytes.** It can send a staged file that does not match its pin, and the worker's scripts refuse it. It can fill the worker's disk. It can no longer run anything on the worker.
- **The operator still runs the install scripts as root,** on files the orchestrator sent. The scripts check the files against pins from the operator's checkout first. A flaw in a checked file's format parser (the model converter, `tar`) is still reached. The converter already runs in a sandbox with its own account ([0015](0015-build-the-model-file-on-the-worker.md)).
- **One more copy step per component.** The scripts go from the workstation to the worker, then the staged files go from the orchestrator. Two steps where there was one.
- **The orchestrator's address is in every certificate until the router exists.** A certificate copied to the orchestrator works on the worker from there. Root on the orchestrator could already reach the worker as root through the feed key, so this is no new reach, and it ends with the router slice.
- **The targets need the same account.** The feed key is planned for the targets too. The target images take the same install script when they exist, in milestone 4.
