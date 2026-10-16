#!/bin/bash
# Installs the journal puller on the orchestrator (ADR 0019). Run as root, from
# the folder that holds aisec_journal_pull.py and its unit and timer.
# Cloud-init runs it with no argument at first boot, which makes the key. The
# runbook runs it again with the worker's host key, which it pins.
#
#   install-journal-pull.sh ["ssh-ed25519 AAAA..."]
#
# It prints the public key, for the worker's install-log-export.sh. It never
# replaces the key or the journal file once they exist.
set -euo pipefail

account=aisec-journal-pull
home=/var/lib/aisec-journal-pull
journal_file=/var/log/aisec/worker-journal.jsonl
# Root's, outside the account's folder, so the puller cannot pin another key.
known_hosts=/etc/aisec/journal-pull-known-hosts
worker=10.40.0.36
host_key=${1:-}
here="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

getent passwd "$account" >/dev/null ||
  useradd --system --no-create-home --home-dir "$home" --shell /usr/sbin/nologin "$account"
install -d -m 0700 -o "$account" -g "$account" "$home"

# Made here, so the private half never passes through Terraform or its state.
if [ ! -e "$home/id_ed25519" ]; then
  runuser -u "$account" -- ssh-keygen -q -t ed25519 -N "" -C "$account" -f "$home/id_ed25519"
fi

if [ -n "$host_key" ]; then
  if ! [[ $host_key =~ ^ssh-ed25519\ [A-Za-z0-9+/]+={0,2}$ ]]; then
    echo "not an ed25519 host key, without a host name in front" >&2
    exit 1
  fi
  install -d -m 0755 -o root -g root /etc/aisec
  printf '%s %s\n' "$worker" "$host_key" >"$known_hosts"
  chown root:root "$known_hosts"
  chmod 0644 "$known_hosts"
fi

install -d -m 0755 -o root -g root /var/log/aisec
if [ ! -e "$journal_file" ]; then
  install -m 0620 -o root -g "$account" /dev/null "$journal_file"
fi
chattr +a "$journal_file"

install -D -m 0644 -o root -g root "$here/aisec_journal_pull.py" /usr/local/lib/aisec/aisec_journal_pull.py
install -m 0644 -o root -g root "$here/aisec-journal-pull.service" /etc/systemd/system/aisec-journal-pull.service
install -m 0644 -o root -g root "$here/aisec-journal-pull.timer" /etc/systemd/system/aisec-journal-pull.timer
systemctl daemon-reload
systemctl enable --now aisec-journal-pull.timer

cat "$home/id_ed25519.pub"
