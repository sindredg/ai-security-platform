# Package proxy

The platform's one way to the internet for the orchestrator and the worker. Squid on the edge VM forwards package downloads to the Ubuntu mirrors, and, while the operator holds a fetch window open, tunnels from the orchestrator to the build and deploy hosts. A second port serves the targets' packages, which the orchestrator forwards to a target during an update run ([ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)). It refuses everything else.

| | |
| --- | --- |
| State | Built. Verified by `P` and `U` on 2026-10-17 ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-edge-vm)). Since 2026-10-18, `P.20` to `P.22` also show that Squid runs the reviewed configuration, not only that the file is the reviewed one ([worklog](../worklogs/0004-edge-network-and-monitoring.md#before-the-ai-part)). The targets' port is built since 2026-10-24, verified by `P.23` to `P.29` ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-targets-package-port)) |
| Runs on | The edge VM, `Standard_B2als_v2` at `10.45.0.4` in Denmark East. Squid and nothing else: no mesh agent, no workload, no credential |
| Software | Squid 7.2, from the Ubuntu `main` repository |
| Version | Not pinned. The archive drops superseded versions, and a pin would hold back security fixes |
| Listens on | `10.45.0.4:3128`, and `10.45.0.4:3129` for the targets' packages. Nothing else |
| Configuration | `/etc/squid/squid.conf`, the fetch host list from `edge/fetch-hosts`, and a systemd sandbox, all from cloud-init (`infra/platform/cloud-init/edge.yaml.tftpl`) |
| Decisions | [0011](../decisions/0011-package-proxy-for-the-worker.md) for the worker's rules, [0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) for the edge VM, the orchestrator's rules, and the fetch window, [0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md) for the targets' port |

![How a package reaches the worker: from apt on the worker to Squid on the edge VM over TCP 3128, through the edge network's NAT gateway to two Ubuntu package hosts, with every other request refused](../diagrams/update-path.svg)

The diagram source is [`diagrams/update-path.html`](../diagrams/update-path.html).

## What it forwards

| Request | From | Answer |
| --- | --- | --- |
| `GET` or `HEAD` on port 80 to `archive.ubuntu.com` or `security.ubuntu.com` | The worker subnet | Forwarded |
| `GET` or `HEAD` on port 80 to `azure.archive.ubuntu.com` | The orchestrator, `10.40.0.4` | Forwarded |
| `CONNECT` on port 443 to a host in `edge/fetch-hosts` | The orchestrator, while a fetch window is open | Tunnelled |
| `GET` or `HEAD` on port 80 to `azure.archive.ubuntu.com`, on port 3129 | The orchestrator, for a target during an update run | Forwarded. A fetch window does not change this port's answers |
| Anything else on port 3129 | Either | 403 |
| Any other host, port, or method, and any other `CONNECT` | Either | 403 |
| Anything | Any other address, the edge itself included | 403 |

It caches nothing. Package integrity over HTTP relies on `apt` verifying package hashes against signed repository metadata. This prevents the proxy from substituting altered packages, but it can still block downloads.

Squid resolves every name. Neither client needs DNS, and both are denied Azure DNS.

## The fetch window

Builds and deploys fetch from GitHub, the two container registries, Hugging Face, and PyPI. All of them accept uploads from anyone with an account, so none of them is on a standing list. The operator opens them for one build or deploy:

```bash
sudo aisec-fetch-window open 30   # on the edge, over SSH through the router
sudo aisec-fetch-window status
sudo aisec-fetch-window close
```

- **Root on the edge only.** The orchestrator has no rule that reaches the edge on SSH, so root on the orchestrator cannot open a window.
- **At most 60 minutes.** A transient systemd timer closes the window at the time `open` prints.
- **Closing ends the tunnels.** A close ends every tunnel still open, and Squid logs each with its host and bytes. A download on port 80 goes on. Tested on the live system on 2026-10-23 ([worklog](../worklogs/0003-toolchain-integration.md#fix-closing-a-fetch-window-ends-its-tunnels)).
- **Logged.** Every open and close goes to the edge's journal under `aisec-fetch-window`, with the operator's name. Every request goes to Squid's access log.
- **A reboot closes it.** The window is one line in a file under `/run`, which Squid includes.

The host list, `edge/fetch-hosts`, holds the names the orchestrator fetches from and the hosts they redirect to, as read from Squid's log on 2026-10-17. A host missing from it shows as `TCP_DENIED` in the log during a window. The [edge runbook](../runbooks/edge-vm.md#open-a-fetch-window) has the procedure.

## The clients' side

| Client | Setting |
| --- | --- |
| Worker | `apt` in `/etc/apt/apt.conf.d/90aisec-proxy`. The image's unattended upgrades use it daily |
| Orchestrator | `apt` in the same file. `http_proxy` and `https_proxy` in `/etc/environment` for the operator's fetch scripts. `CONTAINERD_HTTPS_PROXY` in `k3s.service.env` for image pulls, so K3s and the kubelet have no proxy |

## Sandbox

Squid is the one service the orchestrator and the worker can reach on the edge. Its unit runs with no new privileges, five capabilities, read-only system directories, private `/tmp` and devices, and restricted address families and namespaces. `systemd-analyze security squid` reports `4.3 OK` on the edge, read on 2026-10-17. On the orchestrator, the same drop-in gave `4.3 OK`, and `9.8 UNSAFE` without it.

## Validation

`P` and `U` in the [validation pages](../validation/package-proxy.md).

## Limits

- **The orchestrator and the worker can start a connection to the edge.** One port, one service.
- **During a window the upload hosts are open.** A compromised orchestrator can push data to an account of its own on a listed host while the window lasts (T40).
- **A tunnel that opens just after the close is not ended.** The close ends Squid's tunnels one second after the reload. A request allowed before the reload whose connection opens after that second keeps its tunnel. Reasoned, not seen.
- **Squid sees the host name and the bytes, not the content.** TLS is not inspected.
- **Hostnames, not addresses.** If the repositories or the CDNs move, fetches stop until the list changes.
- **The image phoned home and was refused.** The login message and Ubuntu Pro's apt hook asked for `motd.ubuntu.com`, `changelogs.ubuntu.com`, and `esm.ubuntu.com`, and on the orchestrator each refusal raised `squid-refused-orchestrator`, Sev1. Since 2026-10-19 the units behind them are masked on every VM, checked by `.21` ([#124](https://github.com/sindredg/ai-security-platform/issues/124), [worklog](../worklogs/0003-toolchain-integration.md#ubuntus-own-requests)). Whether the refusals have stopped shows in the proxy log after the next daily apt run.
- **The edge is a single point of failure** for packages and fetches. When it is down, nothing on the platform updates.
- **The targets do not get this path.**
- **Outbound port 80 stays open on the edge because of the mirrors.** Fetching from them over TLS was tried and does not work with this Squid build. See [troubleshooting 03](../troubleshooting/03-proxy-cannot-fetch-upstream-over-tls.md).

## Official documentation

- [Squid configuration reference](https://www.squid-cache.org/Doc/config/)
- [`http_access`](https://www.squid-cache.org/Doc/config/http_access/)
- [systemd sandboxing options](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
- [`systemd-run`](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html)
- [K3s: configuring an HTTP proxy](https://docs.k3s.io/advanced#configuring-an-http-proxy)
- [Ubuntu automatic updates](https://documentation.ubuntu.com/server/how-to/software/automatic-updates/)
