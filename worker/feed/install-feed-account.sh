#!/bin/bash
# Sets up the account the orchestrator's feed key logs in to (ADR 0026). Run as
# root on the worker, from the folder that holds aisec-feed-receive. Cloud-init
# runs it with no argument at first boot. The runbook runs it again with the
# orchestrator's public key, which only exists once the orchestrator has booted.
#
#   install-feed-account.sh ["ssh-ed25519 AAAA... aisec-feed"]
set -euo pipefail

account=aisec-feed
orchestrator=10.40.0.4
key=${1:-}
here="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

# sshd runs a forced command through the account's shell, so it needs one. The
# password is locked, the account has no sudo, and the key can run nothing but
# the command. No files from /etc/skel: the home is root's, so the account
# cannot write a file its shell reads at login.
getent passwd "$account" >/dev/null ||
  useradd --system --no-create-home --home-dir "/home/$account" --shell /bin/bash "$account"
install -d -m 0755 -o root -g root "/home/$account" "/home/$account/.ssh"
for component in model-server agent-runtime; do
  install -d -m 0755 -o "$account" -g "$account" "/home/$account/$component"
done
install -m 0755 -o root -g root "$here/aisec-feed-receive" /usr/local/sbin/aisec-feed-receive

# The key's options are root's to change, not the account's.
if [ -n "$key" ]; then
  if ! [[ $key =~ ^ssh-ed25519\ [A-Za-z0-9+/]+={0,2}(\ [A-Za-z0-9@._-]+)?$ ]]; then
    echo "not an ed25519 public key" >&2
    exit 1
  fi
  printf 'from="%s",restrict,command="/usr/local/sbin/aisec-feed-receive" %s\n' "$orchestrator" "$key" \
    >"/home/$account/.ssh/authorized_keys"
  chown root:root "/home/$account/.ssh/authorized_keys"
  chmod 0644 "/home/$account/.ssh/authorized_keys"
fi
