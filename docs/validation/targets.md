# Targets

The NetBox VM and the lab VM. Each runs what a lab target needs and reaches nothing: no internet, no name server, no proxy port, no platform VM, and not the other target. Packages arrive only during an update run that the orchestrator starts, through one key with one command and one forwarded port ([ADR 0036](../decisions/0036-target-packages-through-a-port-the-orchestrator-forwards.md)). The threats are T27 and T28 in the [threat model](../security/threat-model.md).

The checks are the same list on each VM: `VN` on the NetBox VM, `VL` on the lab VM. The hardening checks on the same VMs are `HN` and `HL` on [host hardening](host-hardening.md). The orchestrator's side of the same paths is `E.15` and `E.16` on [containment](containment.md#the-orchestrators-side), and the effective rules on each interface are `Z.27` and `Z.28`.

Each check was seen to fail on 2026-10-24, on the live system, with a copy of the script that fed it a broken input: another file, another account, a port that listens, or a field it does not compare ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-checks-for-the-targets)). `.20`, `U.14`, and `U.15` failed on the live system before the first update run, and passed after it ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#the-update-run)). The pending count and the reboot field of `U.14` and `U.15` have not been seen to fail on their own.

## Access

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `.1` | The target is reachable through the router with the operator certificate | Administration of the target. The router hides the workstation's mesh address behind its own, so the target sees `10.45.0.36` | An SSH login from the workstation. The first field of `SSH_CLIENT`, read before `sudo`, is the router's address |
| `.2` | No plain key is authorized for the administrator | As `A.5`. sshd ignores the file for this account, and first boot removes the key Azure writes | No line in `/home/aisec/.ssh/authorized_keys` |
| `.3` | The administrator forwards nothing | An SSH forward to a target would be a path the security groups do not see | `sshd -T -C user=aisec,...` shows `no` and `any`, as `A.10` |

## The update account

The orchestrator's update key logs in to `aisec-update`. The limits are set twice, in the sshd block and on the key line, so a change to one file alone does not open the account.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `.4` | The update account has one command and one remote forward | The key's one job is the update. A local forward or a terminal would make it a way into the target network | `sshd -T -C user=aisec-update,addr=10.40.0.4` shows `authorizedkeysfile /etc/ssh/aisec-update-keys`, `allowtcpforwarding remote`, `permitlisten 127.0.0.1:3129`, `permitopen none`, `permittty no`, and the forced command |
| `.5` | The update key is restricted to the orchestrator and the one forward | `from=`, `restrict`, and `permitlisten` are the limits on the key line | One line in `/etc/ssh/aisec-update-keys`, owned by root with mode `644`, with exactly those options |
| `.6` | The update key is the orchestrator's | A key nobody holds on the orchestrator is a key someone else holds | The key on the line equals the public half of `/etc/aisec/target-update/id_ed25519` on the orchestrator, read in the orchestrator's section |
| `.7` | The update account has no other group and no password | A group would add rights. A password would be a second way in | `id -nG` and the status field of `passwd -S`: `aisec-update L` |
| `.8` | The update account may run the update command, without arguments, and nothing else | The forced command runs it through `sudo`. With an argument allowed, the caller would choose what it installs | `sudo -l -U aisec-update` lists one line, the command with `""` |
| `.9` | The update command is root's and the one in the targets checkout | The command runs as root. It has to be the reviewed one | `root 755`, and the SHA-256 of `/usr/local/sbin/aisec-target-update` equals that of `host/aisec-target-update` in the checkout `AISEC_TARGETS` names. Without that variable the check fails |

## Updates

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `.10` | apt's timers and unattended upgrades are masked | Between update runs there is no path to a mirror, so each run could only fail | `systemctl is-enabled` reads `masked` for `apt-daily.timer`, `apt-daily-upgrade.timer`, their two services, and `unattended-upgrades.service` |
| `.11` | apt uses the port an update run forwards | apt reaches the mirror through the orchestrator's session, and through nothing else | `apt-config dump` holds `Acquire::http::Proxy "http://127.0.0.1:3129"` once |
| `.12` | Nothing listens on the forwarded port between update runs | A listener there is a session left open, or a process in the forward's place that apt would trust | `ss` lists no listener on port 3129 |

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `U.14`, `U.15` | An update run in the last 7 days on the NetBox VM and on the lab VM, no security update pending, no reboot required | Nothing updates a target between runs. A missed run, a run that failed, or a kernel update not yet booted shows here, as `U.1` does on the platform VMs | apt's `update-success-stamp`, touched after each successful package list refresh, is newer than first boot's marker and at most 7 days old. The image build touched it too, so only a refresh on the VM counts. `apt list --upgradable` has nothing from the security suite, and `/run/reboot-required` does not exist. Before the first run on 2026-10-24 both read `no 0 no` |

The list `apt list` reads is the one the last run left, so the count says what was pending then, not today. The 7 days bound that.

## No way out

Each far end listens: `1.1.1.1` on 443, Azure DNS (it answers the edge), Squid on both ports (`P.2`), sshd on the orchestrator, the worker, and the other target. So a timeout is a drop, and `refused` would mean the packet got through. [Containment](containment.md#what-a-failed-connection-proves) says why.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `.13` | No connection to the internet | A compromised target cannot connect out or download a payload | TCP to `1.1.1.1:443` times out |
| `.14` | No answer from Azure DNS over TCP or UDP | A resolver is a way to pass data out | TCP to `168.63.129.16:53` times out, and a `dig` query over UDP gets no reply |
| `.15` | No connection to either proxy port on the edge | Port 3129 reaches the target only through the orchestrator's forward. 3128 is the platform's | TCP to `10.45.0.4:3128` and `10.45.0.4:3129` times out |
| `.16` | No connection to the orchestrator or the worker on 22 | A target never starts a session to the trusted side | TCP to `10.40.0.4:22` and `10.40.0.36:22` times out |
| `.17` | No connection to the other target on 22 | A compromised target does not reach the other one | TCP from the NetBox VM to `10.50.0.36:22`, and from the lab VM to `10.50.0.4:22`, times out |

## The rest

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `.18` | First boot ran to its end | First boot stops at its first error, and the marker is its last line | `/var/lib/aisec-first-boot.done` exists, owned by root |
| `.20` | apt's sources name only the mirror the target port serves | Squid's target port refuses every other host (`P.24`), so another source fails each update run ([troubleshooting 16](../troubleshooting/16-targets-apt-sources-fall-back-without-dns.md)) | Every `URIs:` and `deb` line under `/etc/apt` names `http://azure.archive.ubuntu.com/ubuntu/` |
| `.19` | No log agent | Nothing on the targets reaches Azure Monitor, so an agent there could only fail. What the targets log stays on them. Operator sessions to the targets in the audit log are an [open item](../security/accepted-risks.md#open-items) | `dpkg-query` does not report `azuremonitoragent` installed |

## NetBox

NetBox and its background worker run from one image under Podman, with PostgreSQL and Valkey on the NetBox VM's loopback ([ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)). Its port is 8443, TLS only, with a key made on the VM and a certificate the orchestrator pins ([ADR 0038](../decisions/0038-netboxs-tls-key-made-on-the-netbox-vm.md)). The rules allow the port from the orchestrator and from the consumer subnet, and from nothing else. `N.1`, `N.2`, and `N.12` to `N.14` run in the orchestrator's section, `N.3` in the router's, and the rest after the lab VM. `C.12` on [containment](containment.md#from-the-worker) is the worker's side. `N.1` to `N.11` were seen to fail on 2026-10-24, and `N.12` to `N.17` on 2026-10-25, each on the live system with a copy of the script that fed it a broken input ([worklog](../worklogs/0005-netbox-target-and-exercise-1.md#each-new-check-fails), [and](../worklogs/0005-netbox-target-and-exercise-1.md#the-checks-fail-on-broken-inputs)).

`N.14` and `N.17` are exercise 1's two deterministic checks ([ADR 0037](../decisions/0037-an-unscoped-copy-of-the-consumers-permission.md)). Both run `collectors/netbox/netbox_access.py` from this checkout with the contract from the targets checkout, `netbox/contract.json`, on its standard input. Nothing is installed on the hosts for them. Each expects the seed's result: `inventory-reader:excess inventory-reader-control:within`.

| ID | Claim | Why it matters | How it is checked |
| --- | --- | --- | --- |
| `N.1` | The orchestrator reaches NetBox over TLS with the pinned certificate, and gets no page in plain HTTP | The seed and the collectors trust this certificate and nothing else. A plain HTTP answer would carry tokens in the clear | From the orchestrator, `curl --cacert /etc/aisec/netbox/tls.crt` to `https://netbox.aisec.internal:8443/login/`, resolved to `10.50.0.4`, returns `200`. Plain HTTP to the same port returns `000`, no HTTP answer |
| `N.2` | The pinned certificate is root's and not writable by others | A certificate someone else can replace is a pin someone else chooses | `root 644` on `/etc/aisec/netbox/tls.crt` |
| `N.3` | The router's rules drop NetBox's port | The router carries operator sessions and has internet access. It reaches the targets on 22 only | TCP from the router to `10.50.0.4:8443` times out. The port listens (`N.1`), so a timeout is a drop |
| `N.4` | NetBox, its worker, PostgreSQL, and Valkey run | The service under test | `systemctl is-active` on the four units |
| `N.5` | Both containers run the image the targets checkout pins | A load does not keep the registry's digests. The image ID, which is the digest of the image's config, is what the target can compare ([ADR 0035](../decisions/0035-netbox-from-its-image-with-the-database-from-ubuntu.md)) | `podman inspect` gives each container's image ID, equal to `NETBOX_IMAGE_ID` in `netbox/image.env` in the checkout `AISEC_TARGETS` names |
| `N.6` | Both containers run as the image's `netbox` account, read-only and unprivileged | Root in the container, a writable image, or a privileged container widens what a NetBox flaw gives | `podman inspect`: `999:0 true false` for each, the user, the read-only root, and the privileged flag |
| `N.7` | No secret in the containers' environment | `podman inspect` shows the environment to anyone who can run it. The secrets are files under `/run/secrets` | No variable in either container's environment names a password, a secret, or a pepper. A failed read prints an error, not `0` |
| `N.8` | Only SSH and NetBox's port listen beyond loopback | PostgreSQL and Valkey hold the data and are meant for NetBox alone. The containers share the VM's network, so a listener they add shows here | `ss` lists the listening TCP ports on addresses other than `127.0.0.0/8` and `::1`: `22 8443` |
| `N.9` | Valkey refuses a client without the password | Every process on the VM reaches loopback | `valkey-cli ping` with no password answers `NOAUTH` |
| `N.10` | The certificate file on the NetBox VM is the one the orchestrator pins | The pin was copied through the operator's session. A new certificate on the VM shows here before clients fail | The SHA-256 fingerprint of `/etc/aisec/netbox/tls.crt` on the VM equals the orchestrator's, read in `N.2`'s section |
| `N.11` | The consumer subnet reaches NetBox's port | The consumer's path, which a fix that blocks too much would break | TCP from the lab VM to `10.50.0.4:8443` opens |
| `N.12` | NetBox takes a token's client address from the connection, not from a header | Each token is limited to its viewpoint's address. A header that NetBox believed would let any client name that address ([ADR 0039](../decisions/0039-netbox-takes-a-clients-address-from-the-connection.md)) | From the orchestrator, the probe account's token, limited to `192.0.2.1`, three times: with no header, with `X-Forwarded-For: 192.0.2.1`, and with `X-Real-IP: 192.0.2.1`. Each answer is `403` and names `10.40.0.4` as the address refused. A believed header gives `200`. An address in another form, such as `::ffff:10.40.0.4`, gives an empty name |
| `N.13` | The orchestrator's NetBox tokens are root's and closed to others | The collector's token maps who may see what | `root 700` on `/etc/aisec/netbox/tokens`, `root 600` on the collector's and the probe's token |
| `N.14` | The configured permissions give the seeded excess and an unaffected control | The configured half of the finding | On the orchestrator, with the collector's token, the collector adds up each account's enabled permissions, directly and through its groups, per object type and action, and compares the sum with the contract's grants. A grant with no constraint is excess. A constraint other than the contract's is unknown |
| `N.15` | The lab VM's NetBox tokens are root's and closed to others | The consumer's and the control account's tokens | `root 700` on `/etc/aisec/netbox/tokens`, `root 600` on both tokens |
| `N.16` | The lab VM's copy of NetBox's certificate is the one the orchestrator pins | The consumer trusts this certificate and nothing else | Its SHA-256 fingerprint equals the orchestrator's, read in `N.2`'s section |
| `N.17` | The records each token returns give the seeded excess and an unaffected control | The observed half of the finding, from the consumer viewpoint | On the lab VM, with each account's own token, the collector reads the contract's endpoints and compares the records' names and addresses with the contract's. A record the contract does not list is excess. Each expected denial is tried, and any answer other than the contract's status is excess for a `2xx` and unknown otherwise |
