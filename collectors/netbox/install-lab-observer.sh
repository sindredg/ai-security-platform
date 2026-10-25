#!/bin/bash
# Installs the observer account on the lab VM (ADR 0040): the orchestrator's
# one way to run the observed half of NetBox's collector from the consumer
# viewpoint. Run as root, from a folder that holds netbox_access.py.
#
#   install-lab-observer.sh "ssh-ed25519 AAAA... aisec-netbox-observe"
#
# The key is the public half install-collector.sh printed on the
# orchestrator. The account follows the update account's pattern (ADR 0036):
# a key file root owns, the orchestrator's address and restrict on the key
# line, no forwarding, no TTY, and one command through sudo. Run again, it
# writes every file whole, so another key replaces the old one.
set -euo pipefail

orchestrator=10.40.0.4
here="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ "$#" -eq 1 ] || { echo "usage: install-lab-observer.sh PUBLIC_KEY" >&2; exit 2; }
key=$1
if ! [[ $key =~ ^ssh-ed25519\ [A-Za-z0-9+/]+={0,2}(\ [A-Za-z0-9@._-]+)?$ ]]; then
  echo "not an ed25519 public key: $key" >&2
  exit 1
fi
[ -f "$here/netbox_access.py" ] || { echo "missing: $here/netbox_access.py" >&2; exit 1; }

if ! id aisec-observe >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --comment "NetBox's observed half for the orchestrator" aisec-observe
fi
passwd --lock aisec-observe >/dev/null

install -d -m 0755 -o root -g root /usr/local/lib/aisec
install -m 0644 -o root -g root "$here/netbox_access.py" /usr/local/lib/aisec/netbox_access.py

# The contract arrives on standard input, from the orchestrator. The tokens
# the collector reads are root's, so the one command runs as root.
cat >/usr/local/sbin/aisec-observe-netbox <<'EOF'
#!/bin/sh
exec /usr/bin/python3 -I /usr/local/lib/aisec/netbox_access.py observed
EOF
chown root:root /usr/local/sbin/aisec-observe-netbox
chmod 0755 /usr/local/sbin/aisec-observe-netbox

# The same limits again on the key line, so a change to one file alone does
# not open the account.
printf 'from="%s",restrict %s\n' "$orchestrator" "$key" >/etc/ssh/aisec-observe-keys
chown root:root /etc/ssh/aisec-observe-keys
chmod 0644 /etc/ssh/aisec-observe-keys

# sudo skips a name with a dot in it, so the file is checked there first.
new=/etc/sudoers.d/.91-aisec-observe.new
printf '%s\n' 'aisec-observe ALL=(root) NOPASSWD: /usr/local/sbin/aisec-observe-netbox ""' >"$new"
chown root:root "$new"
chmod 0440 "$new"
visudo -c -q -f "$new"
mv -f "$new" /etc/sudoers.d/91-aisec-observe

cat >/etc/ssh/sshd_config.d/20-aisec-observe.conf <<'EOF'
# The orchestrator's observer key (ADR 0040). Its one command is the
# observed half of NetBox's collector. The key file is root's, so the account
# cannot add a key.
Match User aisec-observe
  AuthorizedKeysFile /etc/ssh/aisec-observe-keys
  AllowTcpForwarding no
  PermitTTY no
  ForceCommand sudo -n /usr/local/sbin/aisec-observe-netbox
EOF
chown root:root /etc/ssh/sshd_config.d/20-aisec-observe.conf
chmod 0600 /etc/ssh/sshd_config.d/20-aisec-observe.conf

# ssh.service starts on the first connection, so it may not be running yet.
sshd -t
systemctl try-reload-or-restart ssh.service
sshd -T -C "user=aisec-observe,host=orchestrator,addr=$orchestrator" |
  grep -E '^(authorizedkeysfile|allowtcpforwarding|permittty|forcecommand) '
