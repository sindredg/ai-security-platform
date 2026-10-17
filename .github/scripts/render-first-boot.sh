#!/usr/bin/env bash
# Writes each VM's first-boot script out of its cloud-init template, so that
# ShellCheck can read it. The scripts run as root on first boot and hold
# template expressions, so they are rendered first, with placeholder values.
#
# Usage: render-first-boot.sh OUT_DIR
# Needs terraform on the PATH. Writes OUT_DIR/<template>.sh for each template.
set -euo pipefail

out=${1:?usage: render-first-boot.sh OUT_DIR}
templates=$(cd "$(dirname "$0")/../../infra/platform/cloud-init" && pwd)
script_path=/usr/local/sbin/aisec-first-boot

# Every variable any template takes. A template ignores the ones it does not
# use, and fails on one that is missing here.
vars='{
  admin_username = "aisec", operator_user_ca_public_key = "ssh-ed25519 AAAA placeholder",
  orchestrator_ip = "10.0.0.4", worker_ip = "10.0.0.36", worker_prefix = "10.0.0.32/27",
  edge_ip = "10.0.1.4", platform_address_space = "10.0.0.0/20", k3s_version = "v0.0.0+k3s1",
  k3s_sha256 = "0", k3s_install_sha256 = "0", advertised_routes = "10.0.0.0/20",
  tailscale_version = "0.0.0", tailscale_auth_key = "placeholder",
  audit_copy_py = "", audit_copy_unit = "", audit_copy_install = "",
  journal_pull_py = "", journal_pull_unit = "", journal_pull_timer = "",
  journal_pull_install = "", log_export_command = "", log_export_install = "",
  feed_receive_command = "", feed_receive_install = "", fetch_window = "", fetch_hosts = ""
}'

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
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
  expr="jsonencode([for f in yamldecode(templatefile(\"$template\", $vars)).write_files : f.content if f.path == \"$script_path\"])"
  # An empty configuration, so console needs no provider and no init.
  json=$(tr '\n' ' ' <<<"$expr" | terraform -chdir="$work" console)
  # console prints the JSON as a quoted string. One script, or a failure.
  python3 -I -c '
import json, sys
scripts = json.loads(json.loads(sys.stdin.read()))
if len(scripts) != 1:
    sys.exit(f"{sys.argv[1]}: expected one first-boot script, found {len(scripts)}")
sys.stdout.write(scripts[0])
' "$name" <<<"$json" >"$out/$name.sh"
  echo "rendered $name"
  count=$((count + 1))
done
[ "$count" -gt 0 ]
