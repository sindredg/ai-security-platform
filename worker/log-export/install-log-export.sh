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

# Each login used to start and stop a user service manager for the account,
# whose lines the journal pull then copied: a third of the workspace's daily
# volume for the pull's own logins (issue 164). A session of the light class is
# still registered with logind, and starts no user manager. The profile gives
# the class to this account's sessions only, ahead of pam_systemd.
profile=/usr/share/pam-configs/aisec-light-session-$account
{
  printf 'Name: Sessions of %s without a user service manager\n' "$account"
  printf 'Default: yes\nPriority: 64\nSession-Interactive-Only: yes\nSession-Type: Additional\nSession:\n'
  printf '\t[success=1 default=ignore]\tpam_succeed_if.so quiet user != %s\n' "$account"
  printf '\toptional\tpam_env.so readenv=0 user_readenv=0 conffile=/etc/security/aisec-light-session.conf\n'
} > "$profile"
echo 'XDG_SESSION_CLASS DEFAULT=background-light' > /etc/security/aisec-light-session.conf
chmod 0644 "$profile" /etc/security/aisec-light-session.conf
DEBIAN_FRONTEND=noninteractive pam-auth-update --enable "aisec-light-session-$account"

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
