# 0039. NetBox takes a client's address from the connection, on an IPv4 socket

Status: Accepted
Date: 2026-10-25

## Context

Every NetBox token in exercise 1 is limited to one address ([0037](0037-an-unscoped-copy-of-the-consumers-permission.md)): the consumer's and the control account's to the lab VM, the collector's and the seeding token to the orchestrator. That limit ties a token to its viewpoint. The observed check means something only if the consumer's token answers from the consumer viewpoint and from nowhere else.

NetBox checks a token's allowed addresses against the client address it reads from the request. Read in the pinned image, NetBox v4.7.3 in `netbox-docker` 5.1.1, on 2026-10-25:

- **NetBox's setting.** `HTTP_CLIENT_IP_HEADERS` defaults to `X-Real-IP`, then `X-Forwarded-For`, then the connection's address. The first one present wins.
- **netbox-docker's module.** Granian, the application server, loads `netbox.granian:application`. netbox-docker's `granian.py` wraps NetBox in Granian's proxy-header middleware, which lets any peer in `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7`, and `fe80::/10` set the client's address with `X-Forwarded-For`.
- **The socket.** The launch script passes `--host "::"` to Granian. On that socket an IPv4 client's address is the IPv4-mapped form, `::ffff:10.40.0.4`. NetBox compares addresses with netaddr, and `::ffff:10.40.0.4` is not in `10.40.0.4/32`.

Both header paths assume a proxy in front that sets the header. None sits in front of this NetBox, so the client sets it. On the live system, a token limited to `192.0.2.1`, a documentation address that no host has, was refused from the orchestrator with no header, and accepted with either header naming `192.0.2.1`. The socket failed the other way: the seeding token, limited to `10.40.0.4/32`, was refused from `10.40.0.4` ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-seed-and-the-two-checks)).

## Options

| Option | What it gives | What it costs |
| --- | --- | --- |
| A reverse proxy in front, from Ubuntu `main`, which sets the header. NetBox trusts that proxy only | The layout NetBox's documentation assumes | One more service on the target to configure and patch, and the TLS key moves to it ([0038](0038-netboxs-tls-key-made-on-the-netbox-vm.md)) |
| NetBox reads the connection only, Granian serves NetBox unwrapped, on an IPv4 socket | Three small changes, in files this project owns | Tied to netbox-docker's layout: the module's path, the launch script's extra arguments, and the configuration directory. An image move can undo them |
| Tokens without an address limit. The security groups are the only limit | Nothing to change in the image | The groups let two sources in. A token copied from one to the other works from both, and the observed check cannot show that a token answers only from its viewpoint |

## Decision

NetBox reads the connection only, on an IPv4 socket.

1. **The setting.** `HTTP_CLIENT_IP_HEADERS` names the connection's address only, in a file that both units mount into netbox-docker's configuration directory.
2. **The module.** A `granian.py` that hands Granian NetBox's application without the middleware, mounted over netbox-docker's.
3. **The socket.** `GRANIAN_EXTRA_ARGS=--host=0.0.0.0`. The launch script adds these arguments after its own, and Granian keeps the last `--host`.
4. **A probe proves it on every check run.** An account with no permission has a read-only token limited to `192.0.2.1`. From the orchestrator, NetBox has to refuse it three times, with no header and with each header, and name the orchestrator's own address each time (`N.12`).

## Trade-offs

- **netbox-docker's layout is a dependency.** The three changes rest on a module path, a variable the launch script expands, and a directory whose every `.py` file the configuration reads. An image move has to read them again. `N.12` fails if a header counts again, and if the address is not plain IPv4. Both were seen on 2026-10-25.
- **Not seen apart.** The setting and the module went in together. Whether Granian's middleware alone would have trusted the header was not tried: the peer's address was the mapped form, which its list may not match.
- **No IPv6.** No network in the project has IPv6. A target that needs it gets a new record.
- **A proxy later changes this.** With a proxy in front, the header from that proxy is the one to trust, and the setting names it, in a new record.
- **One more account.** The probe account has no permission, and its token works from no host. It exists so that the check can fail.
