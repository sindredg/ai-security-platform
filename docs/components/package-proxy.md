# Package proxy

How the worker gets security updates without getting the internet. Squid on the orchestrator forwards package downloads to two hosts and refuses everything else.

| | |
| --- | --- |
| State | Built |
| Software | Squid 7.2, from the Ubuntu `main` repository |
| Version | Not pinned. The archive drops superseded versions, and a pin would hold back security fixes |
| Listens on | `10.40.0.4:3128` only |
| Configuration | `/etc/squid/squid.conf` and a systemd sandbox, both from cloud-init |
| Decision | [0011](../decisions/0011-package-proxy-for-the-worker.md). [0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) moves it to an edge VM in milestone 3a, with the same rules for the worker. Not built |

![How a package reaches the worker: from apt on the worker to Squid on the orchestrator over TCP 3128, through the NAT gateway to two Ubuntu package hosts, with every other request refused](../diagrams/update-path.svg)

The diagram source is [`diagrams/update-path.html`](../diagrams/update-path.html).

## What it forwards

| Request | Answer |
| --- | --- |
| `GET` or `HEAD` on port 80 to `archive.ubuntu.com` or `security.ubuntu.com`, from the worker subnet | Forwarded |
| Any other host, port, or method | 403 |
| `CONNECT`, to anywhere | 403 |
| Anything from outside the worker subnet | 403 |

It caches nothing. Package integrity over HTTP relies on `apt` verifying package hashes against signed repository metadata. This prevents the proxy from substituting altered packages, but it can still block downloads.

## The worker's side

`apt` is pointed at the proxy in `/etc/apt/apt.conf.d/90aisec-proxy`. The image's unattended upgrades use it daily.

## Sandbox

Squid is the one service the untrusted side can reach. Its unit runs with no new privileges, five capabilities, read-only system directories, private `/tmp` and devices, and restricted address families and namespaces. `systemd-analyze security squid` reports `4.3 OK`. Without the sandbox it reports `9.8 UNSAFE`.

## Validation

`P` and `U` in the [validation pages](../validation/package-proxy.md).

## Limits

- **The worker can start a connection to the orchestrator.** One port, one service.
- **Two hostnames.** If the repositories move, updates stop quietly.
- **The image phones home and is refused.** The login message and subscription hooks try `motd.ubuntu.com` and an HTTPS host. Harmless, and visible in the proxy log.
- **The targets do not get this path.**
- **Outbound port 80 stays open on the orchestrator because of this path.** Fetching from the mirrors over TLS was tried and does not work with this Squid build. See [troubleshooting 03](../troubleshooting/03-proxy-cannot-fetch-upstream-over-tls.md).

## Official documentation

- [Squid configuration reference](https://www.squid-cache.org/Doc/config/)
- [`http_access`](https://www.squid-cache.org/Doc/config/http_access/)
- [systemd sandboxing options](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
- [Ubuntu automatic updates](https://documentation.ubuntu.com/server/how-to/software/automatic-updates/)
