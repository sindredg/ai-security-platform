#!/bin/bash
# Installs the change commands on the orchestrator (ADR 0043 to 0046). Run as
# root, from a copy of the repository's platform/change and collectors/netbox,
# after install-collector.sh, whose library and observer key they use.
#
#   install-change.sh [APPROVERS]
#
# The commands go into /usr/local/sbin, the libraries beside the collector in
# /usr/local/lib/aisec, and the state directories are root's alone. The reset
# key for the rehearsal copy is made once, and its public half is printed for
# install-rehearsal-reset.sh on the lab VM. With APPROVERS, the file of allowed
# approval signers goes to /etc/aisec/delivery/approvers, which delivery reads
# and nothing replaces but this.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
collectors="$here/../../collectors/netbox"
lib=/usr/local/lib/aisec
reset=/etc/aisec/netbox-rehearsal/reset

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ "$#" -le 1 ] || { echo "usage: install-change.sh [APPROVERS]" >&2; exit 2; }
for file in "$here/propose.py" "$here/policy.py" "$here/rehearse.py" "$here/netbox_change.py" \
  "$collectors/collect_evidence.py"; do
  [ -f "$file" ] || { echo "missing: $file" >&2; exit 1; }
done
[ -f "$lib/netbox_access.py" ] || { echo "no collector in $lib: run install-collector.sh first" >&2; exit 1; }
[ -f /etc/aisec/netbox/observe/known_hosts ] || { echo "no pinned lab VM host key" >&2; exit 1; }

install -d -m 0755 -o root -g root "$lib"
install -m 0644 -o root -g root "$here/policy.py" "$here/rehearse.py" "$here/netbox_change.py" "$lib/"
# rehearse.py runs the copy's halves with the collect command's limits.
install -m 0644 -o root -g root "$collectors/collect_evidence.py" "$lib/collect_evidence.py"
install -m 0755 -o root -g root "$here/propose.py" /usr/local/sbin/propose-netbox-fix
if [ -f "$here/deliver.py" ]; then
  install -m 0755 -o root -g root "$here/deliver.py" /usr/local/sbin/deliver-netbox-change
fi

install -d -m 0700 -o root -g root /var/lib/aisec/proposals /var/lib/aisec/delivery \
  /var/lib/aisec/delivery/results

install -d -m 0700 -o root -g root "$reset"
if [ ! -e "$reset/id_ed25519" ]; then
  ssh-keygen -q -t ed25519 -N "" -C aisec-rehearsal-reset -f "$reset/id_ed25519"
fi

if [ "$#" -eq 1 ]; then
  if ! grep -qE '^aisec-approver namespaces="git" ssh-ed25519 [A-Za-z0-9+/]+={0,2}( [A-Za-z0-9@._-]+)?$' "$1" ||
    [ "$(grep -cv '^#' "$1")" != 1 ]; then
    echo "not one approver line: $1" >&2
    exit 1
  fi
  install -d -m 0755 -o root -g root /etc/aisec/delivery
  install -m 0644 -o root -g root "$1" /etc/aisec/delivery/approvers
fi

cat "$reset/id_ed25519.pub"
