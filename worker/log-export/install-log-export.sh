#!/bin/bash
# Sets up the account the orchestrator pulls the worker's journal through
# (ADR 0019). Run as root on the worker, from the folder that holds
# aisec-journal-export. Cloud-init runs it with no argument at first boot. The
# runbook runs it again with the orchestrator's public key, which only exists
# once the orchestrator has booted.
#
#   install-log-export.sh ["ssh-ed25519 AAAA... aisec-journal-pull"]
set -euo pipefail

account=aisec-logexport
orchestrator=10.40.0.4
key=${1:-}
here="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

# sshd runs a forced command through the account's shell, so it needs one. The
# password is locked, and the key can run nothing but the export.
getent passwd "$account" >/dev/null ||
  useradd --system --create-home --home-dir "/home/$account" --shell /bin/bash \
    --groups systemd-journal "$account"
install -m 0755 -o root -g root "$here/aisec-journal-export" /usr/local/sbin/aisec-journal-export

# The key's options are root's to change, not the account's.
install -d -m 0755 -o root -g root "/home/$account/.ssh"
if [ -n "$key" ]; then
  if ! [[ $key =~ ^ssh-ed25519\ [A-Za-z0-9+/]+={0,2}(\ [A-Za-z0-9@._-]+)?$ ]]; then
    echo "not an ed25519 public key" >&2
    exit 1
  fi
  printf 'from="%s",restrict,command="/usr/local/sbin/aisec-journal-export" %s\n' "$orchestrator" "$key" \
    >"/home/$account/.ssh/authorized_keys"
  chown root:root "/home/$account/.ssh/authorized_keys"
  chmod 0644 "/home/$account/.ssh/authorized_keys"
fi
