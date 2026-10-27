#!/usr/bin/env bash
# Runs on the worker, as root, after install-agent.sh. Sets up how a job
# arrives (ADR 0030): the aisec-job account that the dispatch key logs in to,
# its forced command, the job program, and the socket that starts one sandboxed
# unit per job. Run it again after a change to any of them.
#
# The dispatch key's public half is given once the dispatch secret exists in
# the cluster. Without it, the key line is left as it is.
#
#   install-job.sh ["ssh-ed25519 AAAA... aisec-dispatch"]
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=pins.env
. "$here/pins.env"

account=aisec-job
orchestrator=10.40.0.4
key=${1:-}

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ -x "$GOOSE_DIR/goose" ] || { echo "Goose $GOOSE_VERSION is not installed: run install-agent.sh first" >&2; exit 1; }

# sshd runs a forced command through the account's shell, so it needs one. The
# password is locked, the account has no sudo, and the key can run nothing but
# the command. The home is root's, so the account cannot change its own key.
getent passwd "$account" > /dev/null ||
  useradd --system --user-group --no-create-home --home-dir "/home/$account" --shell /bin/bash "$account"
install -d -m 0755 -o root -g root "/home/$account" "/home/$account/.ssh"

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

install -m 0755 -o root -g root "$here/job/aisec_job_runner.py" /usr/local/sbin/aisec-job-runner
install -d -m 0755 -o root -g root /usr/local/lib/aisec/job
install -m 0644 -o root -g root "$here/job/agent_job.py" "$here/system.txt" /usr/local/lib/aisec/job/
install -m 0644 -o root -g root "$here/job/aisec-agent-job.socket" /etc/systemd/system/aisec-agent-job.socket
sed "s|@GOOSE@|$GOOSE_DIR/goose|" "$here/job/aisec-agent-job@.service" > /etc/systemd/system/aisec-agent-job@.service
chmod 0644 /etc/systemd/system/aisec-agent-job@.service
systemctl daemon-reload
systemctl enable --quiet --now aisec-agent-job.socket

# The key's options are root's to change, not the account's.
if [ -n "$key" ]; then
  if ! [[ $key =~ ^ssh-ed25519\ [A-Za-z0-9+/]+={0,2}(\ [A-Za-z0-9@._-]+)?$ ]]; then
    echo "not an ed25519 public key" >&2
    exit 1
  fi
  printf 'from="%s",restrict,command="/usr/local/sbin/aisec-job-runner" %s\n' "$orchestrator" "$key" \
    > "/home/$account/.ssh/authorized_keys"
  chown root:root "/home/$account/.ssh/authorized_keys"
  chmod 0644 "/home/$account/.ssh/authorized_keys"
fi

stat -c '%U %G %a %n' /run/aisec-job/agent.sock
systemctl is-active aisec-agent-job.socket
