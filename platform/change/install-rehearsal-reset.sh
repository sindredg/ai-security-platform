#!/bin/bash
# Installs the rehearsal copy's reset on the lab VM (ADR 0044): the command,
# and the account the orchestrator runs it through. Run as root, from a folder
# that holds aisec-rehearsal-reset, after the copy is seeded and its dump is
# taken.
#
#   install-rehearsal-reset.sh "ssh-ed25519 AAAA... aisec-rehearsal-reset"
#
# The key is the public half install-change.sh printed on the orchestrator.
# The account follows the observer's pattern (ADR 0040): a key file root owns,
# the orchestrator's address and restrict on the key line, no forwarding, no
# TTY, and one command through sudo. Run again, it writes every file whole,
# so another key replaces the old one.
set -euo pipefail

orchestrator=10.40.0.4
here="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ "$#" -eq 1 ] || { echo "usage: install-rehearsal-reset.sh PUBLIC_KEY" >&2; exit 2; }
key=$1
if ! [[ $key =~ ^ssh-ed25519\ [A-Za-z0-9+/]+={0,2}(\ [A-Za-z0-9@._-]+)?$ ]]; then
  echo "not an ed25519 public key: $key" >&2
  exit 1
fi
[ -f "$here/aisec-rehearsal-reset" ] || { echo "missing: $here/aisec-rehearsal-reset" >&2; exit 1; }
[ -f /var/lib/aisec/rehearsal/seed.dump ] || { echo "no seed dump yet" >&2; exit 1; }

if ! id aisec-rehearse >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --comment "The rehearsal copy's reset, for the orchestrator" aisec-rehearse
fi
passwd --lock aisec-rehearse >/dev/null

install -m 0755 -o root -g root "$here/aisec-rehearsal-reset" /usr/local/sbin/aisec-rehearsal-reset

# The same limits again on the key line, so a change to one file alone does
# not open the account.
printf 'from="%s",restrict %s\n' "$orchestrator" "$key" >/etc/ssh/aisec-rehearse-keys
chown root:root /etc/ssh/aisec-rehearse-keys
chmod 0644 /etc/ssh/aisec-rehearse-keys

# sudo skips a name with a dot in it, so the file is checked there first.
new=/etc/sudoers.d/.92-aisec-rehearse.new
printf '%s\n' 'aisec-rehearse ALL=(root) NOPASSWD: /usr/local/sbin/aisec-rehearsal-reset ""' >"$new"
chown root:root "$new"
chmod 0440 "$new"
visudo -c -q -f "$new"
mv -f "$new" /etc/sudoers.d/92-aisec-rehearse

cat >/etc/ssh/sshd_config.d/21-aisec-rehearse.conf <<'SSHD'
# The orchestrator's reset key for the rehearsal copy (ADR 0044). Its one
# command resets the copy to the seed. The key file is root's, so the account
# cannot add a key.
Match User aisec-rehearse
  AuthorizedKeysFile /etc/ssh/aisec-rehearse-keys
  AllowTcpForwarding no
  PermitTTY no
  ForceCommand sudo -n /usr/local/sbin/aisec-rehearsal-reset
SSHD
chown root:root /etc/ssh/sshd_config.d/21-aisec-rehearse.conf
chmod 0600 /etc/ssh/sshd_config.d/21-aisec-rehearse.conf

sshd -t
systemctl try-reload-or-restart ssh.service
sshd -T -C "user=aisec-rehearse,host=orchestrator,addr=$orchestrator" |
  grep -E '^(authorizedkeysfile|allowtcpforwarding|permittty|forcecommand) '
