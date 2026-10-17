# 0022. Short-lived SSH certificates for the operator

Status: Accepted
Date: 2026-10-16

## Context

The operator logs in to every VM with one long-lived key. Its public half is in the administrator account's `authorized_keys` on the orchestrator and the worker (`A.5`, `A.7`), and will be on the edge, the router, and the targets. A copy of that key works until someone swaps it on every VM. The swap has been run once ([credential inventory](../security/credentials.md)).

Two more gaps sit next to it:

- **The logs cannot tell sessions apart.** Routed sessions arrive with the subnet router's address, and every login uses the same key. `LogLevel VERBOSE` records the key's fingerprint, which is the same for every login.
- **[0020](0020-an-edge-vm-for-the-way-out-and-the-mesh.md) needs a tunnel that the SSH daemon refuses.** It takes the Kubernetes API off the mesh and sends the operator through an SSH tunnel to the orchestrator. The orchestrator's daemon sets `AllowTcpForwarding no` for every account.

The machine keys are a different case. The feed key, the worker log export key, and the planned dispatch key belong to accounts on the orchestrator, each limited on the worker by its account or a forced command. They are not part of this record. [0026](0026-the-feed-key-gets-its-own-account-on-the-worker.md) found that the feed key is not limited this way, and moves it to an account of its own.

OpenSSH on the VMs is 10.2p1, read on 2026-10-16. User certificates, `source-address`, and key revocation lists have been in OpenSSH for many years.

## Options

| Option | A stolen credential works for | Identity in the log | Runs on the VMs | Cost |
| --- | --- | --- | --- | --- |
| Keep the static key | Until it is swapped on every VM | The key's fingerprint, the same for every login | Nothing new | Nothing |
| A static key held on a hardware security key (`sk-ssh-ed25519`) | As long as the attacker holds the device | The same fingerprint | Nothing new | A device. It does not expire anything |
| Microsoft Entra login for Linux VMs | A short-lived certificate from Entra | The Entra user | An extension, and a login path to Entra from each VM | The worker has no way out, and 0020 gives the orchestrator none. A login would depend on Entra being reachable from the VM |
| Tailscale SSH | The tailnet session | The tailnet user | The mesh agent on each VM | 0020 takes the agent off the orchestrator, and the worker and targets never had it |
| A certificate service such as step-ca or Vault | A short-lived certificate | A name per certificate | A service to host, back up, and patch | A new trusted service for one operator |
| OpenSSH's own certificate authority, the key kept by the operator | The certificate's lifetime | The certificate's key ID and serial | One line in the daemon's configuration and one public key file | One signing step per working day |

## Decision

The administrator account accepts only certificates signed by the operator's SSH certificate authority, valid for at most 12 hours.

**The certificate authority**

- An Ed25519 key pair, made by the operator, protected by a passphrase. The private half never touches a VM or the repository. It is used once a day to sign, and kept apart from the daily login key.
- The public half goes to each VM as `/etc/ssh/aisec-user-ca.pub`, from the templates that first boot reads. A rotation writes the new file on the running VMs and is a procedure step.

**The certificates**

- Signed for the operator's login key with `ssh-keygen -s`, for 12 hours, principal `aisec-operator`, and a key ID that names the day.
- Critical option `source-address`: the router subnet `10.45.0.32/27`, where routed sessions come from ([0025](0025-the-mesh-node-on-its-own-vm.md)), and `100.64.0.0/10`, the tailnet range, for logins to the router itself. A certificate copied to any other machine is refused.
- Extensions: a terminal, and port forwarding. No agent forwarding, no X11.

**The SSH daemon, on every VM**

- `TrustedUserCAKeys /etc/ssh/aisec-user-ca.pub`.
- `RevokedKeys /etc/ssh/aisec-revoked.krl`, a key revocation list, empty at first. Revoking a certificate before it expires adds its serial.
- For the administrator account: `AuthorizedPrincipalsFile` lists `aisec-operator`, and `AuthorizedKeysFile none`. A plain key, the old operator key included, is refused.
- Other accounts keep their keys and forced commands as they are.

**The tunnel**

On the orchestrator only, the administrator account gets `AllowTcpForwarding local` and `PermitOpen 127.0.0.1:6443`. Every other account, and every other VM, keeps `AllowTcpForwarding no`. The operator runs `kubectl` through `ssh -L 6443:127.0.0.1:6443`. The API server listens on all addresses (`*:6443`), so loopback reaches it.

**Checks**

- `sshd -T` shows the CA file, the revocation list, and, for the administrator account, `authorizedkeysfile none`, on each VM.
- `sshd -T -C user=aisec` on the orchestrator shows `allowtcpforwarding local` and `permitopen 127.0.0.1:6443`, and the same query on the other VMs shows `allowtcpforwarding no`.
- A login with the old static key is refused. A login with an expired certificate is refused. A forward to any port but 6443 on the orchestrator is refused. These are procedure steps, because they need a key or a certificate the script does not hold.
- `A.5` and `A.7` change: the administrator account has no key line. The machine keys stay in their own accounts.

## Trade-offs

- **The certificate authority's key is the new prize.** Whoever holds it and the passphrase signs certificates until the public half is replaced on every VM. That is the same reach the static key has today, but the key is used once a day instead of on every login, and it can live on a different device from the daily key. Where it lives is the operator's choice, outside this project, as the workstation is.
- **A stolen certificate works for up to 12 hours,** and only from the router's subnet or the tailnet. Revoking it sooner means writing the revocation list on every VM, which is a procedure, not an instant action.
- **One more step a day.** The operator signs a certificate before the first login. Forgetting it is a refused login, not an open door.
- **Clock skew can refuse a valid certificate.** The VMs keep time from the host's clock device (`/dev/ptp_hyperv`, read on the orchestrator on 2026-10-16). A certificate signed on a fast workstation clock can be not yet valid for a minute.
- **Break-glass does not use SSH.** If the authority's key is lost, the way back is Azure's run-command or serial console, which needs the Owner account (T03). The runbook writes a new CA file that way.
- **Host keys stay pinned, not certified.** The operator's `known_hosts` holds each VM's host key, and a rebuild changes it. Host certificates would remove that step. Not worth a second authority while there are three VMs.
- **The tunnel is a port forward on the trusted machine.** It opens one port, for one account, to loopback. Root on the orchestrator could already reach the API, so it adds nothing for an attacker who is already there.
- **The machine keys are unchanged.** They are long-lived, held by root-owned accounts on the orchestrator, and limited by forced commands on the worker. Root on the orchestrator has them. That stays as [0012](0012-dispatch-over-ssh-with-a-forced-command.md) and [0019](0019-how-the-audit-lines-and-the-worker-journal-are-copied.md) decided.
