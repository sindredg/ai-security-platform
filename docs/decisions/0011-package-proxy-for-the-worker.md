# 0011. A package proxy for the worker, on the orchestrator

Status: Accepted
Date: 2026-10-11

Supersedes one part of [0009](0009-one-egress-point-on-the-orchestrator-subnet.md): how the AI worker gets operating system packages. The rest of 0009 stands.

## Context

0009 gave the worker its packages through a SOCKS forward, carried by an SSH session that the orchestrator opens. The path exists only while someone holds it open.

Milestone 2 showed what that costs. The worker booted from an image four days old and has had no update since. An audit of the worker could not even tell what was outdated: its package lists were the ones the image shipped with. Updates that depend on someone running a procedure do not happen on the day a fix is published. They happen when someone remembers.

The SOCKS forward has a second problem. While it is open it reaches any host the orchestrator can reach, on any port the orchestrator's rules allow. It is a real internet path on a machine that is not supposed to have one, held open for as long as an update takes.

An unpatched machine that runs untrusted model output is the worse risk of the two.

## Options

| Option | Path from the worker | Updates | Notes |
| --- | --- | --- | --- |
| Keep the SOCKS forward from 0009 | None, except during an update session. Then any host | When someone runs them | Nothing to build. The worker can never start a connection |
| Allowlisting proxy on the orchestrator | One port on the orchestrator, always. Through it, two package hosts | Automatic, on the image's own schedule | One more service on the orchestrator, reachable from the untrusted side |
| Caching package mirror on the orchestrator | The same port | Automatic | A cache saves nothing for one machine, and the common cache tool is community-maintained |
| Rebuild the worker from a newer image instead of patching | None | When an image is published and someone rebuilds | Loses the model and everything installed on the worker each time |

0009 rejected the proxy because "the worker gains a second destination, and package and model hosts accept uploads as well as downloads". Both points get an answer below.

## Decision

The orchestrator runs a forward proxy for the worker's package manager. The worker updates itself. [0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md) moves the proxy to an edge VM, with the same rules for the worker.

- **Software:** Squid, from the Ubuntu `main` repository, so it gets the distribution's security updates. It caches nothing.
- **What it accepts:** connections from the worker subnet only, on the orchestrator's private address, port 3128.
- **What it forwards:** `GET` and `HEAD` requests on port 80 to `archive.ubuntu.com` and `security.ubuntu.com`. Everything else is refused: other hosts, other ports, other methods, and `CONNECT`. No uploads, and no tunnel.
- **Network rules:** one outbound allow on the worker subnet and one inbound allow on the orchestrator subnet, both for TCP 3128 between those two subnets. The worker's denies for the internet, the target network, and Azure DNS stay where they are, above the allow.
- **The worker:** `apt` is pointed at the proxy. The image's unattended upgrades do the rest.
- **The SOCKS forward is gone.** The worker's SSH daemon refuses TCP forwarding again.

The targets do not get this path. A target may not open a connection into the platform network, and that rule is worth more than convenient patching of machines that are weak on purpose. How they are kept current is a milestone 4 decision. Rebuilding them from a seed is the likely answer. [0036](0036-target-packages-through-a-port-the-orchestrator-forwards.md) decides it.

Plain HTTP is enough here. `apt` verifies every package against signed repository metadata, so the proxy cannot change what gets installed without the signature check failing.

## Trade-offs

- **The worker can now start a connection to the orchestrator.** One port, one service. A flaw in Squid's request handling is reachable from the untrusted side. Squid runs as its own unprivileged user, and it is patched by the same unattended upgrades as the rest of the orchestrator.
- **The path is always there.** 0009's version existed only during an update. This one is narrower and permanent.
- **A turned worker can send requests to two Canonical hosts.** Request paths and headers reach their logs. That is a few bytes per request to a party with no reason to collude. It is not a way to reach a server the attacker controls.
- **The allowlist is by hostname, and the worker has no DNS.** The proxy resolves the names. If Canonical moves the repositories to other hostnames, updates stop until the list changes.
- **The Squid package is not pinned to an exact version.** The archive drops superseded versions, so an exact pin would break the next rebuild, and pinning would hold back security fixes. Every other pin in this project is exact.
- **Unattended upgrades change the worker without anyone looking.** A bad update lands by itself. The alternative, on this evidence, is no updates.
- **Two mechanisms now.** The worker pulls through a proxy. The targets will be fed some other way.
