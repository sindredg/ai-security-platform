# 17. NetBox sees an IPv4 client as an IPv6 address, and refuses its token

Date: 2026-10-25
Milestone: 4, NetBox target and exercise 1 investigation

## Symptom

The first seed run, at 06:43 UTC, stopped at its first request. NetBox refused the seeding token, which is limited to the orchestrator's address, from the orchestrator:

```text
GET /api/tenancy/tenants/?slug=tenant-a&limit=1000: 403 {"detail":"Source IP ::ffff:10.40.0.4 is not permitted to authenticate using this token."}
```

The address probe seconds before had printed `403:` with no address after it, where `403:10.40.0.4` was expected. Its pattern reads digits and dots only.

## Cause

Confirmed on the NetBox VM. netbox-docker's launch script starts Granian with `--host "::"`, and the listener was `*:8443`, one socket for IPv6 and IPv4. On that socket an IPv4 client's address is the IPv4-mapped form, `::ffff:10.40.0.4`. NetBox reads that as the client address and checks it with netaddr. In the image's Python, netaddr 1.3.0:

```text
IPAddress("::ffff:10.40.0.4") in IPNetwork("10.40.0.4/32")  ->  False
IPAddress("10.40.0.4") in IPNetwork("10.40.0.4/32")         ->  True
```

So no token limited to an IPv4 network works on this socket. NetBox's install on 2026-10-24 logged `Listening at: https://:::8443`, and the checks then sent no token.

## Fix

`GRANIAN_EXTRA_ARGS=--host=0.0.0.0` in the targets repository's `netbox/netbox.env` ([ADR 0039](../decisions/0039-netbox-takes-a-clients-address-from-the-connection.md)). The launch script adds these arguments after its own. Before the change, Granian's own parser was run in the container on the launch script's arguments with the extra one: it kept `'0.0.0.0'`, the last `--host`. The install script ran again at 06:49 UTC.

## Verification

After the install, `ss` lists `0.0.0.0:8443` only, and Granian logs `Listening at: https://0.0.0.0:8443`. The probe prints `403:10.40.0.4` three times, so `N.12` passes. The seed's next run went through with the same kind of token, and every check passed ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-seed-and-the-two-checks)).
