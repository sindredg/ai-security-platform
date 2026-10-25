#!/bin/bash
# Installs NetBox's collect command on the orchestrator (ADR 0040). Run as
# root, from a folder that holds netbox_access.py and collect_evidence.py from
# this directory, and contract.json from the targets repository's netbox/.
#
#   install-collector.sh
#
# Makes the observer key once and prints its public half, for
# install-lab-observer.sh on the lab VM. It never replaces the key. The lab
# VM's host key is the one the update run pinned (ADR 0036).
set -euo pipefail

dir=/etc/aisec/netbox/observe
pinned=/etc/aisec/target-update/known_hosts
here="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ "$#" -eq 0 ] || { echo "usage: install-collector.sh" >&2; exit 2; }
for file in netbox_access.py collect_evidence.py contract.json; do
  [ -f "$here/$file" ] || { echo "missing: $here/$file" >&2; exit 1; }
done
python3 -I -c 'import json, sys; json.load(open(sys.argv[1]))' "$here/contract.json"
if ! lab=$(grep -E '^10\.50\.0\.36 ssh-ed25519 [A-Za-z0-9+/]+={0,2}$' "$pinned"); then
  echo "no pinned host key for the lab VM in $pinned" >&2
  exit 1
fi

# Root's alone. The key runs the observed half on the lab VM.
install -d -m 0700 -o root -g root "$dir"
if [ ! -e "$dir/id_ed25519" ]; then
  ssh-keygen -q -t ed25519 -N "" -C aisec-netbox-observe -f "$dir/id_ed25519"
fi
printf '%s\n' "$lab" >"$dir/known_hosts"
chown root:root "$dir/known_hosts"
chmod 0644 "$dir/known_hosts"

install -d -m 0755 -o root -g root /usr/local/lib/aisec
install -m 0644 -o root -g root "$here/netbox_access.py" /usr/local/lib/aisec/netbox_access.py
install -m 0755 -o root -g root "$here/collect_evidence.py" /usr/local/sbin/collect-netbox-evidence
install -m 0644 -o root -g root "$here/contract.json" /etc/aisec/netbox/contract.json
# The verdicts and the full reports of each job. The job never reads them.
install -d -m 0700 -o root -g root /var/lib/aisec/evidence /var/lib/aisec/evidence/netbox

cat "$dir/id_ed25519.pub"
