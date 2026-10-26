#!/usr/bin/env bash
# Checks the claims the platform side makes, against the running system.
#
# Read-only. It opens connections that should fail and reads settings. The one
# thing it sends to Azure is a template validation, which deploys nothing.
#
# Run it from a workstation that is on the mesh VPN and signed in to Azure as
# the operator. What each check proves is in docs/validation/. The Azure
# checks need python3, to put rules from two different commands in one form.
#
#   AISEC_SSH   The ssh command, with host key and identity options.
#               Default: ssh
#   AISEC_ORCH  Orchestrator address or host alias. Default: 10.40.0.4
#   AISEC_WORK  Worker address or host alias. Default: 10.40.0.36
#   AISEC_ROUTER  Router address or host alias, on the mesh VPN.
#               Default: aisec-router
#   AISEC_EDGE  Edge VM address or host alias. Default: 10.45.0.4
#   AISEC_NETBOX  NetBox VM address or host alias. Default: 10.50.0.4
#   AISEC_LAB   Lab VM address or host alias. Default: 10.50.0.36
#   AISEC_TARGETS  The targets repository's checkout on the workstation, to
#               compare the targets' update command and NetBox's image with.
#               Without it, those checks fail.
#   AISEC_USER_CA  The SSH certificate authority's public key file on the
#               workstation. The VMs have to trust this one and no other.
#   TERRAFORM   The terraform command, to render a cloud-init template.
#               Default: terraform
#
#   validation/platform-checks.sh [--no-azure] [--no-workstation]

# The probes are single-quoted on purpose. They are sent to the VMs as text
# and expand there, not here.
# shellcheck disable=SC2016
set -uo pipefail

SSH=${AISEC_SSH:-ssh}
ORCH=${AISEC_ORCH:-10.40.0.4}
WORK=${AISEC_WORK:-10.40.0.36}
ROUTER=${AISEC_ROUTER:-aisec-router}
EDGE=${AISEC_EDGE:-10.45.0.4}
NETBOX=${AISEC_NETBOX:-10.50.0.4}
LAB=${AISEC_LAB:-10.50.0.36}
# The fingerprint the VMs' certificate authority file has to show. Without the
# file there is nothing to compare with, and the check fails.
USER_CA_FP=$(ssh-keygen -l -f "${AISEC_USER_CA:-/nonexistent}" 2>/dev/null | cut -d " " -f 2)
USER_CA_FP=${USER_CA_FP:-"AISEC_USER_CA not given or not a public key"}
ORCH_IP=10.40.0.4
WORK_IP=10.40.0.36
EDGE_IP=10.45.0.4
ROUTER_IP=10.45.0.36
NETBOX_IP=10.50.0.4
LAB_IP=10.50.0.36
WORK_PREFIX=10.40.0.32/27
# What the router advertises (ADR 0025): the platform, the targets, and the
# edge subnet.
ROUTES="10.40.0.0/20 10.45.0.0/27 10.50.0.0/20"
# Squid on the edge, for the worker and the orchestrator (ADR 0020).
PROXY="http://$EDGE_IP:3128"
# Squid's port for the targets' packages, which the orchestrator forwards to a
# target during an update run (ADR 0036).
TARGET_PROXY="http://$EDGE_IP:3129"
MODEL_UNIT=aisec-llama-server
MODEL_PORT=8080
TOOL_PORT=30443
TOOL_NAME=tool-service.aisec.internal
TOOL_CERT=/etc/aisec/tool-service.crt
here=$(cd "$(dirname "$0")" && pwd)
# The digest the reviewed manifest names, read from this checkout.
TOOL_IMAGE_DIGEST=$(sed -n 's/^ *image: ghcr.io[^@]*@\(sha256:[0-9a-f]*\)$/\1/p' "$here/../platform/tool-service/tool-service.yaml")
# The journal export command the worker should run, from this checkout.
EXPORT_SHA=$(sha256sum "$here/../worker/log-export/aisec-journal-export" | cut -d " " -f 1)
# The fetch window's command and host list, from this checkout.
WINDOW_SHA=$(sha256sum "$here/../edge/aisec-fetch-window" | cut -d " " -f 1)
HOSTS_SHA=$(sha256sum "$here/../edge/fetch-hosts" | cut -d " " -f 1)
# K3s's system images and the digest of each, as the release's archive gives
# them (ADR 0033), from this checkout. One line each, joined by spaces.
SYSTEM_IMAGES=$(grep -v "^#" "$here/../infra/platform/k3s-images.txt" 2>/dev/null | tr "\n" " ")
# Squid's configuration as the edge template writes it, with the platform's
# addresses. The x keeps the trailing newline. A failed rendering leaves a
# value no file can hash to.
if squid_conf=$("$here/../.github/scripts/render-cloud-init-file.sh" edge /etc/squid/squid.conf \
  edge_ip=$EDGE_IP orchestrator_ip=$ORCH_IP worker_prefix=$WORK_PREFIX && echo x); then
  SQUID_CONF_SHA=$(printf '%s' "${squid_conf%x}" | sha256sum | cut -d " " -f 1)
else
  SQUID_CONF_SHA="the edge template did not render"
fi
# The unit drop-in that sandboxes Squid, as the edge template writes it.
if squid_dropin=$("$here/../.github/scripts/render-cloud-init-file.sh" edge \
  /etc/systemd/system/squid.service.d/10-aisec.conf && echo x); then
  SQUID_DROPIN_SHA=$(printf '%s' "${squid_dropin%x}" | sha256sum | cut -d " " -f 1)
else
  SQUID_DROPIN_SHA="the edge template did not render"
fi
# The agent runtime's paths and binary pin, and its fixture, from this checkout.
agent="$here/../worker/agent-runtime"
# shellcheck source=../worker/agent-runtime/pins.env
read -r GOOSE_BIN GOOSE_BIN_SHA FIXTURE_DIR < <(. "$agent/pins.env" &&
  echo "$GOOSE_DIR/goose $GOOSE_BINARY_SHA256 $FIXTURE_DIR")
FIXTURE_FILES="check_answer.py evidence_tool.py question.txt system.txt"
# The system text is one file in the checkout, beside the fixture, and the
# worker has a copy of it in the fixture directory.
# shellcheck disable=SC2086 # the file names are one word each
FIXTURE_SHA=$({ (cd "$agent/fixture" && sha256sum ${FIXTURE_FILES% system.txt}) && (cd "$agent" && sha256sum system.txt); } |
  sha256sum | cut -d " " -f 1)
# How a job arrives on the worker (ADR 0030), in install order, with the
# service template filled in as install-job.sh does.
job="$agent/job"
JOB_SHA=$(cat "$job/aisec_job_runner.py" "$job/agent_job.py" "$agent/system.txt" "$job/aisec-agent-job.socket" \
  <(sed "s|@GOOSE@|$GOOSE_BIN|" "$job/aisec-agent-job@.service") | sha256sum | cut -d " " -f 1)
# Argo (ADR 0029): the controller's image and arguments, and the workflow
# template's spec as one SHA-256 over its JSON with sorted keys, as kubectl
# prints it. Read from this checkout. Needs Python's yaml module here.
argo="$here/../platform/argo"
ARGO_IMAGE_DIGEST=$(sed -n 's/^ *image: quay.io[^@]*@\(sha256:[0-9a-f]*\)$/\1/p' "$argo/argo.yaml")
ARGO_EXECUTOR=$(grep -o 'quay.io/argoproj/argoexec@sha256:[0-9a-f]*' "$argo/argo.yaml")
ARGO_ARGS="[\"--namespaced\",\"--managed-namespace\",\"orchestration\",\"--executor-image\",\"$ARGO_EXECUTOR\"]"
TEMPLATE_SHA=$(python3 -I -c '
import hashlib, json, sys, yaml
spec = yaml.safe_load(open(sys.argv[1]))["spec"]
text = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
print(hashlib.sha256(text.encode()).hexdigest())' "$argo/workflow-template.yaml" 2>/dev/null || echo "the template did not parse")
# The feed account's command, from this checkout.
FEED_SHA=$(sha256sum "$here/../worker/feed/aisec-feed-receive" | cut -d " " -f 1)
# The copiers' programs and units, in install order, from this checkout.
logs="$here/../platform/logs"
COPY_SHA=$(cat "$logs/aisec_audit_copy.py" "$logs/aisec-audit-copy.service" | sha256sum | cut -d " " -f 1)
PULL_SHA=$(cat "$logs/aisec_journal_pull.py" "$logs/aisec-journal-pull.service" "$logs/aisec-journal-pull.timer" |
  sha256sum | cut -d " " -f 1)
# The update run's command on the orchestrator, from this checkout.
TARGET_RUN_SHA=$(sha256sum "$here/../platform/target-update/aisec-target-update-run" | cut -d " " -f 1)
# The update key's one command on the targets, from the targets checkout.
TARGET_UPDATE_SHA=$(sha256sum "${AISEC_TARGETS:-/nonexistent}/host/aisec-target-update" 2>/dev/null | cut -d " " -f 1)
TARGET_UPDATE_SHA=${TARGET_UPDATE_SHA:-"AISEC_TARGETS not given or not the targets checkout"}
# The image ID NetBox's containers have to run (ADR 0035), from the targets
# checkout. Podman prints it without the sha256: prefix.
NETBOX_IMAGE_ID=$(sed -n "s/^NETBOX_IMAGE_ID=sha256://p" "${AISEC_TARGETS:-/nonexistent}/netbox/image.env" 2>/dev/null)
NETBOX_IMAGE_ID=${NETBOX_IMAGE_ID:-"AISEC_TARGETS not given or not the targets checkout"}
NETBOX_PORT=8443
# NetBox's consumer contract (ADR 0037), from the targets checkout, and the
# collector that reads both sides of it, from this checkout. The collector goes
# to a VM as an argument and the contract on its standard input, so neither is
# installed there.
CONTRACT=${AISEC_TARGETS:-/nonexistent}/netbox/contract.json
COLLECTOR_CODE=$(cat "$here/../collectors/netbox/netbox_access.py")
# What the seed in the targets checkout gives: the consumer's unscoped copy of
# its permission is excess, and the control account stays within the contract.
SEEDED_VERDICTS="inventory-reader:excess inventory-reader-control:within"
# What the orchestrator collects a job's evidence with (ADR 0040): the
# collector, the collect command, and the contract, in install order.
COLLECT_SHAS="$(sha256sum "$here/../collectors/netbox/netbox_access.py" \
  "$here/../collectors/netbox/collect_evidence.py" "$CONTRACT" "$here/../collectors/netbox/cases.json" \
  2>/dev/null | cut -d " " -f 1 | tr "\n" " " | sed "s/ $//")"
COLLECTOR_SHA=$(sha256sum "$here/../collectors/netbox/netbox_access.py" | cut -d " " -f 1)
RG=rg-aisec-platform
RG_TARGETS=rg-aisec-targets

azure=1
workstation=1
for arg in "$@"; do
  case "$arg" in
    --no-azure) azure=0 ;;
    --no-workstation) workstation=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

pass=0
fail=0

# check ID "what is claimed" expected actual
check() {
  if [ "$3" = "$4" ]; then
    pass=$((pass + 1))
    printf 'PASS  %-5s %s\n' "$1" "$2"
  else
    fail=$((fail + 1))
    printf 'FAIL  %-5s %s\n            expected: %s\n            actual:   %s\n' "$1" "$2" "$3" "$4"
  fi
}

# value KEY, from the "key=value" lines a probe printed
value() { printf '%s\n' "$probe" | sed -n "s/^$1=//p" | head -n 1; }

# tcp HOST PORT [SECONDS] prints how a connection attempt ended:
#
#   open         the handshake completed
#   refused      a reset came back, so the packet reached a host and nothing
#                listens there
#   timeout      nothing came back, so something on the path dropped the packet
#   unreachable  there is no route, or a router said so
#   error        anything else
#
# A network security group and the mesh policy both drop without answering. A
# check that says a rule blocks a path therefore expects "timeout" and nothing
# else. "refused" on such a path means the packet got past the rule and reached
# the host, which is the failure the check is there to catch.
#
# A timeout proves a drop only when something listens at the far end. Where
# nothing does, the comment at the check says what the result is worth.
#
# One definition, sent to the VMs inside the probes and loaded on the
# workstation.
tcp_fn='
tcp() {
  local out rc
  out=$(LC_ALL=C timeout "${3:-5}" bash -c "</dev/tcp/$1/$2" 2>&1); rc=$?
  case "$rc:$out" in
    0:*) echo open ;;
    124:*) echo timeout ;;
    *"Connection refused"*) echo refused ;;
    *"No route to host"*|*"Network is unreachable"*) echo unreachable ;;
    *) echo error ;;
  esac
}
'

# The probes run on the VMs and print key=value lines. Nothing in them changes
# the machine.
probe_common="$tcp_fn"'
sshd_opt() { sshd -T 2>/dev/null | sed -n "s/^$1 //p"; }
# A DNS query over UDP to Azure DNS. dig exits 9 when no reply came back.
udp_dns() {
  timeout 10 dig +tries=1 +time=4 @168.63.129.16 example.com A >/dev/null 2>&1
  case $? in 0) echo answer ;; 9) echo timeout ;; *) echo error ;; esac
}
# count GREP_ARGS -- COMMAND: the lines of COMMAND'"'"'s output that grep counts,
# then COMMAND'"'"'s exit status. A command that fails prints nothing, which grep
# alone would count as no line, the passing value (#173).
count() {
  local args=() out rc
  while [ "$#" -gt 0 ] && [ "$1" != -- ]; do args+=("$1"); shift; done
  shift
  out=$("$@" 2>/dev/null); rc=$?
  if [ -n "$out" ]; then echo "$(grep "${args[@]}" <<< "$out") $rc"; else echo "0 $rc"; fi
}
echo "failed_units=$(systemctl --failed --no-legend | wc -l)"
echo "sshd_root=$(sshd_opt permitrootlogin)"
echo "sshd_password=$(sshd_opt passwordauthentication)"
echo "sshd_tcp_forwarding=$(sshd_opt allowtcpforwarding)"
echo "sshd_agent_forwarding=$(sshd_opt allowagentforwarding)"
echo "sshd_max_auth_tries=$(sshd_opt maxauthtries)"
echo "sysctl_sysrq=$(sysctl -n kernel.sysrq)"
echo "sysctl_kptr=$(sysctl -n kernel.kptr_restrict)"
echo "sysctl_redirects=$(sysctl -n net.ipv4.conf.all.accept_redirects)"
echo "sysctl_bpf_jit=$(sysctl -n net.core.bpf_jit_harden)"
echo "mode_crontab=$(stat -c %a /etc/crontab)"
echo "mode_sshd_config=$(stat -c %a /etc/ssh/sshd_config)"
echo "mode_cron_d=$(stat -c %a /etc/cron.d)"
echo "toolchain=$(command -v as ld gcc cc 2>/dev/null | wc -l)"
echo "unused_modules=$(lsmod | grep -c -E "^(dccp|sctp|rds|tipc|usb_storage) ")"
echo "time_synced=$(timedatectl show -p NTPSynchronized --value)"
# Fetches from Canonical hosts that the image makes by itself: masked, and the
# login release check not executable. A missing unit reads not-found.
echo "ubuntu_fetchers=$(systemctl is-enabled esm-cache.service apt-news.service motd-news.timer update-notifier-motd.timer 2>/dev/null | tr "\n" " ")$(stat -c %a /etc/update-motd.d/91-release-upgrade 2>/dev/null)"
# Azure writes the operator key here at first boot, and first boot removes it.
# sshd ignores the file for this account either way, which the next lines show.
echo "authorized_keys=$(cat /home/aisec/.ssh/authorized_keys 2>/dev/null | grep -c .)"
admin_opt() { sshd -T -C user=aisec,host=check,addr='"$ORCH_IP"' 2>/dev/null | sed -n "s/^$1 //p"; }
echo "sshd_admin_auth=$(for k in authorizedkeysfile trustedusercakeys authorizedprincipalsfile revokedkeys; do admin_opt $k; done | tr "\n" " " | sed "s/ $//")"
echo "sshd_admin_forwarding=$(admin_opt allowtcpforwarding) $(admin_opt permitopen)"
echo "sshd_other_forwarding=$(sshd -T -C user=nobody,host=check,addr='"$ORCH_IP"' 2>/dev/null | sed -n "s/^allowtcpforwarding //p")"
echo "user_ca=$(ssh-keygen -l -f /etc/ssh/aisec-user-ca.pub 2>/dev/null | cut -d " " -f 2) $(grep -c . /etc/ssh/aisec-user-ca.pub 2>/dev/null)"
echo "principals=$(stat -c "%U %G %a" /etc/ssh/aisec-principals 2>/dev/null) $(cat /etc/ssh/aisec-principals 2>/dev/null | tr "\n" " " | sed "s/ $//")"
echo "revoked_keys=$(stat -c "%U %G" /etc/ssh/aisec-revoked.krl 2>/dev/null) $(ssh-keygen -Q -l -f /etc/ssh/aisec-revoked.krl >/dev/null 2>&1 && echo valid || echo invalid)"
# The log agent (ADR 0021): installed, and its service state.
echo "monitor_agent=$(dpkg-query -W -f="\${Status}" azuremonitoragent 2>/dev/null | grep -c " ok installed$") $(systemctl is-active azuremonitoragent 2>/dev/null)"
# The lines between the markers the hosts script writes, sorted. No block is
# an empty hash input, which no endpoint record matches.
echo "monitor_hosts=$(awk "/^# BEGIN aisec-monitoring/ { on = 1; next } /^# END aisec-monitoring/ { on = 0 } on" /etc/hosts | sort | sha256sum | cut -d " " -f 1)"
'

probe_orchestrator="$probe_common"'
echo "unit_k3s=$(systemctl is-active k3s)"
echo "node_ready=$(k3s kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready ")"
echo "pods_not_running=$(count -v -c " Running " -- k3s kubectl get pods -A -l "!workflows.argoproj.io/workflow" --no-headers)"
echo "secrets_encryption=$(k3s secrets-encrypt status 2>/dev/null | sed -n "s/^Encryption Status: //p")"
echo "cert_modes_not_600=$(stat -c %a /var/lib/rancher/k3s/server/tls/*.crt | grep -v -c "^600$")"
echo "default_sa_automount=$(count -v -c "^false$" -- k3s kubectl get sa -A --field-selector metadata.name=default -o jsonpath="{range .items[*]}{.automountServiceAccountToken}{\"\n\"}{end}")"
echo "apiserver_anonymous=$(journalctl -u k3s --no-pager 2>/dev/null | grep "Running kube-apiserver" | tail -n 1 | grep -o -- "--anonymous-auth=[a-z]*")"
echo "kubelet_auth=$(k3s kubectl get --raw "/api/v1/nodes/$(hostname)/proxy/configz" 2>/dev/null | python3 -I -c "
import json, sys
config = json.load(sys.stdin)[\"kubeletconfig\"]
print(str(config[\"authentication\"][\"anonymous\"][\"enabled\"]).lower(), config[\"authorization\"][\"mode\"])
" 2>/dev/null)"
# A privileged pod that mounts the root of the host, sent to every namespace as a
# server-side dry run. Admission runs and nothing is stored. A namespace that
# does not refuse it by pod security is listed, so an error is not a refusal.
privileged_pod="{\"apiVersion\":\"v1\",\"kind\":\"Pod\",\"metadata\":{\"name\":\"aisec-privileged-probe\"},\"spec\":{\"containers\":[{\"name\":\"probe\",\"image\":\"registry.k8s.io/pause:3.10\",\"securityContext\":{\"privileged\":true},\"volumeMounts\":[{\"name\":\"host\",\"mountPath\":\"/host\"}]}],\"volumes\":[{\"name\":\"host\",\"hostPath\":{\"path\":\"/\"}}]}}"
admitted=""
namespaces=$(k3s kubectl get namespaces -o jsonpath="{.items[*].metadata.name}" 2>/dev/null)
for ns in $namespaces; do
  printf "%s" "$privileged_pod" | k3s kubectl create --dry-run=server -n "$ns" -f - 2>&1 | grep -q "violates PodSecurity" || admitted="$admitted $ns"
done
echo "privileged_admitted=$([ -z "$namespaces" ] && echo "no namespaces" || echo "${admitted:- none}" | sed "s/^ //")"
echo "system_deployments_not_ready=$(k3s kubectl get deployments -n kube-system -o jsonpath="{range .items[*]}{.metadata.name} {.status.replicas} {.status.readyReplicas}{\"\n\"}{end}" 2>/dev/null | awk "NF { n++; if (\$2 != \$3) bad++ } END { print n ? bad + 0 : \"no deployments\" }")"
# Each tag K3s holds from rancher/ and each image a system pod runs, with the
# digest containerd has for it. A name that is not in the list with that
# digest is printed.
pinned="'"$SYSTEM_IMAGES"'"
held=$(k3s ctr -n k8s.io images ls 2>/dev/null | awk "NR > 1 && \$1 ~ /^docker\.io\/rancher\// && \$1 !~ /@/ {print \$1 \"@\" \$3}")
running=$(k3s kubectl get pods -n kube-system -o jsonpath="{range .items[*]}{range .status.containerStatuses[*]}{.image}{\"\n\"}{end}{end}" 2>/dev/null)
unpinned=""
for name in $({ printf "%s\n" "$held" | sed "s/@.*//"; printf "%s\n" "$running"; } | sort -u); do
  digest=$(printf "%s\n" "$held" | awk -F@ -v n="$name" "\$1 == n {print \$2}")
  case " $pinned " in *" $name@$digest "*) ;; *) unpinned="$unpinned $name" ;; esac
done
echo "system_images=$([ -z "$running" ] && echo "no system pods" || echo "${unpinned:- none}" | sed "s/^ //")"
echo "pod_egress=$(nft list chain inet aisec_pod_egress forward 2>/dev/null | sed -n "s/^\t\t//p" | sed "s/counter packets [0-9]* bytes [0-9]* /counter /" | tr "\n" "|")"
echo "pod_egress_input=$(nft list chain inet aisec_pod_egress input 2>/dev/null | sed -n "s/^\t\t//p" | sed "s/counter packets [0-9]* bytes [0-9]* /counter /" | tr "\n" "|")"
echo "pod_egress_unit=$(systemctl is-enabled aisec-pod-egress 2>/dev/null)"
# The one way out of the orchestrator is Squid on the edge.
echo "squid_installed=$(dpkg-query -W -f="\${Status}" squid 2>/dev/null | grep -c " ok installed$")"
code() { curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$@"; }
echo "proxy_own_mirror=$(code -x '"$PROXY"' http://azure.archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "proxy_worker_mirror=$(code -x '"$PROXY"' http://archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "proxy_tunnel=$(curl -s -o /dev/null -w "%{http_connect}" --max-time 8 -x '"$PROXY"' https://github.com/ 2>/dev/null)"
echo "target_proxy_mirror=$(code -x '"$TARGET_PROXY"' http://azure.archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "target_proxy_other_host=$(code -x '"$TARGET_PROXY"' http://archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "target_proxy_post=$(code -x '"$TARGET_PROXY"' -X POST -d x http://azure.archive.ubuntu.com/ubuntu/)"
echo "target_proxy_other_port=$(code -x '"$TARGET_PROXY"' http://azure.archive.ubuntu.com:8080/)"
echo "target_proxy_tunnel=$(curl -s -o /dev/null -w "%{http_connect}" --max-time 8 -x '"$TARGET_PROXY"' https://github.com/ 2>/dev/null)"
echo "apt_proxy=$(apt-config dump 2>/dev/null | grep -c "Acquire::http::Proxy \"'"$PROXY"'\"")"
echo "containerd_proxy=$(tr "\0" "\n" < /proc/$(pidof containerd)/environ 2>/dev/null | sed -n "s/^HTTPS_PROXY=//p")"
echo "azure_dns=$(tcp 168.63.129.16 53)"
echo "azure_dns_udp=$(udp_dns)"
# The package, and the interface it makes. Both are gone once the orchestrator
# leaves the mesh VPN (ADR 0025).
echo "mesh_agent=$(dpkg-query -W -f="\${Status}" tailscale 2>/dev/null | grep -c " ok installed$") $(ip -br link show tailscale0 2>/dev/null | wc -l)"
echo "egress_https=$(tcp 1.1.1.1 443)"
echo "to_worker_ssh=$(tcp '"$WORK_IP"' 22)"
echo "to_worker_http=$(tcp '"$WORK_IP"' 80)"
echo "to_worker_model=$(tcp '"$WORK_IP"' '"$MODEL_PORT"')"
echo "to_targets_ssh=$(tcp '"$NETBOX_IP"' 22) $(tcp '"$LAB_IP"' 22)"
# The NetBox API, with the certificate the NetBox VM made, which the orchestrator
# pins (ADR 0038), then plain HTTP on the same port, which gets no page.
cert=/etc/aisec/netbox/tls.crt
echo "netbox_cert=$(stat -c "%U %a" $cert 2>/dev/null) $(openssl x509 -in $cert -noout -fingerprint -sha256 2>/dev/null | cut -d = -f 2)"
echo "netbox_api=$(code --noproxy "*" --cacert $cert --resolve netbox.aisec.internal:'"$NETBOX_PORT:$NETBOX_IP"' \
  https://netbox.aisec.internal:'"$NETBOX_PORT"'/login/) $(code --noproxy "*" http://'"$NETBOX_IP:$NETBOX_PORT"'/login/)"
# NetBox takes the address of a client from the connection only (ADR 0039).
# The token of the probe account is limited to 192.0.2.1, which no host has,
# so NetBox refuses it here and names the address it saw. A header that names
# 192.0.2.1 has to change neither. The token goes to curl in a file, not in an
# argument. This text is inside single quotes, so it has no apostrophe.
tokens=/etc/aisec/netbox/tokens
address() {
  local out
  out=$(curl -s --noproxy "*" --max-time 8 --cacert $cert -w " %{http_code}" "$@" \
    -H @<(printf "Authorization: Bearer %s\n" "$(cat $tokens/aisec-address-probe 2>/dev/null)") \
    https://'"$NETBOX_IP:$NETBOX_PORT"'/api/status/)
  echo "${out##* }:$(printf "%s" "$out" | sed -n "s/.*Source IP \([0-9.]*\) is not permitted.*/\1/p")"
}
echo "netbox_address=$(address) $(address -H "X-Forwarded-For: 192.0.2.1") $(address -H "X-Real-IP: 192.0.2.1")"
echo "netbox_tokens=$(stat -c "%U %a" $tokens $tokens/aisec-collector $tokens/aisec-address-probe 2>/dev/null | tr "\n" " " | sed "s/ $//")"
# The key an update run logs in to the targets with (ADR 0036), and its
# public half, which each target holds.
update_key=/etc/aisec/target-update/id_ed25519
echo "target_update_key=$(stat -c "%U %a" $update_key 2>/dev/null) $(ssh-keygen -y -f $update_key 2>/dev/null | cut -d " " -f 1,2)"
run=/usr/local/sbin/aisec-target-update-run
echo "target_update_run=$(stat -c "%U %a" $run 2>/dev/null) $(sha256sum $run 2>/dev/null | cut -d " " -f 1)"
# The key each target offers, against the one the update run pins. A missing
# pin is a difference, not a match.
pins=""
for address in '"$NETBOX_IP $LAB_IP"'; do
  pinned=$(awk -v a="$address" "\$1 == a {print \$2, \$3}" /etc/aisec/target-update/known_hosts 2>/dev/null)
  offered=$(ssh-keyscan -T 8 -t ed25519 "$address" 2>/dev/null | grep -v "^#" | cut -d " " -f 2-)
  pins="$pins $([ -n "$pinned" ] && [ "$pinned" = "$offered" ] && echo match || echo differ)"
done
echo "target_update_pins=${pins# }"
# The collect command for NetBox, and the key it runs the observed half with
# on the lab VM (ADR 0040). The pin for the lab VM is the one the update run uses.
echo "netbox_collect=$(sha256sum /usr/local/lib/aisec/netbox_access.py /usr/local/sbin/collect-netbox-evidence \
  /etc/aisec/netbox/contract.json /etc/aisec/netbox/cases.json 2>/dev/null | cut -d " " -f 1 | tr "\n" " " | sed "s/ $//")"
observe=/etc/aisec/netbox/observe
echo "netbox_observe_key=$(stat -c "%U %a" $observe $observe/id_ed25519 2>/dev/null | tr "\n" " " | sed "s/ $//")"
lab_pin=$(grep "^'"$LAB_IP"' " /etc/aisec/target-update/known_hosts 2>/dev/null)
echo "netbox_observe_pin=$(wc -l <$observe/known_hosts 2>/dev/null) $([ -n "$lab_pin" ] && [ "$(cat $observe/known_hosts 2>/dev/null)" = "$lab_pin" ] && echo same || echo differ)"
# Exit status 2 is the feed command refusing. 255 would be SSH failing, and 0
# that the key ran a command it should not.
sudo -u aisec ssh -n -i /home/aisec/.ssh/aisec-feed -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 aisec-feed@aisec-worker id >/dev/null 2>&1
echo "feed_refuses=$?"
echo "security_updates_pending=$(count -c -e -security -- apt list --upgradable)"
k() { k3s kubectl "$@" 2>/dev/null; }
echo "tool_ready=$(k get deployment tool-service -n tool-services -o jsonpath="{.status.readyReplicas}")"
echo "tool_image=$(k get pods -n tool-services -l app.kubernetes.io/name=tool-service -o jsonpath="{.items[0].status.containerStatuses[0].imageID}" | sed "s/.*@//")"
echo "tool_pod_security=$(k get pods -n tool-services -l app.kubernetes.io/name=tool-service -o jsonpath="{.items[0].spec.automountServiceAccountToken} {.items[0].spec.securityContext.runAsNonRoot} {.items[0].spec.containers[0].securityContext.readOnlyRootFilesystem} {.items[0].spec.containers[0].securityContext.allowPrivilegeEscalation} {.items[0].spec.containers[0].securityContext.capabilities.drop[0]}")"
echo "tool_evidence=$(k get pods -n tool-services -l app.kubernetes.io/name=tool-service -o jsonpath="{range .items[0].spec.containers[0].volumeMounts[?(@.mountPath!=\"/aisec\")]}{.name}:{.mountPath}:{.readOnly} {end}{range .items[0].spec.volumes[?(@.configMap)]}{.configMap.name} {end}{.items[0].spec.containers[0].env[0].name}={.items[0].spec.containers[0].env[0].value}")"
echo "pod_security_admission=$(k get namespace tool-services orchestration -o jsonpath="{range .items[*]}{.metadata.labels.pod-security\.kubernetes\.io/enforce} {end}" | sed "s/ $//")"
echo "default_deny=$({ k get networkpolicy default-deny -n tool-services -o name; k get networkpolicy default-deny -n orchestration -o name; } | tr "\n" " " | sed "s/ $//")"
echo "tool_cert_14_days=$(openssl x509 -in /etc/aisec/tool-service/tls.crt -noout -checkend 1209600 >/dev/null 2>&1 && echo yes || echo no)"
audit=/var/log/aisec/tool-audit.jsonl
echo "audit_copy_active=$(systemctl is-active aisec-audit-copy 2>/dev/null)"
echo "audit_copy_enabled=$(systemctl is-enabled aisec-audit-copy 2>/dev/null)"
echo "audit_copy_code=$(cat /usr/local/lib/aisec/aisec_audit_copy.py /etc/systemd/system/aisec-audit-copy.service 2>/dev/null | sha256sum | cut -d " " -f 1)"
echo "audit_file=$(stat -c "%U %G %a" $audit 2>/dev/null) $(lsattr $audit 2>/dev/null | cut -d " " -f 1 | tr -cd a)"
ok_time=$(stat -c %Y /var/lib/aisec-audit-copy/ok 2>/dev/null || echo 0)
echo "audit_copy_recent=$([ $(( $(date +%s) - ok_time )) -le 10 ] && echo yes || echo no)"
echo "audit_mounts=$(count -c -x -E "/|/var/?|/var/log/?|/var/log/aisec(/.*)?" -- k3s kubectl get pods -A -o jsonpath="{range .items[*].spec.volumes[*]}{.hostPath.path}{\"\n\"}{end}")"
echo "audit_holes=$(python3 -I -c "
import json, sys
seen = {}
bad = 0
for raw in open(sys.argv[1], \"rb\"):
    try:
        line = json.loads(raw)
    except ValueError:
        bad += 1
        continue
    if isinstance(line, dict) and \"start\" in line:
        seen.setdefault(line[\"start\"], set()).add(line[\"seq\"])
print(bad + sum(max(numbers) - len(numbers) for numbers in seen.values()))
" $audit 2>&1 | tail -n 1)"
echo "audit_markers=$(grep -c "\"event\":\"copy\"" $audit 2>/dev/null)"
journal=/var/log/aisec/worker-journal.jsonl
echo "journal_timer=$(systemctl is-active aisec-journal-pull.timer 2>/dev/null) $(systemctl is-enabled aisec-journal-pull.timer 2>/dev/null)"
echo "journal_file=$(stat -c "%U %G %a" $journal 2>/dev/null) $(lsattr $journal 2>/dev/null | cut -d " " -f 1 | tr -cd a)"
ok_time=$(stat -c %Y /var/lib/aisec-journal-pull/ok 2>/dev/null || echo 0)
echo "journal_pull_recent=$([ $(( $(date +%s) - ok_time )) -le 1500 ] && echo yes || echo no)"
echo "journal_markers=$(grep -c "\"event\":\"copy\"" $journal 2>/dev/null)"
echo "journal_pull_code=$(cat /usr/local/lib/aisec/aisec_journal_pull.py /etc/systemd/system/aisec-journal-pull.service /etc/systemd/system/aisec-journal-pull.timer 2>/dev/null | sha256sum | cut -d " " -f 1)"
pinned=$(cut -d " " -f 2- /etc/aisec/journal-pull-known-hosts 2>/dev/null)
# OpenSSH 10 prints its banner as a comment on standard output. Only the key line counts.
offered=$(ssh-keyscan -T 8 -t ed25519 '"$WORK_IP"' 2>/dev/null | grep -v "^#" | cut -d " " -f 2-)
echo "journal_host_key=$([ -n "$pinned" ] && [ "$pinned" = "$offered" ] && echo match || echo differ)"
runuser -u aisec-journal-pull -- ssh -T -n -i /var/lib/aisec-journal-pull/id_ed25519 -o IdentitiesOnly=yes \
  -o UserKnownHostsFile=/etc/aisec/journal-pull-known-hosts -o GlobalKnownHostsFile=none \
  -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=8 aisec-logexport@'"$WORK_IP"' id >/dev/null 2>&1
echo "journal_export_refuses=$?"
echo "tool_egress=$(k3s kubectl exec -n tool-services deployment/tool-service -- python -c "
import socket
try:
    socket.create_connection((\"1.1.1.1\", 443), 5).close()
    print(\"open\")
except ConnectionRefusedError:
    print(\"refused\")
except TimeoutError:
    print(\"timeout\")
except OSError:
    print(\"other\")
" 2>&1 | tail -n 1)"
echo "argo_ready=$(k get deployment workflow-controller -n argo -o jsonpath="{.status.readyReplicas}")"
echo "argo_image=$(k get pods -n argo -l app=workflow-controller -o jsonpath="{.items[0].status.containerStatuses[0].imageID}" | sed "s/.*@//")"
echo "argo_args=$(k get deployment workflow-controller -n argo -o jsonpath="{.spec.template.spec.containers[0].args}")"
echo "argo_restriction=$(k get configmap workflow-controller-configmap -n argo -o jsonpath="{.data.workflowRestrictions}" | tr -d "\n")"
echo "argo_roles=$({ k get role argo-role -n argo -o jsonpath="{.rules}"; echo; k get role argo-role -n orchestration -o jsonpath="{.rules}"; echo; } | sort -u | grep -c .)"
echo "argo_executor_role=$(k get role argo-executor -n orchestration -o jsonpath="{.rules}")"
echo "argo_server=$(count -c -e argo-server -- k3s kubectl get deployments -A -o name)"
echo "argo_namespace=$(k get namespace argo -o jsonpath="{.metadata.labels.pod-security\.kubernetes\.io/enforce}") $(k get networkpolicy default-deny -n argo -o name)"
echo "argo_template=$(k get workflowtemplate investigate -n orchestration -o jsonpath="{.spec}" | sha256sum | cut -d " " -f 1)"
# W.12: each service account in argo, orchestration, and tool-services, asked
# whether it may create, update, patch, or delete a config map in
# orchestration. An error answers neither yes nor no.
answers=$(for ns in argo orchestration tool-services; do
  for sa in $(k get serviceaccounts -n "$ns" -o name); do
    for verb in create update patch delete; do
      k auth can-i "$verb" configmaps -n orchestration --as="system:serviceaccount:$ns:${sa#serviceaccount/}"
    done
  done
done)
echo "configmap_writers=$(printf "%s\n" "$answers" | grep -c "^yes$") $(printf "%s\n" "$answers" | grep -c "^no$")"
echo "argo_executor_token=$(k get secret argo-executor.service-account-token -n orchestration -o json | python3 -I -c "
import json, sys
secret = json.load(sys.stdin)
print(secret[\"type\"], secret[\"metadata\"][\"annotations\"][\"kubernetes.io/service-account.name\"],
      \"token\" if secret.get(\"data\", {}).get(\"token\") else \"empty\")
" 2>/dev/null)"
echo "dispatch_secret=$(k get secret dispatch-ssh -n orchestration -o json | python3 -I -c "
import base64, json, sys
data = json.load(sys.stdin)[\"data\"]
print(\" \".join(sorted(data)), base64.b64decode(data[\"known_hosts\"]).decode().strip())
" 2>/dev/null)"
'

probe_worker="$probe_common"'
code() { curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$@"; }
echo "internet=$(tcp 1.1.1.1 443)"
echo "targets_netbox=$(tcp 10.50.0.4 22)"
echo "targets_netbox_api=$(tcp 10.50.0.4 '"$NETBOX_PORT"')"
echo "targets_rehearsal=$(tcp 10.50.1.4 22)"
echo "targets_consumer=$(tcp '"$LAB_IP"' 22)"
echo "azure_dns=$(tcp 168.63.129.16 53)"
echo "azure_dns_udp=$(udp_dns)"
timeout 6 getent hosts example.com >/dev/null 2>&1; echo "resolve_public_name_rc=$?"
echo "orchestrator_ssh=$(tcp '"$ORCH_IP"' 22)"
echo "orchestrator_api=$(tcp '"$ORCH_IP"' 6443)"
echo "orchestrator_kubelet=$(tcp '"$ORCH_IP"' 10250)"
echo "edge_proxy=$(tcp '"$EDGE_IP"' 3128)"
echo "edge_target_proxy=$(tcp '"$EDGE_IP"' 3129)"
echo "proxy_archive=$(code -x '"$PROXY"' http://archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "proxy_security=$(code -x '"$PROXY"' http://security.ubuntu.com/ubuntu/dists/resolute-security/InRelease)"
echo "proxy_other_host=$(code -x '"$PROXY"' http://example.com/)"
echo "proxy_post=$(code -x '"$PROXY"' -X POST -d x http://archive.ubuntu.com/ubuntu/)"
echo "proxy_other_port=$(code -x '"$PROXY"' http://archive.ubuntu.com:8080/)"
echo "proxy_connect=$(curl -s -o /dev/null -w "%{http_connect}" --max-time 8 -x '"$PROXY"' https://example.com/ 2>/dev/null)"
echo "apt_proxy=$(apt-config dump 2>/dev/null | grep -c "Acquire::http::Proxy \"'"$PROXY"'\"")"
echo "unattended_upgrades=$(systemctl is-enabled unattended-upgrades 2>/dev/null)"
echo "security_updates_pending=$(count -c -e -security -- apt list --upgradable)"
echo "ip_forward=$(sysctl -n net.ipv4.ip_forward)"
echo "model_unit_active=$(systemctl is-active '"$MODEL_UNIT"' 2>/dev/null)"
echo "model_unit_enabled=$(systemctl is-enabled '"$MODEL_UNIT"' 2>/dev/null)"
echo "model_listen=$(ss -Hltnp | awk "\$4 ~ /:'"$MODEL_PORT"'\$/ {print \$4, \$6}" | sed "s/ users:((\"\([^\"]*\)\".*/ \1/" | tr "\n" " " | sed "s/ $//")"
echo "model_health=$(code http://127.0.0.1:'"$MODEL_PORT"'/health)"
echo "model_exposure=$(LC_ALL=C systemd-analyze security --no-pager '"$MODEL_UNIT"'.service 2>/dev/null | sed -n "s/.*Overall exposure level for [^:]*: \([0-9.]*\).*/\1/p")"
model_file=$(systemctl show '"$MODEL_UNIT"' -p ExecStart --value 2>/dev/null | sed -n "s/.* --model \([^ ]*\) .*/\1/p")
echo "model_sum=$(cd "$(dirname "$model_file")" 2>/dev/null && grep "  $(basename "$model_file")\$" SHA256SUMS 2>/dev/null | sha256sum --check --strict --status 2>/dev/null && echo match || echo differ)"
tool() { curl -s -o /dev/null -w "%{http_code}" --max-time 8 -X POST -d "{}" "$@"; }
echo "tool_port=$(tcp '"$ORCH_IP"' '"$TOOL_PORT"')"
echo "tool_no_token=$(tool --cacert '"$TOOL_CERT"' https://'"$TOOL_NAME"':'"$TOOL_PORT"'/mcp)"
echo "tool_untrusted=$(tool https://'"$TOOL_NAME"':'"$TOOL_PORT"'/mcp)"
echo "tool_wrong_name=$(tool --cacert '"$TOOL_CERT"' https://'"$ORCH_IP"':'"$TOOL_PORT"'/mcp)"
echo "tool_tls12=$(tool --cacert '"$TOOL_CERT"' --tls-max 1.2 https://'"$TOOL_NAME"':'"$TOOL_PORT"'/mcp)"
keys=/home/aisec-logexport/.ssh/authorized_keys
echo "export_key=$(wc -l < $keys 2>/dev/null) $(stat -c "%U %G %a" $keys 2>/dev/null) $(sed "s/ ssh-ed25519 .*//" $keys 2>/dev/null)"
echo "export_groups=$(id -nG aisec-logexport 2>/dev/null)"
echo "export_command=$(sha256sum /usr/local/sbin/aisec-journal-export 2>/dev/null | cut -d " " -f 1)"
echo "export_manager=$(u=$(id -u aisec-logexport 2>/dev/null); n=$(journalctl --no-pager -o cat --since -20min -u ssh.service 2>/dev/null | grep -c "Accepted publickey for aisec-logexport "); if [ -n "$u" ] && [ "$n" -gt 0 ]; then journalctl --no-pager -o cat --since -20min _SYSTEMD_UNIT=user@$u.service 2>/dev/null | wc -l; else echo no-logins; fi)"
keys=/home/aisec-feed/.ssh/authorized_keys
echo "feed_key=$(wc -l < $keys 2>/dev/null) $(stat -c "%U %G %a" $keys 2>/dev/null) $(sed "s/ ssh-ed25519 .*//" $keys 2>/dev/null)"
echo "feed_account=$(id -nG aisec-feed 2>/dev/null) $(sudo -n -l -U aisec-feed 2>/dev/null | grep -c "may run") $(stat -c %U /home/aisec-feed 2>/dev/null)"
echo "feed_command=$(sha256sum /usr/local/sbin/aisec-feed-receive 2>/dev/null | cut -d " " -f 1)"
echo "goose_binary=$(stat -c "%U %a" '"$GOOSE_BIN"' 2>/dev/null) $(sha256sum '"$GOOSE_BIN"' 2>/dev/null | cut -d " " -f 1)"
echo "fixture=$(cd '"$FIXTURE_DIR"' 2>/dev/null && sha256sum '"$FIXTURE_FILES"' 2>/dev/null | sha256sum | cut -d " " -f 1)"
echo "agent_job_unit=$(systemctl show aisec-agent-job -p LoadState --value 2>/dev/null)"
echo "agent_job_tmp=$(ls -d /tmp/systemd-private-*-aisec-agent-job.service-* /var/tmp/systemd-private-*-aisec-agent-job.service-* /tmp/systemd-private-*-aisec-agent-job@*.service-* /var/tmp/systemd-private-*-aisec-agent-job@*.service-* 2>/dev/null | wc -l)"
keys=/home/aisec-job/.ssh/authorized_keys
echo "job_key=$(wc -l < $keys 2>/dev/null) $(stat -c "%U %G %a" $keys 2>/dev/null) $(sed "s/ ssh-ed25519 .*//" $keys 2>/dev/null)"
echo "job_account=$(id -nG aisec-job 2>/dev/null) $(sudo -n -l -U aisec-job 2>/dev/null | grep -c "may run") $(stat -c %U /home/aisec-job 2>/dev/null)"
echo "job_session=$(grep -c "pam_succeed_if.so quiet user != aisec-job$" /etc/pam.d/common-session 2>/dev/null) $(cat /etc/security/aisec-light-session.conf 2>/dev/null)"
echo "job_socket=$(systemctl is-active aisec-agent-job.socket 2>/dev/null) $(stat -c "%U %G %a" /run/aisec-job/agent.sock 2>/dev/null)"
echo "job_programs=$(cat /usr/local/sbin/aisec-job-runner /usr/local/lib/aisec/job/agent_job.py /usr/local/lib/aisec/job/system.txt /etc/systemd/system/aisec-agent-job.socket /etc/systemd/system/aisec-agent-job@.service 2>/dev/null | sha256sum | cut -d " " -f 1)"
echo "job_instances=$(systemctl list-units --all --no-legend "aisec-agent-job@*" 2>/dev/null | wc -l)"
echo "slot_erased=$(journalctl --no-pager -o cat -u "aisec-agent-job@*" 2>/dev/null | sed -n "s/.*\"slot_erased\": \([a-z]*\).*/\1/p" | tail -n 1)"
echo "host_key=$(cut -d " " -f 1,2 /etc/ssh/ssh_host_ed25519_key.pub 2>/dev/null)"
'

probe_router="$probe_common"'
echo "unit_tailscaled=$(systemctl is-active tailscaled)"
echo "unit_mss_clamp=$(systemctl is-active aisec-mss-clamp)"
echo "mss_rules=$(nft list table inet aisec_mss 2>/dev/null | grep -c maxseg)"
echo "ip_forward=$(sysctl -n net.ipv4.ip_forward)"
echo "lock=$(tailscale lock status 2>/dev/null | head -n 1)"
echo "lock_signed=$(tailscale lock status 2>/dev/null | grep -c "This node is accessible under Tailnet Lock")"
echo "auth_key_file=$(ls /run/aisec 2>/dev/null | wc -l)"
echo "tailscale_held=$(apt-mark showhold | grep -c "^tailscale$")"
echo "tailscale_installed=$(dpkg-query -W -f="\${Version}" tailscale 2>/dev/null)"
echo "netbox_api=$(tcp '"$NETBOX_IP"' '"$NETBOX_PORT"')"
prefs=$(tailscale debug prefs 2>/dev/null | tr -d " \n")
pref() { printf "%s" "$prefs" | grep -o "\"$1\":[a-z]*" | head -n 1 | cut -d: -f2; }
echo "tailscale_auto_apply=$(printf "%s" "$prefs" | grep -o "\"AutoUpdate\":{[^}]*}" | grep -o "\"Apply\":[a-z]*" | cut -d: -f2)"
echo "tailscale_features=$(pref RunSSH) $(pref RunWebClient)"
echo "advertised_routes=$(printf "%s" "$prefs" | grep -o "\"AdvertiseRoutes\":\[[^]]*\]" | grep -o "[0-9./]*/[0-9]*" | sort | tr "\n" " " | sed "s/ $//")"
# The running agent, not the defaults file, so a restart with other flags shows.
echo "log_upload_off=$(tr "\0" " " < /proc/$(pidof tailscaled)/cmdline 2>/dev/null | grep -c -- "--no-logs-no-support")"
echo "serve_config=$(tailscale serve status --json 2>/dev/null | tr -d " \n")"
echo "mesh_udp=$(tailscale netcheck 2>/dev/null | sed -n "s/^[^A-Za-z]*UDP: //p" | head -n 1)"
echo "unattended_upgrades=$(systemctl is-enabled unattended-upgrades 2>/dev/null)"
echo "security_updates_pending=$(count -c -e -security -- apt list --upgradable)"
'

probe_edge="$probe_common"'
code() { curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$@"; }
echo "unit_squid=$(systemctl is-active squid)"
echo "squid_listen=$(ss -ltn | awk "{print \$4}" | grep -E ":312[89]$" | sort | tr "\n" " " | sed "s/ $//")"
echo "squid_no_new_privileges=$(systemctl show squid -p NoNewPrivileges --value)"
# The edge itself is neither client, so Squid refuses it.
echo "squid_from_edge=$(code -x '"$PROXY"' http://azure.archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "squid_from_edge_target_port=$(code -x '"$TARGET_PROXY"' http://azure.archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "window=$(stat -c "%U %a %s" /run/aisec/fetch-window.conf 2>/dev/null) $(systemctl is-active aisec-fetch-window-close.timer 2>/dev/null)"
echo "window_command=$(stat -c "%U %a" /usr/local/sbin/aisec-fetch-window 2>/dev/null) $(sha256sum /usr/local/sbin/aisec-fetch-window 2>/dev/null | cut -d " " -f 1)"
echo "fetch_hosts=$(sha256sum /etc/squid/aisec-fetch-hosts 2>/dev/null | cut -d " " -f 1)"
echo "squid_conf=$(stat -c "%U %a" /etc/squid/squid.conf 2>/dev/null) $(sha256sum /etc/squid/squid.conf 2>/dev/null | cut -d " " -f 1)"
echo "squid_command=$(tr "\0" " " < /proc/$(systemctl show squid -p MainPID --value)/cmdline 2>/dev/null | sed "s/ $//")"
dropin=/etc/systemd/system/squid.service.d/10-aisec.conf
echo "squid_dropins=$(systemctl show squid -p DropInPaths --value 2>/dev/null) $(sha256sum $dropin 2>/dev/null | cut -d " " -f 1)"
# When Squid last read squid.conf, at start or reload, against the newest
# change to any file its configuration reads. A file changed after that is not
# what Squid runs.
loaded=$(journalctl -u squid -b -o short-unix --no-pager 2>/dev/null |
  grep -F "Processing Configuration File: /etc/squid/squid.conf (depth 0)" | tail -n 1 | cut -d " " -f 1)
changed=$(find /etc/squid/squid.conf /etc/squid/aisec-fetch-hosts /run/aisec/fetch-window.conf -maxdepth 0 \
  -printf "%C@\n" 2>/dev/null | sort -n | tail -n 1)
echo "squid_loaded_after_change=$(awk -v l="$loaded" -v c="$changed" "BEGIN { print (l != \"\" && c != \"\" && l + 0 > c + 0) ? \"yes\" : \"no\" }")"
echo "mesh_agent=$(dpkg-query -W -f="\${Status}" tailscale 2>/dev/null | grep -c " ok installed$")"
echo "unattended_upgrades=$(systemctl is-enabled unattended-upgrades 2>/dev/null)"
echo "security_updates_pending=$(count -c -e -security -- apt list --upgradable)"
'

# The targets (ADR 0036). $1 is the other target's address.
probe_target="$probe_common"'
update_opt() { sshd -T -C user=aisec-update,host=check,addr='"$ORCH_IP"' 2>/dev/null | sed -n "s/^$1 //p"; }
echo "sshd_update=$(for k in authorizedkeysfile allowtcpforwarding permitlisten permitopen permittty forcecommand; do echo "$k $(update_opt $k)"; done | tr "\n" ";" | sed "s/;$//")"
keys=/etc/ssh/aisec-update-keys
echo "update_key=$(wc -l < $keys 2>/dev/null) $(stat -c "%U %G %a" $keys 2>/dev/null) $(sed "s/ ssh-ed25519 .*//" $keys 2>/dev/null)"
echo "update_key_body=$(grep -o "ssh-ed25519 [A-Za-z0-9+/=]*" $keys 2>/dev/null)"
echo "update_account=$(id -nG aisec-update 2>/dev/null) $(passwd -S aisec-update 2>/dev/null | cut -d " " -f 2)"
echo "update_sudo=$(sudo -n -l -U aisec-update 2>/dev/null | sed -n "/may run/,\$p" | tail -n +2 | sed "s/^ *//" | tr "\n" "|")"
echo "update_command=$(stat -c "%U %a" /usr/local/sbin/aisec-target-update 2>/dev/null) $(sha256sum /usr/local/sbin/aisec-target-update 2>/dev/null | cut -d " " -f 1)"
echo "apt_timers=$(systemctl is-enabled apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service unattended-upgrades.service 2>/dev/null | tr "\n" " " | sed "s/ $//")"
echo "apt_proxy=$(apt-config dump 2>/dev/null | grep -c "Acquire::http::Proxy \"http://127.0.0.1:3129\"")"
echo "forward_listener=$(ss -Hltn "sport = :3129" 2>/dev/null | wc -l)"
echo "internet=$(tcp 1.1.1.1 443)"
echo "azure_dns=$(tcp 168.63.129.16 53) $(udp_dns)"
echo "edge_proxy=$(tcp '"$EDGE_IP"' 3128) $(tcp '"$EDGE_IP"' 3129)"
echo "platform_ssh=$(tcp '"$ORCH_IP"' 22) $(tcp '"$WORK_IP"' 22)"
echo "other_target_ssh=$(tcp "$1" 22)"
echo "first_boot=$(stat -c "%U" /var/lib/aisec-first-boot.done 2>/dev/null)"
echo "apt_sources=$(grep -rhoE "^(URIs:|deb) +[^ ]+" /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null | awk "{print \$2}" | sort -u | tr "\n" " " | sed "s/ $//")"
# apt touches the stamp after each successful package list refresh. The image
# build made one too, so only a refresh after first boot counts.
stamp=/var/lib/apt/periodic/update-success-stamp
echo "last_update=$([ "$stamp" -nt /var/lib/aisec-first-boot.done ] && [ $(( $(date +%s) - $(stat -c %Y "$stamp") )) -le 604800 ] && echo yes || echo no) $(count -c -e -security -- apt list --upgradable) $([ -e /run/reboot-required ] && echo yes || echo no)"
'

common_checks() { # prefix
  check "$1.1" "No failed systemd unit" 0 "$(value failed_units)"
  check "$1.2" "SSH: no root login" no "$(value sshd_root)"
  check "$1.3" "SSH: no password login" no "$(value sshd_password)"
  check "$1.4" "SSH: no TCP forwarding" no "$(value sshd_tcp_forwarding)"
  check "$1.5" "SSH: no agent forwarding" no "$(value sshd_agent_forwarding)"
  check "$1.6" "SSH: three authentication tries" 3 "$(value sshd_max_auth_tries)"
  check "$1.7" "Kernel: SysRq off" 0 "$(value sysctl_sysrq)"
  check "$1.8" "Kernel: pointers hidden" 2 "$(value sysctl_kptr)"
  check "$1.9" "Kernel: ICMP redirects ignored" 0 "$(value sysctl_redirects)"
  check "$1.10" "Kernel: BPF JIT hardened" 2 "$(value sysctl_bpf_jit)"
  check "$1.11" "/etc/crontab is 600" 600 "$(value mode_crontab)"
  check "$1.12" "/etc/ssh/sshd_config is 600" 600 "$(value mode_sshd_config)"
  check "$1.13" "/etc/cron.d is 700" 700 "$(value mode_cron_d)"
  check "$1.14" "No assembler, linker, or compiler" 0 "$(value toolchain)"
  check "$1.15" "Unused network and USB storage modules not loaded" 0 "$(value unused_modules)"
  check "$1.16" "Clock is synchronized" yes "$(value time_synced)"
  check "$1.17" "SSH: the administrator takes only a certificate" \
    "none /etc/ssh/aisec-user-ca.pub /etc/ssh/aisec-principals /etc/ssh/aisec-revoked.krl" "$(value sshd_admin_auth)"
  # One key in the file, and it is the one on the workstation.
  check "$1.18" "SSH: the certificate authority is the operator's" "$USER_CA_FP 1" "$(value user_ca)"
  check "$1.19" "SSH: one principal, in root's file" "root root 644 aisec-operator" "$(value principals)"
  # sshd refuses every certificate if the list is missing or unreadable.
  check "$1.20" "SSH: the revocation list is root's and loads" "root root valid" "$(value revoked_keys)"
  check "$1.21" "Ubuntu's news, Pro status, and release checks are off" \
    "masked masked masked masked 644" "$(value ubuntu_fetchers)"
}

echo "== Orchestrator ($ORCH)"
if probe=$($SSH "$ORCH" 'sudo bash -s' <<<"$probe_orchestrator" 2>/dev/null) && [ -n "$probe" ]; then
  check A.1 "Reachable through the router with the operator certificate" yes yes
  check A.11 "The orchestrator is not on the mesh VPN" "0 0" "$(value mesh_agent)"
  check A.5 "No plain key is authorized for the administrator" 0 "$(value authorized_keys)"
  check A.8 "The administrator forwards only to the API server on loopback" "local 127.0.0.1:6443" "$(value sshd_admin_forwarding)"
  check A.9 "Other accounts forward nothing" no "$(value sshd_other_forwarding)"
  check K.1 "k3s is active" active "$(value unit_k3s)"
  check K.2 "The node is Ready" 1 "$(value node_ready)"
  # A workflow's pods end Completed or Error. The workflow's status says which.
  check K.3 "Every pod outside workflows is Running" "0 0" "$(value pods_not_running)"
  check K.4 "Secrets encryption is enabled" Enabled "$(value secrets_encryption)"
  check K.5 "Every certificate file is 600" 0 "$(value cert_modes_not_600)"
  check K.6 "No default service account mounts a token" "0 0" "$(value default_sa_automount)"
  check K.7 "The API server refuses anonymous requests" "--anonymous-auth=false" "$(value apiserver_anonymous)"
  # The kubelet's running configuration, as it reports it, so a later file in
  # its configuration folder or a flag cannot override it unseen.
  check K.8 "The kubelet refuses anonymous requests" "false Webhook" "$(value kubelet_auth)"
  # Pod security refuses it in every namespace, labelled or not: restricted
  # by default, baseline in kube-system by its label.
  check K.9 "Every namespace refuses a privileged pod" none "$(value privileged_admitted)"
  # A system pod that pod security refuses is never created, so K.3 does not
  # see it. Its deployment stays short of ready.
  check K.10 "Every system deployment is ready" 0 "$(value system_deployments_not_ready)"
  # The binary names them by tag. First boot imports them from the release's
  # archive, checked against its pin, and Docker Hub is not on the edge's
  # list, so a tag that moves upstream does not reach the cluster.
  check K.11 "K3s's system images are the ones in the release's archive" none "$(value system_images)"
  # Both addresses answer when the path is open, so a timeout is the
  # security group's deny. Before the way out closed, both were "open".
  check E.12 "The orchestrator opens no connection to the internet" timeout "$(value egress_https)"
  check E.13 "The orchestrator gets no answer from Azure DNS over TCP" timeout "$(value azure_dns)"
  check E.14 "The orchestrator gets no answer from Azure DNS over UDP" timeout "$(value azure_dns_udp)"
  check E.2 "The orchestrator reaches the worker on 22" open "$(value to_worker_ssh)"
  # Nothing listens on the worker's port 80. If its rules let the packet in,
  # the worker answers with a reset. Only a timeout shows the rules dropped it.
  check E.3 "The worker's rules drop the orchestrator on 80" timeout "$(value to_worker_http)"
  check E.4 "The feed key runs nothing but the feed command" 2 "$(value feed_refuses)"
  check E.15 "The orchestrator reaches both targets on 22" "open open" "$(value to_targets_ssh)"
  check E.16 "The targets' update key is root's and closed to others" "root 600" "$(value target_update_key | cut -d " " -f 1,2)"
  check E.17 "The update run command is root's and the one in this checkout" "root 700 $TARGET_RUN_SHA" "$(value target_update_run)"
  check E.18 "The update run pins both targets' host keys" "match match" "$(value target_update_pins)"
  # curl checks the certificate against the pinned file and nothing else.
  # 000 is no HTTP answer at all.
  check N.1 "The orchestrator reaches NetBox over TLS with the pinned certificate, and not in plain HTTP" \
    "200 000" "$(value netbox_api)"
  check N.2 "The pinned NetBox certificate is root's and not writable by others" "root 644" "$(value netbox_cert | cut -d " " -f 1,2)"
  # Kept for N.10, which reads the certificate file on the NetBox VM.
  NETBOX_CERT_FP=$(value netbox_cert | cut -d " " -f 3)
  # 403 and the orchestrator's own address, three times. A header that NetBox
  # believed would get 200, or the header's address.
  check N.12 "NetBox takes a token's client address from the connection, not from a header" \
    "403:$ORCH_IP 403:$ORCH_IP 403:$ORCH_IP" "$(value netbox_address)"
  check N.13 "The orchestrator's NetBox tokens are root's and closed to others" \
    "root 700 root 600 root 600" "$(value netbox_tokens)"
  # The collector reads each account's permissions with its own token, which
  # is limited to this address (ADR 0037).
  configured=$($SSH "$ORCH" "sudo python3 -I -c $(printf %q "$COLLECTOR_CODE") configured --summary" \
    <"$CONTRACT" 2>/dev/null)
  check N.14 "The configured permissions give the seeded excess and an unaffected control" \
    "$SEEDED_VERDICTS" "${configured:-not read}"
  check N.18 "The orchestrator's collector, collect command, contract, and cases are the ones in the two checkouts" \
    "$COLLECT_SHAS" "$(value netbox_collect)"
  check N.19 "The observer key is root's and closed to others, and pins the lab VM's host key the update run pins" \
    "root 700 root 600 1 same" "$(value netbox_observe_key) $(value netbox_observe_pin)"
  # Kept for each target's .6, which reads the key the target accepts.
  TARGET_UPDATE_KEY=$(value target_update_key | cut -d " " -f 3,4)
  check P.12 "Squid is not installed on the orchestrator" 0 "$(value squid_installed)"
  check P.13 "The edge serves the orchestrator's package mirror" 200 "$(value proxy_own_mirror)"
  check P.14 "The edge refuses the orchestrator another host" 403 "$(value proxy_worker_mirror)"
  # A procedure step opens a window and sees 200. The checks only read, so a
  # window open while they run shows here as a failure.
  check P.15 "The edge refuses the orchestrator a tunnel while no window is open" 403 "$(value proxy_tunnel)"
  # Port 3129, which an update run forwards to a target (ADR 0036). Its rules
  # come before the fetch window's, so P.27 holds during a window too. A
  # runbook step shows that, because the checks do not open one.
  check P.23 "The target port serves the orchestrator's mirror" 200 "$(value target_proxy_mirror)"
  check P.24 "The target port refuses another host" 403 "$(value target_proxy_other_host)"
  check P.25 "The target port refuses an upload" 403 "$(value target_proxy_post)"
  check P.26 "The target port refuses another port" 403 "$(value target_proxy_other_port)"
  check P.27 "The target port refuses a tunnel" 403 "$(value target_proxy_tunnel)"
  check U.10 "apt on the orchestrator uses the edge" 1 "$(value apt_proxy)"
  check U.11 "containerd pulls images through the edge" "$PROXY" "$(value containerd_proxy)"
  # The model server listens on the worker's loopback address only (S.4), so
  # this is E.3 again on the port that matters: nothing answers on this
  # address, a packet the rules let in gets a reset, and only a timeout shows
  # the rules dropped it.
  check S.1 "The worker's rules drop the orchestrator on the model server port" timeout "$(value to_worker_model)"
  check U.1 "No security update is pending on the orchestrator" "0 0" "$(value security_updates_pending)"
  # The chain as nft lists it, with the counter's values taken out. It holds
  # a pod from its first packet, before kube-router writes the pod's policy.
  # The one address outside the pods is the worker's SSH port (ADR 0030).
  check E.6 "Forwarded traffic from pods goes only to pods, and to the worker's SSH port" \
    "type filter hook forward priority filter + 10; policy accept;|ip saddr 10.42.0.0/16 ct state established,related accept|ip saddr 10.42.0.0/16 ip daddr 10.42.0.0/16 accept|ip saddr 10.42.0.0/16 ip daddr 10.40.0.36 tcp dport 22 accept|ip saddr 10.42.0.0/16 counter drop|" \
    "$(value pod_egress)"
  check E.7 "The pod egress rule loads at boot" enabled "$(value pod_egress_unit)"
  # The same for traffic from pods to the host itself (ADR 0023). Replies to
  # connections the host started, and the API server and the kubelet.
  check E.8 "Pods reach the host only on the API server and kubelet ports" \
    "type filter hook input priority filter + 10; policy accept;|ip saddr 10.42.0.0/16 ct state established,related accept|ip saddr 10.42.0.0/16 tcp dport { 6443, 10250 } accept|ip saddr 10.42.0.0/16 counter drop|" \
    "$(value pod_egress_input)"
  check T.1 "The tool service pod is ready" 1 "$(value tool_ready)"
  # The digest that runs, against the digest the reviewed manifest names. An
  # empty manifest digest is a failure, not a match.
  check T.2 "The tool service runs the image its manifest names" "${TOOL_IMAGE_DIGEST:-no digest in the manifest}" "$(value tool_image)"
  check T.3 "The tool service pod has no token, no root, and nothing writable" "false true true false ALL" "$(value tool_pod_security)"
  check T.4 "Both namespaces enforce the restricted pod security level" "restricted restricted" "$(value pod_security_admission)"
  # One read-only volume per target's evidence, outside /aisec, and the
  # variable that points the service at them (ADR 0040).
  check T.14 "The tool service mounts each target's evidence read-only, NetBox's from the collect command's config map" \
    "evidence-synthetic:/evidence/synthetic:true evidence-netbox:/evidence/netbox:true tool-service-evidence tool-service-evidence-netbox AISEC_EVIDENCE=/evidence" \
    "$(value tool_evidence)"
  check T.5 "Both namespaces deny by default" "networkpolicy.networking.k8s.io/default-deny networkpolicy.networking.k8s.io/default-deny" "$(value default_deny)"
  check T.7 "The tool service certificate has more than 14 days left" yes "$(value tool_cert_14_days)"
  # From inside the pod. K3s enforces network policies with kube-router, which
  # rejects with an ICMP port unreachable, so a blocked connection is
  # "refused", observed on 2026-10-15. The orchestrator itself reaches 443
  # (E.1), so without the policy this is "open". Any other end is a failure.
  check T.8 "The tool service pod cannot reach the internet" refused "$(value tool_egress)"
  # Argo (ADR 0029). The digest that runs and the flags that keep the
  # controller to orchestration, against argo.yaml in this checkout.
  check W.1 "The Argo controller is ready" 1 "$(value argo_ready)"
  check W.2 "The Argo controller runs the image argo.yaml names" "${ARGO_IMAGE_DIGEST:-no digest in argo.yaml}" "$(value argo_image)"
  check W.3 "The Argo controller manages orchestration only, with the pinned executor" "$ARGO_ARGS" "$(value argo_args)"
  # Without it, the right to create a workflow is the right to run any pod.
  check W.4 "The Argo controller runs only workflows that reference a template" "templateReferencing: Secure" "$(value argo_restriction)"
  # One distinct line: the Role in argo and its copy in orchestration match.
  check W.5 "The controller's Role in orchestration is a copy of its own" 1 "$(value argo_roles)"
  check W.6 "The executor may only record task results" \
    '[{"apiGroups":["argoproj.io"],"resources":["workflowtaskresults"],"verbs":["create","patch"]}]' "$(value argo_executor_role)"
  check W.7 "No Argo server runs in the cluster" "0 0" "$(value argo_server)"
  check W.8 "The argo namespace is restricted and denies by default" \
    "restricted networkpolicy.networking.k8s.io/default-deny" "$(value argo_namespace)"
  check W.9 "The workflow template is the one in this checkout" "$TEMPLATE_SHA" "$(value argo_template)"
  # Without it, every workflow pod waits on the mount and no step starts.
  check W.11 "The executor's token secret is for argo-executor and holds a token" \
    "kubernetes.io/service-account-token argo-executor token" "$(value argo_executor_token)"
  # The collect command writes each job's verdicts for the comparison step into
  # a config map in orchestration (ADR 0041). Seven accounts, four ways to
  # change it: no yes, and 28 answers of no.
  check W.12 "No workload account may change config maps in orchestration" "0 28" "$(value configmap_writers)"
  # Kept for W.10 in the worker's section, which reads the worker's own key.
  DISPATCH_SECRET=$(value dispatch_secret)
  check L.1 "The audit copier is active" active "$(value audit_copy_active)"
  check L.2 "The audit copier starts at boot" enabled "$(value audit_copy_enabled)"
  # Owner, group, mode, and the append-only attribute. The copier's group can
  # append, and nobody but root can remove the attribute.
  check L.3 "The audit file is root's and append-only" "root aisec-audit-copy 620 a" "$(value audit_file)"
  # Five times the copier's interval. A pass with nothing new still counts, and
  # a pass that finds no log file of the tool service does not (ADR 0019).
  check L.4 "The audit copier succeeded in the last 10 seconds" yes "$(value audit_copy_recent)"
  # A hostPath of the folder or anything above it would expose the file.
  check L.5 "No pod mounts the audit folder" "0 0" "$(value audit_mounts)"
  # Missing numbers within each start, plus lines that are not JSON. Lines
  # without a start, from the image before ADR 0019, are not counted.
  check L.6 "No audit line is missing" 0 "$(value audit_holes)"
  # A marker stands for a line the copier refused or a full file.
  check L.7 "The audit copier refused no line" 0 "$(value audit_markers)"
  # The program and unit installed, against this checkout. A missing file
  # changes the hash, so it fails too.
  check L.8 "The audit copier installed is the one in this checkout" "$COPY_SHA" "$(value audit_copy_code)"
  check J.1 "The journal pull timer is active and starts at boot" "active enabled" "$(value journal_timer)"
  check J.2 "The worker's journal file is root's and append-only" "root aisec-journal-pull 620 a" "$(value journal_file)"
  # Five times the timer's interval of five minutes.
  check J.3 "The journal pull succeeded in the last 25 minutes" yes "$(value journal_pull_recent)"
  check J.4 "The journal puller refused no line" 0 "$(value journal_markers)"
  # The key the puller pins, against the key the worker offers now. A missing
  # pin is a difference, not a match.
  check J.5 "The puller pins the worker's host key" match "$(value journal_host_key)"
  # Exit status 2 is the export refusing. 255 would be SSH failing, and 0 that
  # the key ran a command it should not.
  check J.6 "The export key runs nothing but the export" 2 "$(value journal_export_refuses)"
  check J.10 "The journal puller installed is the one in this checkout" "$PULL_SHA" "$(value journal_pull_code)"
  check O.1 "The log agent is installed and active on the orchestrator" "1 active" "$(value monitor_agent)"
  hosts_orchestrator=$(value monitor_hosts)
  common_checks HO
else
  check A.1 "Reachable through the router with the operator certificate" yes no
fi

echo
echo "== Worker ($WORK)"
if probe=$($SSH "$WORK" 'sudo bash -s' <<<"$probe_worker" 2>/dev/null) && [ -n "$probe" ]; then
  check A.6 "Reachable through the subnet router with the operator certificate" yes yes
  check A.7 "No plain key is authorized for the administrator" 0 "$(value authorized_keys)"
  check A.10 "The administrator forwards nothing on the worker" "no any" "$(value sshd_admin_forwarding)"
  # C.1 and C.4 aim at ports that are known to listen, so a timeout is a drop.
  check C.1 "No connection to the internet" timeout "$(value internet)"
  # The NetBox and lab VMs listen on 22 (E.15), so a timeout is a drop. No
  # machine is in the rehearsal subnet, so C.3 times out with or without the
  # deny rule. Z.6 names the rule.
  check C.2 "No connection to the NetBox subnet" timeout "$(value targets_netbox)"
  check C.11 "No connection to the consumer subnet" timeout "$(value targets_consumer)"
  # NetBox listens on its port (N.1), so a timeout is a drop.
  check C.12 "No connection to NetBox's port" timeout "$(value targets_netbox_api)"
  check C.3 "No connection to the rehearsal subnet" timeout "$(value targets_rehearsal)"
  check C.4 "No connection to the platform resolver" timeout "$(value azure_dns)"
  # The same query from the edge gets an answer, so a timeout here is the
  # worker's rule and not the resolver.
  check C.10 "No answer from the platform resolver over UDP" timeout "$(value azure_dns_udp)"
  check C.5 "A public name does not resolve" no "$([ "$(value resolve_public_name_rc)" = 0 ] && echo yes || echo no)"
  # All three ports listen on the orchestrator: E.2 and M.1 reach 22, M.2
  # reaches 6443, and the kubelet runs with k3s. A timeout is a drop.
  check C.6 "No connection to the orchestrator on 22" timeout "$(value orchestrator_ssh)"
  check C.7 "No connection to the Kubernetes API" timeout "$(value orchestrator_api)"
  check C.8 "No connection to the kubelet" timeout "$(value orchestrator_kubelet)"
  check C.9 "The worker does not forward packets" 0 "$(value ip_forward)"
  check P.5 "The worker reaches the proxy port on the edge" open "$(value edge_proxy)"
  # Squid listens on 3129 (P.2), so a timeout is the rules. "refused" would
  # mean the packet reached the edge.
  check P.28 "The worker's rules drop the target port on the edge" timeout "$(value edge_target_proxy)"
  check P.6 "The proxy serves archive.ubuntu.com" 200 "$(value proxy_archive)"
  check P.7 "The proxy serves security.ubuntu.com" 200 "$(value proxy_security)"
  check P.8 "The proxy refuses another host" 403 "$(value proxy_other_host)"
  check P.9 "The proxy refuses an upload" 403 "$(value proxy_post)"
  check P.10 "The proxy refuses another port" 403 "$(value proxy_other_port)"
  check P.11 "The proxy refuses a tunnel" 403 "$(value proxy_connect)"
  check S.2 "The model server unit is active" active "$(value model_unit_active)"
  check S.3 "The model server unit starts at boot" enabled "$(value model_unit_enabled)"
  check S.4 "The model server is the only listener on its port, on loopback" "127.0.0.1:$MODEL_PORT llama-server" "$(value model_listen)"
  check S.5 "The model server answers with a loaded model" 200 "$(value model_health)"
  # The score systemd gives the unit's sandbox settings, as observed on
  # 2026-10-11. A setting taken out of the unit moves it. So does a systemd
  # release that scores differently, and then the new value needs a look.
  check S.6 "The model server unit's exposure score is unchanged" 1.3 "$(value model_exposure)"
  # The file named on the unit's command line, against the line for it in the
  # SHA256SUMS the build wrote. No line for that file is "differ", not a pass.
  check S.7 "The model file the server loads matches its checksum from the build" match "$(value model_sum)"
  check T.9 "The worker reaches the tool port" open "$(value tool_port)"
  # Through TLS with the pinned certificate and the name in it, to a refusal:
  # the service answers, and wants a token.
  check T.10 "The tool service refuses a call without a token" 401 "$(value tool_no_token)"
  # 000 is curl's code for no HTTP answer. Here it means the TLS handshake failed.
  check T.11 "The system's trust store does not trust the tool service" 000 "$(value tool_untrusted)"
  check T.12 "The certificate does not cover the bare address" 000 "$(value tool_wrong_name)"
  check T.13 "The tool service refuses TLS 1.2" 000 "$(value tool_tls12)"
  # One key, root's file, and the options that tie it to the orchestrator's
  # address and the export command.
  check J.7 "The export key is restricted to the orchestrator and the export" \
    "1 root root 644 from=\"$ORCH_IP\",restrict,command=\"/usr/local/sbin/aisec-journal-export\"" "$(value export_key)"
  check J.8 "The export account reads the journal and nothing more" "aisec-logexport systemd-journal" "$(value export_groups)"
  # The export command is the boundary on the worker. It has to be the
  # reviewed one.
  check J.9 "The worker runs the export command in this checkout" "$EXPORT_SHA" "$(value export_command)"
  # Each pull is a login. A login that starts the account's user service
  # manager logs about 67 lines, which the next pull copies (issue 164).
  # Without a pull in the last 20 minutes this reads no-logins.
  check J.11 "The export account's logins start no user service manager" 0 "$(value export_manager)"
  # The same shape for the feed key (ADR 0026).
  check E.9 "The feed key is restricted to the orchestrator and the feed command" \
    "1 root root 644 from=\"$ORCH_IP\",restrict,command=\"/usr/local/sbin/aisec-feed-receive\"" "$(value feed_key)"
  check E.10 "The feed account has no other group, no sudo, and not its own home" "aisec-feed 0 root" "$(value feed_account)"
  check E.11 "The worker runs the feed command in this checkout" "$FEED_SHA" "$(value feed_command)"
  # The agent runtime. The binary against its pin, not against the checksum
  # file the install wrote beside it.
  check G.1 "The Goose binary is root's and the one pinned in this checkout" "root 755 $GOOSE_BIN_SHA" "$(value goose_binary)"
  check G.2 "The fixture tool and its prompts are the ones in this checkout" "$FIXTURE_SHA" "$(value fixture)"
  # The checks run between jobs. During a job these read "loaded" and 2.
  check G.3 "No agent job unit is loaded" not-found "$(value agent_job_unit)"
  check G.4 "No agent job left its private directories" 0 "$(value agent_job_tmp)"
  # How a job arrives (ADR 0030): the dispatch key's line, the account it logs
  # in to, the socket that starts each job's unit, and what runs there.
  check G.5 "The dispatch key is restricted to the orchestrator and the job runner" \
    "1 root root 644 from=\"$ORCH_IP\",restrict,command=\"/usr/local/sbin/aisec-job-runner\"" "$(value job_key)"
  check G.6 "The job account has no other group, no sudo, and not its own home" "aisec-job 0 root" "$(value job_account)"
  check G.7 "The job socket listens, and only root and the job account may use it" "active root aisec-job 660" "$(value job_socket)"
  check G.8 "The worker runs the job runner, program, and units in this checkout" "$JOB_SHA" "$(value job_programs)"
  check G.9 "No dispatched job's unit is loaded between jobs" 0 "$(value job_instances)"
  # The job program erases the model server's slot after each job (#32), and
  # its last line says whether the server did. A worker that has run no job
  # fails this.
  slot_erased=$(value slot_erased)
  check G.10 "The last job erased the model server's slot" true "${slot_erased:-no job outcome in the journal}"
  # The job account gets the export account's light session (issue 164). It
  # logs in only during a job, so this reads the PAM configuration.
  check G.11 "The job account's sessions start no user service manager" \
    "1 XDG_SESSION_CLASS DEFAULT=background-light" "$(value job_session)"
  # The dispatch secret, read in the orchestrator's section, holds the key and
  # the worker's host key, and that host key is this worker's.
  check W.10 "The dispatch secret pins this worker's host key" \
    "id_ed25519 known_hosts $WORK_IP $(value host_key)" "${DISPATCH_SECRET:-no dispatch secret read}"
  check U.3 "apt on the worker uses the edge" 1 "$(value apt_proxy)"
  check U.4 "Unattended upgrades are enabled on the worker" enabled "$(value unattended_upgrades)"
  check U.5 "No security update is pending on the worker" "0 0" "$(value security_updates_pending)"
  # The worker ships nothing (ADR 0021). Its journal leaves with the orchestrator.
  check O.4 "No log agent on the worker" 0 "$(value monitor_agent | cut -d " " -f 1)"
  common_checks HW
else
  check A.6 "Reachable through the subnet router with the operator certificate" yes no
fi

echo
echo "== Router ($ROUTER)"
if probe=$($SSH "$ROUTER" 'sudo bash -s' <<<"$probe_router" 2>/dev/null) && [ -n "$probe" ]; then
  check A.12 "Reachable over the mesh VPN with the operator certificate" yes yes
  check A.2 "Mesh VPN node signing is enabled" "Tailnet Lock is ENABLED." "$(value lock)"
  check A.3 "The router's node key is signed" 1 "$(value lock_signed)"
  check A.4 "The spent auth key file is gone" 0 "$(value auth_key_file)"
  check A.13 "No plain key is authorized for the administrator" 0 "$(value authorized_keys)"
  # Routed sessions pass through the router at the IP layer. SSH on the router
  # forwards nothing, for any account.
  check A.14 "The administrator forwards nothing on the router" "no any" "$(value sshd_admin_forwarding)"
  check R.1 "The mesh VPN agent is active" active "$(value unit_tailscaled)"
  check R.2 "The segment size clamp is loaded" "active 2" "$(value unit_mss_clamp) $(value mss_rules)"
  check R.3 "The router forwards packets" 1 "$(value ip_forward)"
  check R.4 "The router advertises the platform, the targets, and the edge subnet" "$ROUTES" "$(value advertised_routes)"
  # The flag on the running agent's command line (ADR 0025). The defaults file
  # alone would not show an agent started without it.
  check R.5 "The mesh VPN agent uploads no logs to the vendor" 1 "$(value log_upload_off)"
  check R.6 "Tailscale SSH and the web client are off" "false false" "$(value tailscale_features)"
  # An empty configuration is "{}". No answer is a failure, not a match.
  check R.7 "Nothing is served or funnelled through the mesh VPN" "{}" "$(value serve_config)"
  # NetBox listens on its port (N.1). The router's rules allow only SSH to the
  # targets, for its own connections and the sessions it routes, so a timeout
  # is a drop.
  check N.3 "The router's rules drop NetBox's port" timeout "$(value netbox_api)"
  # The router's rules have no UDP to the internet, so it cannot reach a STUN
  # server, and the agent uses the relays over TCP 443.
  check E.5 "The router sends no UDP to the internet" false "$(value mesh_udp)"
  check U.2 "The mesh VPN agent is held at its pinned version" 1 "$(value tailscale_held)"
  # The hold stops apt. The agent has its own updater, which the hold does not stop.
  check U.6 "The mesh VPN agent does not install updates itself" false "$(value tailscale_auto_apply)"
  # The hold means nothing moves the agent but the pin. This catches a pin left
  # behind. The current stable version is read here, from the package site.
  stable=$(curl -fsS --max-time 10 "https://pkgs.tailscale.com/stable/?mode=json" 2>/dev/null |
    python3 -I -c "import json, sys; print(json.load(sys.stdin)[\"Version\"])" 2>/dev/null)
  check U.7 "The mesh VPN agent is the current stable release" \
    "${stable:-no answer from pkgs.tailscale.com}" "$(value tailscale_installed)"
  check U.8 "Unattended upgrades are enabled on the router" enabled "$(value unattended_upgrades)"
  check U.9 "No security update is pending on the router" "0 0" "$(value security_updates_pending)"
  check O.3 "The log agent is installed and active on the router" "1 active" "$(value monitor_agent)"
  hosts_router=$(value monitor_hosts)
  common_checks HR
else
  check A.12 "Reachable over the mesh VPN with the operator certificate" yes no
fi

echo
echo "== Edge ($EDGE)"
if probe=$($SSH "$EDGE" 'sudo bash -s' <<<"$probe_edge" 2>/dev/null) && [ -n "$probe" ]; then
  check A.15 "Reachable through the router with the operator certificate" yes yes
  check A.16 "No plain key is authorized for the administrator" 0 "$(value authorized_keys)"
  check A.17 "The administrator forwards nothing on the edge" "no any" "$(value sshd_admin_forwarding)"
  check A.18 "The edge is not on the mesh VPN" 0 "$(value mesh_agent)"
  check P.1 "Squid is active" active "$(value unit_squid)"
  check P.2 "Squid listens on the edge's private address only" "$EDGE_IP:3128 $EDGE_IP:3129" "$(value squid_listen)"
  check P.3 "Squid cannot gain privileges" yes "$(value squid_no_new_privileges)"
  check P.4 "Squid refuses a client outside the two subnets" 403 "$(value squid_from_edge)"
  check P.29 "Squid refuses the target port to any client but the orchestrator" 403 "$(value squid_from_edge_target_port)"
  # Empty file, no close timer: no window is open while the checks run.
  check P.16 "No fetch window is open" "root 644 0 inactive" "$(value window)"
  check P.17 "The fetch window command is root's and the one in this checkout" "root 700 $WINDOW_SHA" "$(value window_command)"
  check P.18 "Squid's fetch host list is the one in this checkout" "$HOSTS_SHA" "$(value fetch_hosts)"
  check P.19 "Squid's configuration is root's and the edge template's" "root 644 $SQUID_CONF_SHA" "$(value squid_conf)"
  # The running process, so a unit changed to start Squid with -f and another
  # file shows. The command line is the Ubuntu package's unit. A package
  # update that changes it needs a look.
  check P.20 "Squid runs with the default configuration file" "/usr/sbin/squid --foreground -sYC" "$(value squid_command)"
  check P.21 "Squid's only unit drop-in is the edge template's" \
    "/etc/systemd/system/squid.service.d/10-aisec.conf $SQUID_DROPIN_SHA" "$(value squid_dropins)"
  # P.19 reads the file. This shows Squid read it after its last change, so the
  # file is what runs. A configuration edited, reloaded, and put back fails
  # here until Squid is reloaded again. So does a fetch window file emptied
  # without the reload the window command does.
  check P.22 "Squid loaded its configuration after the files last changed" yes "$(value squid_loaded_after_change)"
  check U.12 "Unattended upgrades are enabled on the edge" enabled "$(value unattended_upgrades)"
  check U.13 "No security update is pending on the edge" "0 0" "$(value security_updates_pending)"
  check O.2 "The log agent is installed and active on the edge" "1 active" "$(value monitor_agent)"
  hosts_edge=$(value monitor_hosts)
  common_checks HE
else
  check A.15 "Reachable through the router with the operator certificate" yes no
fi

# The NetBox and lab VMs. The same checks on each, with the prefix V and the
# VM's letter, and the hardening checks with H and the same letter.
target_checks() { # letter name host other-target-address update-check-ID
  echo
  echo "== $2 ($3)"
  # The address the target sees the session come from, read before sudo.
  if probe=$($SSH "$3" 'echo "ssh_client=${SSH_CLIENT%% *}"; sudo bash -s '"$4" <<<"$probe_target" 2>/dev/null) &&
    [ -n "$(value failed_units)" ]; then
    # The router hides the workstation's mesh address behind its own.
    check "V$1.1" "Reachable through the router with the operator certificate" "$ROUTER_IP" "$(value ssh_client)"
    check "V$1.2" "No plain key is authorized for the administrator" 0 "$(value authorized_keys)"
    check "V$1.3" "The administrator forwards nothing" "no any" "$(value sshd_admin_forwarding)"
    # The orchestrator's update key (ADR 0036): one command, and one listener
    # on loopback for the forwarded port.
    check "V$1.4" "SSH: the update account has one command and one remote forward" \
      "authorizedkeysfile /etc/ssh/aisec-update-keys;allowtcpforwarding remote;permitlisten 127.0.0.1:3129;permitopen none;permittty no;forcecommand sudo -n /usr/local/sbin/aisec-target-update" \
      "$(value sshd_update)"
    check "V$1.5" "The update key is restricted to the orchestrator and the one forward" \
      "1 root root 644 from=\"$ORCH_IP\",restrict,port-forwarding,permitlisten=\"127.0.0.1:3129\"" "$(value update_key)"
    check "V$1.6" "The update key is the orchestrator's" "${TARGET_UPDATE_KEY:-no update key read on the orchestrator}" "$(value update_key_body)"
    check "V$1.7" "The update account has no other group and no password" "aisec-update L" "$(value update_account)"
    # An empty argument list: sudo refuses the command with any argument.
    check "V$1.8" "The update account may run the update command, without arguments, and nothing else" \
      '(root) NOPASSWD: /usr/local/sbin/aisec-target-update ""|' "$(value update_sudo)"
    check "V$1.9" "The update command is root's and the one in the targets checkout" "root 755 $TARGET_UPDATE_SHA" "$(value update_command)"
    # Between update runs there is no path to a mirror, so these could only fail.
    check "V$1.10" "apt's timers and unattended upgrades are masked" \
      "masked masked masked masked masked" "$(value apt_timers)"
    check "V$1.11" "apt uses the port an update run forwards" 1 "$(value apt_proxy)"
    # A listener here between runs is a session left open, or a process in
    # the forward's place.
    check "V$1.12" "Nothing listens on the forwarded port between update runs" 0 "$(value forward_listener)"
    # Every far end listens: 1.1.1.1 on 443, Azure DNS (it answers the edge),
    # Squid on both ports (P.2), sshd on the orchestrator, the worker, and the
    # other target. A timeout is a drop.
    check "V$1.13" "No connection to the internet" timeout "$(value internet)"
    check "V$1.14" "No answer from Azure DNS over TCP or UDP" "timeout timeout" "$(value azure_dns)"
    check "V$1.15" "No connection to either proxy port on the edge" "timeout timeout" "$(value edge_proxy)"
    check "V$1.16" "No connection to the orchestrator or the worker on 22" "timeout timeout" "$(value platform_ssh)"
    check "V$1.17" "No connection to the other target on 22" timeout "$(value other_target_ssh)"
    check "V$1.18" "First boot ran to its end" root "$(value first_boot)"
    # Squid's target port serves this mirror and no other host (P.24).
    check "V$1.20" "apt's sources name only the mirror the target port serves" \
      "http://azure.archive.ubuntu.com/ubuntu/" "$(value apt_sources)"
    # Nothing updates a target between runs (ADR 0036), so the list a run left
    # behind is the one read here. Seven days, so a missed run shows.
    check "$5" "An update run in the last 7 days, no security update pending, no reboot required" \
      "yes 0 0 no" "$(value last_update)"
    # Nothing from the targets reaches Azure Monitor: an accepted gap.
    check "V$1.19" "No log agent" 0 "$(value monitor_agent | cut -d " " -f 1)"
    common_checks "H$1"
  else
    check "V$1.1" "Reachable through the router with the operator certificate" "$ROUTER_IP" "not reached"
  fi
}
target_checks N NetBox "$NETBOX" "$LAB_IP" U.14
target_checks L Lab "$LAB" "$NETBOX_IP" U.15

# NetBox on its VM (ADR 0035). A value that podman could not read is printed
# as an error, so that it cannot compare as equal.
probe_netbox='
echo "units=$(systemctl is-active netbox netbox-worker postgresql valkey-server 2>/dev/null | tr "\n" " " | sed "s/ $//")"
echo "images=$(podman inspect --format "{{.Image}}" netbox netbox-worker 2>/dev/null | tr "\n" " " | sed "s/ $//")"
echo "container=$(podman inspect --format "{{.Config.User}} {{.HostConfig.ReadonlyRootfs}} {{.HostConfig.Privileged}}" netbox netbox-worker 2>/dev/null | tr "\n" ";" | sed "s/;$//")"
if env=$(podman inspect --format "{{range .Config.Env}}{{println .}}{{end}}" netbox netbox-worker 2>/dev/null) && [ -n "$env" ]; then
  echo "env_secrets=$(printf "%s\n" "$env" | cut -d = -f 1 | grep -c -i -E "password|secret|pepper")"
else
  echo "env_secrets=no containers read"
fi
echo "listeners=$(ss -Hltn | awk "{print \$4}" | grep -v -E "^(127\.|\[::1\]:)" | sed "s/.*://" | sort -un | tr "\n" " " | sed "s/ $//")"
echo "valkey_auth=$(valkey-cli -h 127.0.0.1 ping 2>&1 | cut -d " " -f 1)"
echo "cert=$(openssl x509 -in /etc/aisec/netbox/tls.crt -noout -fingerprint -sha256 2>/dev/null | cut -d = -f 2)"
'
echo
echo "== NetBox service ($NETBOX)"
if probe=$($SSH "$NETBOX" 'sudo bash -s' <<<"$probe_netbox" 2>/dev/null) && [ -n "$(value units)" ]; then
  check N.4 "NetBox, its worker, PostgreSQL, and Valkey run" "active active active active" "$(value units)"
  check N.5 "Both containers run the image the targets checkout pins" "$NETBOX_IMAGE_ID $NETBOX_IMAGE_ID" "$(value images)"
  check N.6 "Both containers run as the image's netbox account, read-only and unprivileged" \
    "999:0 true false;999:0 true false" "$(value container)"
  check N.7 "No secret in the containers' environment" 0 "$(value env_secrets)"
  # PostgreSQL and Valkey listen on loopback only.
  check N.8 "Only SSH and NetBox's port listen beyond loopback" "22 $NETBOX_PORT" "$(value listeners)"
  check N.9 "Valkey refuses a client without the password" NOAUTH "$(value valkey_auth)"
  check N.10 "The certificate file on the NetBox VM is the one the orchestrator pins" \
    "${NETBOX_CERT_FP:-no certificate read on the orchestrator}" "$(value cert)"
else
  check N.4 "NetBox, its worker, PostgreSQL, and Valkey run" "active active active active" "not reached"
fi
# The consumer's subnet is the one other source the rules allow.
lab_port=$($SSH "$LAB" "$tcp_fn"'
tcp '"$NETBOX_IP $NETBOX_PORT" 2>/dev/null)
check N.11 "The consumer subnet reaches NetBox's port" open "${lab_port:-not reached}"
# The consumer's and the control account's tokens, and the certificate they
# trust, on the consumer viewpoint (ADR 0037).
probe=$($SSH "$LAB" 'sudo bash -s' 2>/dev/null <<<'
t=/etc/aisec/netbox/tokens
echo "tokens=$(stat -c "%U %a" $t $t/inventory-reader $t/inventory-reader-control 2>/dev/null | tr "\n" " " | sed "s/ $//")"
echo "cert=$(openssl x509 -in /etc/aisec/netbox/tls.crt -noout -fingerprint -sha256 2>/dev/null | cut -d = -f 2)"
# The observer account (ADR 0040), as sshd applies it to the orchestrator.
echo "observer=$(sshd -T -C user=aisec-observe,host=orchestrator,addr='"$ORCH_IP"' 2>/dev/null |
  grep -E "^(authorizedkeysfile|allowtcpforwarding|permittty|forcecommand) " | sort | tr "\n" ";")"
keys=/etc/ssh/aisec-observe-keys
echo "observer_keys=$(stat -c "%U %a" $keys 2>/dev/null) $(wc -l <$keys 2>/dev/null) $(cut -d " " -f 1 $keys 2>/dev/null)"
echo "observer_sudo=$(grep -v -e "^#" -e "^$" /etc/sudoers.d/91-aisec-observe 2>/dev/null | tr "\n" ";")"
echo "observer_collector=$(sha256sum /usr/local/lib/aisec/netbox_access.py 2>/dev/null | cut -d " " -f 1)"
')
check N.15 "The lab VM's NetBox tokens are root's and closed to others" "root 700 root 600 root 600" "$(value tokens)"
check N.16 "The lab VM's copy of NetBox's certificate is the one the orchestrator pins" \
  "${NETBOX_CERT_FP:-no certificate read on the orchestrator}" "$(value cert)"
# Each account's own reads, from the viewpoint its token is limited to. The
# same verdicts as N.14: the two methods agree.
observed=$($SSH "$LAB" "sudo python3 -I -c $(printf %q "$COLLECTOR_CODE") observed --summary" \
  <"$CONTRACT" 2>/dev/null)
check N.17 "The records each token returns give the seeded excess and an unaffected control" \
  "$SEEDED_VERDICTS" "${observed:-not read}"
check N.20 "The lab VM's observer account takes its key from root's file, with no forwarding, no TTY, and one command" \
  "allowtcpforwarding no;authorizedkeysfile /etc/ssh/aisec-observe-keys;forcecommand sudo -n /usr/local/sbin/aisec-observe-netbox;permittty no;" \
  "$(value observer)"
check N.21 "The observer's key file holds one key, limited to the orchestrator, and sudo allows it one command" \
  "root 644 1 from=\"$ORCH_IP\",restrict aisec-observe ALL=(root) NOPASSWD: /usr/local/sbin/aisec-observe-netbox \"\";" \
  "$(value observer_keys) $(value observer_sudo)"
check N.22 "The lab VM's copy of the collector is the one in this checkout" "$COLLECTOR_SHA" "$(value observer_collector)"
# The collect command's own path to the observed half. The command it asks
# for, id, is not what runs: the forced command is, with the contract on its
# standard input, and its verdicts are N.17's.
observer_run=$($SSH "$ORCH" "sudo ssh -F none -i /etc/aisec/netbox/observe/id_ed25519 -o IdentitiesOnly=yes \
  -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/aisec/netbox/observe/known_hosts \
  -T aisec-observe@$LAB_IP id" <"$CONTRACT" 2>/dev/null | python3 -I -c 'import json, sys
try:
    accounts = json.load(sys.stdin)["accounts"]
    print(" ".join(a + ":" + v["verdict"] for a, v in accounts.items()))
except (ValueError, KeyError, TypeError):
    print("not a report")')
check N.23 "From the orchestrator, the observer account runs the observed half and nothing else" \
  "$SEEDED_VERDICTS" "$observer_run"

if [ "$workstation" = 1 ]; then
  echo
  echo "== Workstation, through the mesh VPN"
  eval "$tcp_fn"
  check M.1 "The mesh policy allows SSH to the orchestrator" open "$(tcp $ORCH_IP 22 6)"
  # The API server listens on this address (K.1). The policy no longer grants
  # it: kubectl goes through an SSH tunnel to the orchestrator (A.8).
  check M.2 "The mesh policy drops the Kubernetes API" timeout "$(tcp $ORCH_IP 6443 6)"
  # Squid listens on the edge (P.2), and the kubelet on the orchestrator (C.8
  # above). The mesh drops what its policy does not grant, so a timeout is the
  # policy. "refused" would mean the packet reached the VM.
  check M.3 "The mesh policy drops the proxy port on the edge" timeout "$(tcp $EDGE_IP 3128 6)"
  check M.9 "The mesh policy drops the target port on the edge" timeout "$(tcp $EDGE_IP 3129 6)"
  check M.8 "The mesh policy allows SSH to the edge" open "$(tcp $EDGE_IP 22 6)"
  check M.4 "The mesh policy drops the kubelet port" timeout "$(tcp $ORCH_IP 10250 6)"
  check M.5 "The mesh policy drops the tool port" timeout "$(tcp $ORCH_IP $TOOL_PORT 6)"
  check M.6 "The mesh policy allows SSH to the router" open "$(tcp "$ROUTER" 22 6)"
  # Nothing listens on the router's port 80. If the policy let the packet in,
  # the router would answer with a reset. Only a timeout shows the drop.
  check M.7 "The mesh policy drops another port on the router" timeout "$(tcp "$ROUTER" 80 6)"
fi

if [ "$azure" = 1 ]; then
  echo
  echo "== Azure, as the operator"
  # Both groups. An empty answer is not 0, so a failed call fails.
  check Z.1 "No VM has a public address" "0 0" \
    "$(az vm list -g $RG -d --query "length([?publicIps!=''])" -o tsv 2>/dev/null) $(az vm list -g $RG_TARGETS -d \
      --query "length([?publicIps!=''])" -o tsv 2>/dev/null)"
  # The edge network's gateway is the platform's only way out (ADR 0020).
  check Z.2 "The platform group holds one public address, the NAT gateway's" 1 \
    "$(az network public-ip list -g $RG --query "length(@)" -o tsv 2>/dev/null)"
  check Z.3 "The target group holds no public address" 0 \
    "$(az network public-ip list -g $RG_TARGETS --query "length(@)" -o tsv 2>/dev/null)"

  # Effective rules equal configured rules, field by field: direction,
  # priority, access, name, protocol, both address lists, both port lists. A
  # rule that keeps its name and changes its port is a difference.
  #
  # The two commands spell the same rule differently. Effective rules say "All"
  # for any protocol, "0.0.0.0/0" and "::/0" for any address, "22-22" for port
  # 22, and fill both the single and the list field. nsg_rules puts both in one
  # form and sorts every list. A configured "0.0.0.0/0" reads as any address,
  # which is what it means to a rule.
  #
  # Two differences are allowed. Azure's default rules are in every effective
  # list and in no configured one. The platform adds one IPv6 deny through its
  # network manager, and only that rule from that source is skipped: a second
  # security group on the interface would still show up. The target side has
  # no network manager.
  nsg_normalise='
import json, sys

ANY = {"*", "0.0.0.0/0", "::/0"}

def values(rule, one, many):
    found = set(rule.get(many) or [])
    if rule.get(one):
        found.add(rule[one])
    return found

def addresses(rule, side):
    found = values(rule, side + "AddressPrefix", side + "AddressPrefixes")
    return ",".join(sorted({"*" if a in ANY else a for a in found}))

def ports(rule, side):
    found = values(rule, side + "PortRange", side + "PortRanges")
    spans = {"0-65535" if p == "*" else p if "-" in p else p + "-" + p for p in found}
    return ",".join(sorted(spans))

try:
    doc = json.load(sys.stdin)
except ValueError:
    sys.exit("the answer is not JSON")
if sys.argv[1] == "effective":
    rules = []
    for group in doc["value"]:
        managed = bool((group.get("association") or {}).get("networkManager"))
        for rule in group["effectiveSecurityRules"]:
            if managed and rule["name"].endswith("DefaultIPv6OutboundDeny"):
                continue
            rules.append(rule)
else:
    rules = doc["securityRules"]

lines = []
for rule in rules:
    if rule["name"].startswith("defaultSecurityRules/"):
        continue
    protocol = rule["protocol"].lower()
    lines.append(" ".join([
        rule["direction"], str(rule["priority"]), rule["access"], rule["name"].split("/")[-1],
        "*" if protocol == "all" else protocol,
        "from", addresses(rule, "source"), "ports", ports(rule, "source"),
        "to", addresses(rule, "destination"), "ports", ports(rule, "destination"),
    ]))
if not lines:
    sys.exit("the answer holds no rules")
print("\n".join(sorted(lines)))
'
  nsg_rules() { python3 -c "$nsg_normalise" "$1"; }

  # An Azure call that fails prints nothing, and two empty answers are equal.
  # So an answer has to arrive and hold rules before anything is compared. No
  # answer is a FAIL that says so.
  az_err=$(mktemp)
  # Each row: check ID, VM, its security group, and their resource group. A
  # target VM's group is its subnet's.
  for row in Z.4:orchestrator:nsg-aisec-platform-orchestrator:$RG Z.5:worker:nsg-aisec-platform-worker:$RG \
    Z.16:router:nsg-aisec-edge-router:$RG Z.20:edge:nsg-aisec-edge-edge:$RG \
    Z.27:netbox:nsg-aisec-targets-netbox:$RG_TARGETS Z.28:lab:nsg-aisec-targets-consumer:$RG_TARGETS; do
    IFS=: read -r id vm nsg group <<<"$row"
    claim="Effective rules on the $vm interface equal the configured rules"
    : >"$az_err"
    effective=$(az network nic list-effective-nsg -g "$group" -n "nic-aisec-$vm" -o json 2>>"$az_err" |
      nsg_rules effective 2>>"$az_err")
    effective_rc=$?
    configured=$(az network nsg show -g "$group" -n "$nsg" -o json 2>>"$az_err" |
      nsg_rules configured 2>>"$az_err")
    configured_rc=$?
    if [ "$effective_rc" != 0 ] || [ -z "$effective" ]; then
      check "$id" "$claim" "effective rules from Azure" "no usable answer: $(head -n 1 "$az_err" | cut -c1-200)"
    elif [ "$configured_rc" != 0 ] || [ -z "$configured" ]; then
      check "$id" "$claim" "configured rules from Azure" "no usable answer: $(head -n 1 "$az_err" | cut -c1-200)"
    elif [ "$effective" = "$configured" ]; then
      check "$id" "$claim" equal equal
    else
      check "$id" "$claim" equal different
      # "<" is configured only, ">" is effective only.
      diff <(printf '%s\n' "$configured") <(printf '%s\n' "$effective") | grep '^[<>]' | sed 's/^/            /'
    fi
    # No subnet has a rule that reaches the router (ADR 0025). Its tunnel is
    # opened outbound. Counted on the rules Azure enforces, once they arrived.
    if [ "$vm" = router ] && [ -n "$effective" ]; then
      check Z.17 "Nothing is allowed into the router" 0 "$(printf '%s\n' "$effective" | grep -c '^Inbound [0-9]* Allow ')"
    elif [ "$vm" = router ]; then
      check Z.17 "Nothing is allowed into the router" 0 "no usable answer"
    fi
    # Into the edge: Squid from the orchestrator and the worker subnets, its
    # target port from the orchestrator, and SSH from the router subnet.
    # Nothing else.
    if [ "$vm" = edge ] && [ -n "$effective" ]; then
      check Z.21 "Only the proxy ports and SSH from the router are allowed into the edge" \
        "allow-proxy-from-orchestrator 3128-3128 allow-proxy-from-worker 3128-3128 allow-ssh-from-router 22-22 allow-target-packages-from-orchestrator 3129-3129" \
        "$(printf '%s\n' "$effective" | awk '$1 == "Inbound" && $3 == "Allow" { print $4, $NF }' | sort | tr '\n' ' ' | sed 's/ $//')"
    elif [ "$vm" = edge ]; then
      check Z.21 "Only the proxy ports and SSH from the router are allowed into the edge" allowed "no usable answer"
    fi
  done
  rm -f "$az_err"

  flow() { # remote address:port [vm local-address], printed as "Access rule"
    az network watcher test-ip-flow -g $RG --vm "vm-aisec-${2:-worker}" --direction Outbound --protocol TCP \
      --local "${3:-$WORK_IP}:50000" --remote "$1" --query "join(' ', [access, ruleName])" -o tsv 2>/dev/null |
      sed 's#securityRules/##'
  }
  check Z.6 "Worker to the target network is denied by its own rule" "Deny deny-to-targets" "$(flow 10.50.0.4:22)"
  check Z.7 "Worker to the internet is denied by its own rule" "Deny deny-to-internet" "$(flow 1.1.1.1:443)"
  check Z.8 "Worker to the proxy on the edge is allowed by its own rule" "Allow allow-package-proxy-to-edge" "$(flow $EDGE_IP:3128)"
  check Z.9 "Worker to the Kubernetes API is denied" "Deny deny-all-outbound" "$(flow $ORCH_IP:6443)"
  check Z.13 "Worker to the tool port is allowed by its own rule" "Allow allow-tool-service-to-orchestrator" "$(flow $ORCH_IP:$TOOL_PORT)"
  check Z.22 "Orchestrator to the internet is denied by its own rule" "Deny deny-to-internet" "$(flow 1.1.1.1:443 orchestrator $ORCH_IP)"
  check Z.23 "Orchestrator to the proxy on the edge is allowed by its own rule" "Allow allow-proxy-to-edge" "$(flow $EDGE_IP:3128 orchestrator $ORCH_IP)"
  check Z.26 "Orchestrator to the target port on the edge is allowed by its own rule" "Allow allow-target-packages-to-edge" "$(flow $EDGE_IP:3129 orchestrator $ORCH_IP)"

  # A network interface with a public address, validated and never deployed.
  sub=$(az account show --query id -o tsv 2>/dev/null)
  template=$(mktemp)
  n=10
  for side in platform targets; do
    subnet=$(az network vnet subnet list -g "rg-aisec-$side" --vnet-name "vnet-aisec-$side" --query "[0].id" -o tsv 2>/dev/null)
    # The interface goes where its network is, so the public address is the
    # template's only fault. The target group is in Denmark East and its
    # network in Poland Central. With the group's region, Azure still reports
    # the policy first (seen 2026-10-17), but the check would rest on that order.
    region=$(az network vnet show -g "rg-aisec-$side" -n "vnet-aisec-$side" --query location -o tsv 2>/dev/null)
    cat >"$template" <<EOF
{"\$schema":"https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#","contentVersion":"1.0.0.0","resources":[{"type":"Microsoft.Network/networkInterfaces","apiVersion":"2024-05-01","name":"nic-policy-check","location":"$region","properties":{"ipConfigurations":[{"name":"c","properties":{"subnet":{"id":"$subnet"},"privateIPAllocationMethod":"Dynamic","publicIPAddress":{"id":"/subscriptions/$sub/resourceGroups/rg-aisec-$side/providers/Microsoft.Network/publicIPAddresses/pip-policy-check"}}}]}}]}
EOF
    check "Z.$n" "A public address on an interface is refused by policy in the $side group" 1 \
      "$(az deployment group validate -g "rg-aisec-$side" --template-file "$template" -o json 2>&1 | grep -c -m 1 RequestDisallowedByPolicy)"
    n=$((n + 1))
  done
  rm -f "$template"
  check Z.12 "The policy check left nothing behind" 0 \
    "$(az resource list --query "length([?contains(name,'policy-check')])" -o tsv 2>/dev/null)"

  # ADR 0020 moves the target network to Poland Central. Its resource group and
  # state stay in Denmark East, so the group's location proves nothing here.
  check Z.14 "The target network is in Poland Central" polandcentral \
    "$(az network vnet show -g $RG_TARGETS -n vnet-aisec-targets --query location -o tsv 2>/dev/null)"
  # Each side holds its own half of the peering. When one network is rebuilt,
  # the other half shows Disconnected, even though the name and ID are the
  # same, until that half is re-created.
  check Z.15 "Both halves of the peering are connected" "Connected Connected" \
    "$(az network vnet peering show -g $RG --vnet-name vnet-aisec-platform -n peer-platform-to-targets \
      --query peeringState -o tsv 2>/dev/null) $(az network vnet peering show -g $RG_TARGETS \
      --vnet-name vnet-aisec-targets -n peer-targets-to-platform --query peeringState -o tsv 2>/dev/null)"
  check Z.18 "Both halves of the platform and edge peering are connected" "Connected Connected" \
    "$(az network vnet peering show -g $RG --vnet-name vnet-aisec-platform -n peer-platform-to-edge \
      --query peeringState -o tsv 2>/dev/null) $(az network vnet peering show -g $RG \
      --vnet-name vnet-aisec-edge -n peer-edge-to-platform --query peeringState -o tsv 2>/dev/null)"
  # The router's sessions to the targets cross this peering. The target half
  # belongs to the targets repository.
  check Z.24 "Both halves of the edge and target peering are connected" "Connected Connected" \
    "$(az network vnet peering show -g $RG --vnet-name vnet-aisec-edge -n peer-edge-to-targets \
      --query peeringState -o tsv 2>/dev/null) $(az network vnet peering show -g $RG_TARGETS \
      --vnet-name vnet-aisec-targets -n peer-targets-to-edge --query peeringState -o tsv 2>/dev/null)"
  # The configured inbound allows of each target group. The NetBox and lab
  # groups' effective rules are Z.27 and Z.28. No VM is in the other two
  # subnets, so there is no interface to read their effective rules from.
  # NetBox's port is allowed into its subnet from the orchestrator's address
  # and the consumer subnet (ADR 0035).
  want="" got=""
  for g in netbox consumer unintended rehearsal; do
    want="$want$g: "
    [ "$g" = netbox ] && want="${want}allow-netbox-from-consumer 10.50.0.32/27 $NETBOX_PORT, allow-netbox-from-orchestrator $ORCH_IP/32 $NETBOX_PORT, "
    want="${want}allow-ssh-from-orchestrator 10.40.0.0/27 22, allow-ssh-from-router 10.45.0.32/27 22; "
    got="$got$g: $(az network nsg rule list -g $RG_TARGETS --nsg-name "nsg-aisec-targets-$g" \
      --query "[?direction=='Inbound' && access=='Allow'].[name, sourceAddressPrefix, destinationPortRange]" \
      -o tsv 2>/dev/null | sort | tr '\t' ' ' | paste -sd ',' - | sed 's/,/, /g'); "
  done
  check Z.25 "Only SSH from the orchestrator and the router, and NetBox's port from the orchestrator and the consumer, is allowed into the target subnets" \
    "$want" "$got"
  check Z.19 "The edge network is in Denmark East" denmarkeast \
    "$(az network vnet show -g $RG -n vnet-aisec-edge --query location -o tsv 2>/dev/null)"

  # Monitoring (ADR 0021, ADR 0027).
  #
  # The hosts entries each VM holds, against the names and addresses the
  # private endpoint records, in the form the hosts script writes them. No
  # answer from Azure hashes to the hash of nothing, which no VM holds once its
  # block is written. A VM that was not reached has no value, and fails.
  endpoint_hosts=$(az network private-endpoint show -g $RG -n pe-aisec-monitoring -o json 2>/dev/null |
    python3 -I -c "
import json, sys
try:
    configs = json.load(sys.stdin).get(\"customDnsConfigs\") or []
except ValueError:
    configs = []
lines = sorted({f\"{a} {c['fqdn']}\" for c in configs for a in c.get(\"ipAddresses\") or []})
print(\"\\n\".join(lines))
" 2>/dev/null)
  if [ -n "$endpoint_hosts" ]; then
    endpoint_hosts=$(printf '%s\n' "$endpoint_hosts" | sha256sum | cut -d " " -f 1)
  else
    endpoint_hosts="no record from the private endpoint"
  fi
  check O.5 "The orchestrator's hosts entries are the private endpoint's" "$endpoint_hosts" "${hosts_orchestrator:-not reached}"
  check O.6 "The edge's hosts entries are the private endpoint's" "$endpoint_hosts" "${hosts_edge:-not reached}"
  check O.7 "The router's hosts entries are the private endpoint's" "$endpoint_hosts" "${hosts_router:-not reached}"
  check O.8 "The workspace takes no public ingestion and no shared key" "Disabled Enabled true" \
    "$(az monitor log-analytics workspace show -g $RG -n log-aisec \
      --query "join(' ', [publicNetworkAccessForIngestion, publicNetworkAccessForQuery, to_string(features.disableLocalAuth)])" \
      -o tsv 2>/dev/null)"
  check O.9 "The Private Link Scope takes ingestion only from its private endpoint" "PrivateOnly Open" \
    "$(az resource show -g $RG -n ampls-aisec --resource-type microsoft.insights/privateLinkScopes \
      --query "join(' ', [properties.accessModeSettings.ingestionAccessMode, properties.accessModeSettings.queryAccessMode])" \
      -o tsv 2>/dev/null)"
  # Queries go to the workspace's API with the operator's sign-in. A failed
  # call prints nothing, which matches no expected value.
  workspace_id=$(az monitor log-analytics workspace show -g $RG -n log-aisec --query customerId -o tsv 2>/dev/null)
  kql() {
    az rest --method post --resource https://api.loganalytics.io \
      --url "https://api.loganalytics.io/v1/workspaces/${workspace_id:-none}/query" \
      --body "$(python3 -I -c "import json, sys; print(json.dumps({\"query\": sys.argv[1]}))" "$1")" \
      --query "tables[0].rows[]" -o tsv 2>/dev/null | tr '\n' ' ' | sed 's/ $//'
  }
  check O.10 "A heartbeat from each log agent in the last 10 minutes" "aisec-edge aisec-orchestrator aisec-router" \
    "$(kql "Heartbeat | where TimeGenerated > ago(10m) | distinct Computer | order by Computer asc")"
  # The pull runs every five minutes (J.3), and each pass writes at least the
  # lines the worker logged since the last one.
  check O.11 "The worker's journal copy reached the workspace in the last 25 minutes" yes \
    "$(kql "AisecWorkerJournal_CL | where TimeGenerated > ago(25m) | count | project iff(Count > 0, 'yes', 'no')")"
  # A VM's identity can send, and nothing else: no role anywhere, so it cannot
  # read or delete what it sent. The worker has no identity at all.
  roles=""
  for vm in orchestrator edge router; do
    principal=$(az vm show -g $RG -n "vm-aisec-$vm" --query identity.principalId -o tsv 2>/dev/null)
    roles="$roles$vm $( [ -n "$principal" ] && az role assignment list --all --assignee "$principal" --query "length(@)" -o tsv 2>/dev/null || echo "no identity"); "
  done
  check O.12 "The log agents' identities hold no role" "orchestrator 0; edge 0; router 0; " "$roles"
  check O.13 "The worker has no managed identity" none \
    "$(az vm show -g $RG -n vm-aisec-worker --query "identity.type || 'none'" -o tsv 2>/dev/null)"

  # The alert rules (ADR 0021, ADR 0028). The names come from this checkout,
  # each with "on stateful none": enabled, resolving itself, and no action
  # group. A rule missing in Azure, or one that sends something, differs.
  sub_id=$(az account show --query id -o tsv 2>/dev/null)
  rule_names=$(grep -E '^    [a-z-]+ = \{$' "$here/../infra/platform/alerts.tf" | awk '{print $1}' | sort)
  want_rules=$(for r in $rule_names; do printf 'alert-aisec-%s on stateful none; ' "$r"; done)
  got_rules=$(az rest --method get \
    --url "https://management.azure.com/subscriptions/${sub_id:-none}/resourceGroups/$RG/providers/Microsoft.Insights/scheduledQueryRules?api-version=2023-12-01" \
    -o json 2>/dev/null | python3 -I -c "
import json, sys
try:
    rules = json.load(sys.stdin)['value']
except (ValueError, KeyError):
    rules = []
for r in sorted(rules, key=lambda r: r['name']):
    p = r['properties']
    groups = (p.get('actions') or {}).get('actionGroups') or []
    print(r['name'], 'on' if p.get('enabled') else 'off', 'stateful' if p.get('autoMitigate') else 'stateless',
          'none' if not groups else 'sends', end='; ')
" 2>/dev/null)
  check O.14 "Every alert rule in this checkout is on, resolves itself, and sends nothing" "${want_rules:-no rules in the checkout}" "$got_rules"
  # The subscription's control changes, in the platform state group, where no
  # deployment identity has a role.
  check O.15 "Four Activity Log rules watch the controls and send nothing" \
    "alert-aisec-policy-assignments on none; alert-aisec-role-assignments on none; alert-aisec-security-groups on none; alert-aisec-security-rules on none; " \
    "$(az rest --method get \
      --url "https://management.azure.com/subscriptions/${sub_id:-none}/resourceGroups/rg-aisec-platform-state/providers/Microsoft.Insights/activityLogAlerts?api-version=2020-10-01" \
      -o json 2>/dev/null | python3 -I -c "
import json, sys
try:
    rules = json.load(sys.stdin)['value']
except (ValueError, KeyError):
    rules = []
for r in sorted(rules, key=lambda r: r['name']):
    p = r['properties']
    groups = (p.get('actions') or {}).get('actionGroups') or []
    print(r['name'], 'on' if p.get('enabled') else 'off', 'none' if not groups else 'sends', end='; ')
" 2>/dev/null)"
  flows=""
  for region in swedencentral denmarkeast; do
    flows="$flows$(az network watcher flow-log list -l $region \
      --query "[?name=='fl-aisec-$([ $region = swedencentral ] && echo platform || echo edge)'].join(' ', [name, to_string(enabled), to_string(flowAnalyticsConfiguration.networkWatcherFlowAnalyticsConfiguration.enabled), to_string(flowAnalyticsConfiguration.networkWatcherFlowAnalyticsConfiguration.trafficAnalyticsInterval)])" \
      -o tsv 2>/dev/null); "
  done
  check O.16 "Flow logs are on for both networks, with traffic analytics every 10 minutes" \
    "fl-aisec-platform true true 10; fl-aisec-edge true true 10; " "$flows"
  # Traffic analytics writes every 10 minutes, and the checks themselves make
  # flows. An hour is six intervals. denied-flow-to-internet reads the
  # platform's rows.
  check O.17 "Traffic analytics wrote flows from both flow logs in the last hour" "fl-aisec-edge fl-aisec-platform" \
    "$(kql "NTANetAnalytics | where TimeGenerated > ago(1h) and SubType == 'FlowLog' | extend log = tostring(split(FlowLogResourceId, '/')[-1]) | distinct log | order by log asc")"
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
