#!/bin/bash
# Installs the update run on the orchestrator (ADR 0036). Run as root, from the
# folder that holds aisec-target-update-run.
#
#   install-target-update.sh ["NETBOX_HOST_KEY" "LAB_HOST_KEY"]
#
# Before the targets exist, run it with no argument: it makes the update key
# and prints the public half, for the targets root's update_public_key. Once
# they exist, run it again with each VM's host key from its serial log, as
# "ssh-ed25519 AAAA...", which it pins. It never replaces the key.
set -euo pipefail

dir=/etc/aisec/target-update
here="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ "$#" -eq 0 ] || [ "$#" -eq 2 ] || { echo "usage: install-target-update.sh [NETBOX_HOST_KEY LAB_HOST_KEY]" >&2; exit 2; }
for key in "$@"; do
  if ! [[ $key =~ ^ssh-ed25519\ [A-Za-z0-9+/]+={0,2}$ ]]; then
    echo "not an ed25519 host key, without a host name in front: $key" >&2
    exit 1
  fi
done

# Root's alone. The key logs in to every target.
install -d -m 0700 -o root -g root "$dir"
if [ ! -e "$dir/id_ed25519" ]; then
  ssh-keygen -q -t ed25519 -N "" -C aisec-target-update -f "$dir/id_ed25519"
fi

# Written whole each time, so a rebuilt target's new key replaces the old one.
if [ "$#" -eq 2 ]; then
  printf '10.50.0.4 %s\n10.50.0.36 %s\n' "$1" "$2" >"$dir/known_hosts"
  chown root:root "$dir/known_hosts"
  chmod 0644 "$dir/known_hosts"
fi

install -m 0700 -o root -g root "$here/aisec-target-update-run" /usr/local/sbin/aisec-target-update-run

cat "$dir/id_ed25519.pub"
