# Package proxy

The worker's only outbound access: a proxy on the orchestrator that forwards package downloads to two hosts. The design is [ADR 0011](../decisions/0011-package-proxy-for-the-worker.md). It is the exception to T17, so it gets its own checks.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `P.1` | Squid is active | Updates stop without it | `systemctl is-active` |
| `P.2` | Squid listens on the orchestrator's private address only | Not on the mesh interface, not on every address | The only listener on 3128 is `10.40.0.4:3128` |
| `P.3` | Squid cannot gain privileges | It is the one service the untrusted side can reach | `NoNewPrivileges` is `yes` on the unit |
| `P.4` | Squid refuses a client outside the worker subnet | Nothing else gets to use it | A request from the orchestrator's own address returns 403 |
| `P.5` | The worker reaches the proxy port | The path exists | TCP to 3128 |
| `P.6`, `P.7` | The proxy serves the two package hosts | Updates work | A release file from each returns 200 |
| `P.8` | The proxy refuses another host | It is not a general outbound path | `http://example.com/` returns 403 |
| `P.9` | The proxy refuses an upload | Package hosts accept uploads. The proxy does not pass them | A `POST` to a package host returns 403 |
| `P.10` | The proxy refuses another port | Only plain package downloads | Port 8080 on a package host returns 403 |
| `P.11` | The proxy refuses a tunnel | A tunnel would carry anything | `CONNECT` returns 403 |

## Updates

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `U.1` | No security update is pending on the orchestrator | Unattended upgrades are doing their job | `apt list --upgradable` has nothing from the security suite |
| `U.2` | The mesh VPN agent is held at its pinned version | Its version moves on purpose, not with a nightly upgrade | `apt-mark showhold` on the router |
| `U.3` | `apt` on the worker uses the proxy | Otherwise it hangs for minutes and fails | `apt-config dump` |
| `U.4` | Unattended upgrades are enabled on the worker | Nobody has to remember | `systemctl is-enabled` |
| `U.5` | No security update is pending on the worker | The whole path works, daily | `apt list --upgradable` has nothing from the security suite |
| `U.6` | The mesh VPN agent does not install updates itself | The hold in `U.2` stops `apt`, not the agent's own updater. An update it applied would be code from the vendor running as root | `tailscale debug prefs` on the router, `AutoUpdate.Apply` |
| `U.7` | The mesh VPN agent is the current stable release | The hold in `U.2` and the updater off in `U.6` mean only the pin moves the agent. A pin left behind misses fixes, and nothing else would show it | The installed package version on the router equals `Version` from `pkgs.tailscale.com/stable/?mode=json`, read from the workstation. No answer from the site is a failure |
| `U.8` | Unattended upgrades are enabled on the router | As `U.4` | `systemctl is-enabled` |
| `U.9` | No security update is pending on the router | As `U.1`. The router reaches the Ubuntu mirrors through its own NAT gateway | `apt list --upgradable` has nothing from the security suite |

`U.2`, `U.6`, and `U.7` read the orchestrator until it left the mesh.

## Limits of these checks

- `U.1` and `U.5` read the package lists on the machine. If the daily refresh has stopped, the lists are stale and the check still passes. Nothing alerts on a refresh that stopped.
- `U.2` is also a gap: a held package gets no security fixes until someone moves the pin. `U.7` catches that for the mesh agent. Nothing catches it for the pinned K3s release.
