# Package proxy

The orchestrator's and the worker's only outbound access: Squid on the edge VM, which forwards package downloads, and tunnels for the orchestrator during a fetch window. The design is [ADR 0011](../decisions/0011-package-proxy-for-the-worker.md) for the worker and [ADR 0020](../decisions/0020-an-edge-vm-for-the-way-out-and-the-mesh.md) for the edge and the orchestrator. It is the exception to T05 and T17, so it gets its own checks.

## On the edge

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `P.1` | Squid is active | Updates and fetches stop without it | `systemctl is-active` |
| `P.2` | Squid listens on the edge's private address only | Not on every address | The only listener on 3128 is `10.45.0.4:3128` |
| `P.3` | Squid cannot gain privileges | It is the one service the orchestrator and the worker can reach on the edge | `NoNewPrivileges` is `yes` on the unit |
| `P.4` | Squid refuses a client outside the two subnets | Nothing else gets to use it | A request from the edge's own address returns 403 |
| `P.16` | No fetch window is open | The checks run between windows. A window left open is an upload path left open (T40) | `/run/aisec/fetch-window.conf` is root's, mode `644`, and empty, and the close timer is `inactive`. During a window this check fails, on purpose |
| `P.17` | The fetch window command is root's and the one in this checkout | Root on the edge is the only one who opens a window. The command has to be the reviewed one | Owner and mode `root 700`, and the SHA-256 of `/usr/local/sbin/aisec-fetch-window` equals that of `edge/aisec-fetch-window` |
| `P.18` | Squid's fetch host list is the one in this checkout | A name added on the edge alone would open a host nobody reviewed | The SHA-256 of `/etc/squid/aisec-fetch-hosts` equals that of `edge/fetch-hosts` |
| `P.19` | Squid's configuration is root's and the edge template's | An `http_access allow` added on the edge alone would pass every other check while no window is open | Owner and mode `root 644`, and the SHA-256 of `/etc/squid/squid.conf` equals that of the file `infra/platform/cloud-init/edge.yaml.tftpl` writes, rendered by Terraform (`.github/scripts/render-cloud-init-file.sh`) with the edge, orchestrator, and worker addresses the check script holds. The script's addresses are constants, not read from Terraform, so a change to the network fails this check until they move with it. The check needs `terraform` on the workstation, and fails without it |

## From the worker

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `P.5` | The worker reaches the proxy port on the edge | The path exists | TCP to `10.45.0.4:3128` |
| `P.6`, `P.7` | The proxy serves the two package hosts | Updates work | A release file from each returns 200 |
| `P.8` | The proxy refuses another host | It is not a general outbound path | `http://example.com/` returns 403 |
| `P.9` | The proxy refuses an upload | Package hosts accept uploads. The proxy does not pass them | A `POST` to a package host returns 403 |
| `P.10` | The proxy refuses another port | Only plain package downloads | Port 8080 on a package host returns 403 |
| `P.11` | The proxy refuses a tunnel | A tunnel would carry anything | `CONNECT` returns 403 |

## From the orchestrator

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `P.12` | Squid is not installed on the orchestrator | The proxy moved. A leftover is a service nobody checks | `dpkg-query` finds no installed `squid` |
| `P.13` | The edge serves the orchestrator's package mirror | Its unattended upgrades keep working | A release file from `azure.archive.ubuntu.com` returns 200 |
| `P.14` | The edge refuses the orchestrator another host | Its standing list is one mirror and nothing else | A release file from `archive.ubuntu.com`, the worker's host, returns 403 |
| `P.15` | The edge refuses the orchestrator a tunnel while no window is open | Every upload host is behind a tunnel | `CONNECT` to `github.com:443` returns 403. During a window this check fails, on purpose |

## Updates

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `U.1` | No security update is pending on the orchestrator | Unattended upgrades are doing their job | `apt list --upgradable` has nothing from the security suite |
| `U.2` | The mesh VPN agent is held at its pinned version | Its version moves on purpose, not with a nightly upgrade | `apt-mark showhold` on the router |
| `U.3` | `apt` on the worker uses the edge | Otherwise it hangs for minutes and fails | `apt-config dump` names `http://10.45.0.4:3128` |
| `U.4` | Unattended upgrades are enabled on the worker | Nobody has to remember | `systemctl is-enabled` |
| `U.5` | No security update is pending on the worker | The whole path works, daily | `apt list --upgradable` has nothing from the security suite |
| `U.6` | The mesh VPN agent does not install updates itself | The hold in `U.2` stops `apt`, not the agent's own updater. An update it applied would be code from the vendor running as root | `tailscale debug prefs` on the router, `AutoUpdate.Apply` |
| `U.7` | The mesh VPN agent is the current stable release | The hold in `U.2` and the updater off in `U.6` mean only the pin moves the agent. A pin left behind misses fixes, and nothing else would show it | The installed package version on the router equals `Version` from `pkgs.tailscale.com/stable/?mode=json`, read from the workstation. No answer from the site is a failure |
| `U.8` | Unattended upgrades are enabled on the router | As `U.4` | `systemctl is-enabled` |
| `U.9` | No security update is pending on the router | As `U.1`. The router reaches the Ubuntu mirrors through the edge network's NAT gateway | `apt list --upgradable` has nothing from the security suite |
| `U.10` | `apt` on the orchestrator uses the edge | It has no other way to its mirror | `apt-config dump` names `http://10.45.0.4:3128` |
| `U.11` | containerd pulls images through the edge | A pull without it fails, and only on the next deploy | `HTTPS_PROXY` in containerd's environment is the edge |
| `U.12` | Unattended upgrades are enabled on the edge | As `U.4` | `systemctl is-enabled` |
| `U.13` | No security update is pending on the edge | As `U.1`. The edge is the most exposed machine | `apt list --upgradable` has nothing from the security suite |

`U.2`, `U.6`, and `U.7` read the orchestrator until it left the mesh.

## Limits of these checks

- `P.15` and `P.16` cannot show that a window opens. Opening one changes state, and the checks only read. The [edge runbook](../runbooks/edge-vm.md#open-a-fetch-window) has that step.
- `U.1` and `U.5` read the package lists on the machine. If the daily refresh has stopped, the lists are stale and the check still passes. Nothing alerts on a refresh that stopped.
- `U.2` is also a gap: a held package gets no security fixes until someone moves the pin. `U.7` catches that for the mesh agent. Nothing catches it for the pinned K3s release.
