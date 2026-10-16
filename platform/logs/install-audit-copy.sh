#!/bin/bash
# Installs the audit copier on the orchestrator (ADR 0019). Run as root, from
# the folder that holds aisec_audit_copy.py and aisec-audit-copy.service.
# Cloud-init runs it after K3s, and the runbook runs it on a live machine.
#
# It can run again. It never replaces the audit file once it exists: that file
# is append-only, and starting it over would throw the record away.
set -euo pipefail

account=aisec-audit-copy
audit_file=/var/log/aisec/tool-audit.jsonl
here="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ -d /var/log/pods ] || { echo "/var/log/pods is missing: is K3s running?" >&2; exit 1; }

DEBIAN_FRONTEND=noninteractive apt-get install -y -q -o DPkg::Lock::Timeout=120 acl

getent passwd "$account" >/dev/null ||
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$account"

# Read on the pod logs, for this group only. The default entries reach the
# folders and files the runtime creates later. -X gives search on folders, not
# execute on files.
setfacl -m "g:$account:r-x" -m "d:g:$account:r-x" /var/log/pods
setfacl -R -m "g:$account:r-X" /var/log/pods
find /var/log/pods -mindepth 1 -type d -exec setfacl -m "d:g:$account:r-x" {} +

install -d -m 0755 -o root -g root /var/log/aisec
if [ ! -e "$audit_file" ]; then
  install -m 0620 -o root -g "$account" /dev/null "$audit_file"
fi
chattr +a "$audit_file"

install -D -m 0644 -o root -g root "$here/aisec_audit_copy.py" /usr/local/lib/aisec/aisec_audit_copy.py
install -m 0644 -o root -g root "$here/aisec-audit-copy.service" /etc/systemd/system/aisec-audit-copy.service
systemctl daemon-reload
systemctl enable aisec-audit-copy.service
systemctl restart aisec-audit-copy.service
