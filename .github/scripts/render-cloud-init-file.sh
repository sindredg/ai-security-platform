#!/usr/bin/env bash
# Prints one file that a cloud-init template writes, rendered by Terraform the
# way the platform root renders it. Every template variable gets a placeholder
# value unless NAME=VALUE gives it another one.
#
# Usage: render-cloud-init-file.sh TEMPLATE PATH [NAME=VALUE ...]
#   TEMPLATE  a template's name in infra/platform/cloud-init, without
#             .yaml.tftpl: orchestrator, edge, router, worker
#   PATH      the path of one entry in its write_files
# Needs terraform on the PATH, or TERRAFORM naming it. Fails unless exactly one
# entry has that path.
set -euo pipefail

name=${1:?usage: render-cloud-init-file.sh TEMPLATE PATH [NAME=VALUE ...]}
path=${2:?usage: render-cloud-init-file.sh TEMPLATE PATH [NAME=VALUE ...]}
shift 2
terraform=${TERRAFORM:-terraform}
template="$(cd "$(dirname "$0")/../../infra/platform/cloud-init" && pwd)/$name.yaml.tftpl"
[ -f "$template" ] || { echo "no template $template" >&2; exit 2; }

# Every variable any template takes. A template ignores the ones it does not
# use, and fails on one that is missing here.
vars='{
  admin_username = "aisec", operator_user_ca_public_key = "ssh-ed25519 AAAA placeholder",
  orchestrator_ip = "10.0.0.4", worker_ip = "10.0.0.36", worker_prefix = "10.0.0.32/27",
  edge_ip = "10.0.1.4", platform_address_space = "10.0.0.0/20", k3s_version = "v0.0.0+k3s1",
  k3s_sha256 = "0", k3s_install_sha256 = "0", k3s_images_sha256 = "0", advertised_routes = "10.0.0.0/20",
  tailscale_version = "0.0.0", tailscale_auth_key = "placeholder",
  audit_copy_py = "", audit_copy_unit = "", audit_copy_install = "",
  journal_pull_py = "", journal_pull_unit = "", journal_pull_timer = "",
  journal_pull_install = "", log_export_command = "", log_export_install = "",
  feed_receive_command = "", feed_receive_install = "", fetch_window = "", fetch_hosts = "",
  host_audit_rules = "", host_audit_plugin = "", host_audit_aide_conf = "", host_audit_check = "",
  host_audit_baseline = "", host_audit_service = "", host_audit_timer = "", host_audit_install = ""
}'

# The overrides as an HCL object. A value is a JSON string, which HCL reads
# the same way, as long as it holds no template sequence. A name the list
# above does not hold is refused: a typo would leave the placeholder. The
# Python is single-quoted on purpose: its ${ is a string to look for, not an
# expansion.
# shellcheck disable=SC2016
overrides=$(python3 -I -c '
import json, re, sys
known = set(re.findall(r"([a-z_]+) =", sys.argv[1]))
pairs = {}
for arg in sys.argv[2:]:
    key, sep, value = arg.partition("=")
    if not sep or not re.fullmatch(r"[a-z_]+", key):
        sys.exit(f"not NAME=VALUE: {arg}")
    if key not in known:
        sys.exit(f"no template variable named {key}")
    if "${" in value or "%{" in value:
        sys.exit(f"template sequence in the value of {key}")
    pairs[key] = value
print("{" + ", ".join(f"{k} = {json.dumps(v)}" for k, v in pairs.items()) + "}")
' "$vars" "$@")

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT

expr="jsonencode([for f in yamldecode(templatefile(\"$template\", merge($vars, $overrides))).write_files : f.content if f.path == \"$path\"])"
# An empty configuration, so console needs no provider and no init.
json=$(tr '\n' ' ' <<<"$expr" | "$terraform" -chdir="$work" console)
# console prints the JSON as a quoted string. One file, or a failure.
python3 -I -c '
import json, sys
files = json.loads(json.loads(sys.stdin.read()))
if len(files) != 1:
    sys.exit(f"{sys.argv[1]}: expected one entry for {sys.argv[2]}, found {len(files)}")
sys.stdout.write(files[0])
' "$name" "$path" <<<"$json"
