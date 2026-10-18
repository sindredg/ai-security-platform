#!/usr/bin/env bash
# Writes each VM's first-boot script out of its cloud-init template, so that
# ShellCheck can read it. The scripts run as root on first boot and hold
# template expressions, so they are rendered first, with placeholder values.
#
# Usage: render-first-boot.sh OUT_DIR
# Needs terraform on the PATH. Writes OUT_DIR/<template>.sh for each template.
set -euo pipefail

out=${1:?usage: render-first-boot.sh OUT_DIR}
here=$(cd "$(dirname "$0")" && pwd)
templates=$(cd "$here/../../infra/platform/cloud-init" && pwd)
script_path=/usr/local/sbin/aisec-first-boot

mkdir -p "$out"

count=0
for template in "$templates"/*.yaml.tftpl; do
  name=$(basename "$template" .yaml.tftpl)
  # The worker's first boot is a list of commands in runcmd, and the scripts
  # it runs are files in the repository that ShellCheck reads directly.
  if ! grep -q "path: $script_path\$" "$template"; then
    echo "skipped $name: no first-boot script"
    continue
  fi
  "$here/render-cloud-init-file.sh" "$name" "$script_path" >"$out/$name.sh"
  echo "rendered $name"
  count=$((count + 1))
done
[ "$count" -gt 0 ]
