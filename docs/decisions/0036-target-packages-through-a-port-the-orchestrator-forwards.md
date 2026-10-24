# 0036. Target packages through a port the orchestrator forwards, to a Squid port of their own

Status: Accepted
Date: 2026-10-24

## Context

The targets need operating system packages: Podman, PostgreSQL, and Valkey at provisioning ([0035](0035-netbox-from-its-image-with-the-database-from-ubuntu.md)), and security updates after that. [0011](0011-package-proxy-for-the-worker.md) left this open. It gave the worker a standing path to Squid and kept the targets off it: "A target may not open a connection into the platform network". It named rebuilding from a seed as the likely answer.

Rebuilding alone does not work. First boot has to install the three packages, and a target with no path at all cannot. Something has to bring packages to the target at least once.

0011 also says what went wrong with the path it replaced. [0009](0009-one-egress-point-on-the-orchestrator-subnet.md)'s SOCKS forward reached any host the orchestrator could reach, and updates that wait for someone to run a procedure do not happen.

A forwarded port from the orchestrator has a problem of its own. Squid answers by source address, and a forward makes the target's requests arrive from the orchestrator. While a fetch window is open, the orchestrator may tunnel to GitHub, the registries, Hugging Face, and PyPI ([0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md)), and so would the target.

## Options

| Option | Path from the target | Updates | What it costs |
| --- | --- | --- | --- |
| A standing path to Squid, as the worker has | TCP 3128 to the edge, always. Two package hosts | Automatic | A rule that lets a target start a connection out of its network, for machines that are weak on purpose. The target-side allow lives in the targets root, which that side's identity can change |
| The orchestrator copies `.deb` files to the target | None | When someone runs it | The orchestrator resolves dependencies for another machine, and the archive's signatures are checked on the orchestrator, not by `apt` on the target |
| A port the orchestrator forwards over SSH, to the orchestrator's existing Squid port | Only while the session lasts, to whatever Squid allows the orchestrator | When someone runs it | During a fetch window the target can reach the upload hosts |
| A port the orchestrator forwards over SSH, to a Squid port that serves only the package mirror | Only while the session lasts. One host, `GET` and `HEAD` on port 80 | When someone runs it | One more port and rule on the edge. No unattended upgrades on the targets |

## Decision

A forwarded port to a Squid port of its own.

1. **The edge.** Squid listens on a second port, `10.45.0.4:3129`, for the targets' packages. Requests on that port get `GET` and `HEAD` on port 80 to `azure.archive.ubuntu.com` and nothing else. The fetch window's rules do not apply on it, and it refuses `CONNECT`.
2. **The rules.** One outbound allow on the orchestrator's group and one inbound allow on the edge's, both for TCP 3129 from the orchestrator's address. Both are on the platform side. No rule on the target side changes, and the targets still cannot start a connection out of their network.
3. **The session.** An update run on the orchestrator opens an SSH session to the target with a remote forward from the target's loopback to `10.45.0.4:3129`, runs `apt` on the target through it, and closes it. The target's `apt` is pointed at `127.0.0.1` on that port and finds nothing there between runs.
4. **The target's SSH.** It allows remote forwarding to the account the orchestrator logs in with, and no local forwarding. The orchestrator's client sets the forward's destination, `10.45.0.4:3129`, so a target cannot point it anywhere else. The client forwards no agent and no other port.
5. **When it runs.** At provisioning, and then as an update run the operator starts, at least at the start of each exercise and before each milestone's checks. A `U` check on each target fails when security updates are pending, as on the platform VMs.
6. **Unattended upgrades stay off on the targets.** With no path between runs, they would only fail.

## Trade-offs

- **The targets are only as current as the last run.** This is the cost 0011 named. It is accepted here because the targets are rebuilt for each exercise, hold synthetic data, and are weak on purpose anyway, and because the alternative is a standing path out of the target network. The `U` check makes a missed run visible.
- **The orchestrator gets a second port on the edge.** Root on the orchestrator could use it without a target, but the port gives it nothing beyond the mirror it already reaches on 3128.
- **During a run the target reaches the mirror as the orchestrator.** Squid's log names the orchestrator, not the target. The update run's own journal lines say which target it was.
- **Root on a target can use the forwarded port while a run lasts.** It reaches one host with `GET` and `HEAD`, the same as the worker does at all times. It cannot change where the port leads: the destination is on the orchestrator's side of the session.
- **The orchestrator logs in to a machine assumed compromised.** A key login gives the target nothing it can replay, and without agent forwarding the target cannot use the orchestrator's agent. The target sees whatever the update run types, so the run carries no secret.
- **Not a pattern for the platform.** The worker keeps its standing path from 0011. Its updates matter more, because it runs model output every day.
