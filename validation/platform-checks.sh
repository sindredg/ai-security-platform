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
#
#   validation/platform-checks.sh [--no-azure] [--no-workstation]

# The probes are single-quoted on purpose. They are sent to the VMs as text
# and expand there, not here.
# shellcheck disable=SC2016
set -uo pipefail

SSH=${AISEC_SSH:-ssh}
ORCH=${AISEC_ORCH:-10.40.0.4}
WORK=${AISEC_WORK:-10.40.0.36}
ORCH_IP=10.40.0.4
WORK_IP=10.40.0.36
PROXY="http://$ORCH_IP:3128"
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
echo "authorized_keys=$(wc -l < /home/aisec/.ssh/authorized_keys)"
'

probe_orchestrator="$probe_common"'
for unit in k3s tailscaled aisec-mss-clamp squid; do
  echo "unit_$(echo $unit | tr - _)=$(systemctl is-active $unit)"
done
echo "node_ready=$(k3s kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready ")"
echo "pods_not_running=$(k3s kubectl get pods -A --no-headers 2>/dev/null | grep -v -c " Running ")"
echo "secrets_encryption=$(k3s secrets-encrypt status 2>/dev/null | sed -n "s/^Encryption Status: //p")"
echo "cert_modes_not_600=$(stat -c %a /var/lib/rancher/k3s/server/tls/*.crt | grep -v -c "^600$")"
echo "default_sa_automount=$(k3s kubectl get sa -A --field-selector metadata.name=default -o jsonpath="{range .items[*]}{.automountServiceAccountToken}{\"\n\"}{end}" 2>/dev/null | grep -v -c "^false$")"
echo "apiserver_anonymous=$(journalctl -u k3s --no-pager 2>/dev/null | grep "Running kube-apiserver" | tail -n 1 | grep -o -- "--anonymous-auth=[a-z]*")"
echo "mss_rules=$(nft list table inet aisec_mss 2>/dev/null | grep -c maxseg)"
echo "pod_egress=$(nft list chain inet aisec_pod_egress forward 2>/dev/null | sed -n "s/^\t\t//p" | sed "s/counter packets [0-9]* bytes [0-9]* /counter /" | tr "\n" "|")"
echo "pod_egress_unit=$(systemctl is-enabled aisec-pod-egress 2>/dev/null)"
echo "ip_forward=$(sysctl -n net.ipv4.ip_forward)"
echo "squid_listen=$(ss -ltn | awk "{print \$4}" | grep ":3128$" | tr "\n" " " | sed "s/ $//")"
echo "squid_no_new_privileges=$(systemctl show squid -p NoNewPrivileges --value)"
echo "squid_from_orchestrator=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 -x '"$PROXY"' http://archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "lock=$(tailscale lock status 2>/dev/null | head -n 1)"
echo "lock_signed=$(tailscale lock status 2>/dev/null | grep -c "This node is accessible under Tailnet Lock")"
echo "tailscale_held=$(apt-mark showhold | grep -c "^tailscale$")"
echo "tailscale_auto_apply=$(tailscale debug prefs 2>/dev/null | tr -d " \n" | grep -o "\"AutoUpdate\":{[^}]*}" | grep -o "\"Apply\":[a-z]*" | cut -d: -f2)"
echo "auth_key_file=$(ls /run/aisec 2>/dev/null | wc -l)"
echo "egress_https=$(tcp 1.1.1.1 443)"
echo "to_worker_ssh=$(tcp '"$WORK_IP"' 22)"
echo "to_worker_http=$(tcp '"$WORK_IP"' 80)"
echo "to_worker_model=$(tcp '"$WORK_IP"' '"$MODEL_PORT"')"
echo "feed=$(sudo -u aisec ssh -n -i /home/aisec/.ssh/aisec-feed -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 aisec@aisec-worker hostname 2>/dev/null)"
echo "security_updates_pending=$(apt list --upgradable 2>/dev/null | grep -c -- -security)"
echo "mesh_udp=$(tailscale netcheck 2>/dev/null | sed -n "s/^[^A-Za-z]*UDP: //p" | head -n 1)"
k() { k3s kubectl "$@" 2>/dev/null; }
echo "tool_ready=$(k get deployment tool-service -n tool-services -o jsonpath="{.status.readyReplicas}")"
echo "tool_image=$(k get pods -n tool-services -l app.kubernetes.io/name=tool-service -o jsonpath="{.items[0].status.containerStatuses[0].imageID}" | sed "s/.*@//")"
echo "tool_pod_security=$(k get pods -n tool-services -l app.kubernetes.io/name=tool-service -o jsonpath="{.items[0].spec.automountServiceAccountToken} {.items[0].spec.securityContext.runAsNonRoot} {.items[0].spec.containers[0].securityContext.readOnlyRootFilesystem} {.items[0].spec.containers[0].securityContext.allowPrivilegeEscalation} {.items[0].spec.containers[0].securityContext.capabilities.drop[0]}")"
echo "pod_security_admission=$(k get namespace tool-services orchestration -o jsonpath="{range .items[*]}{.metadata.labels.pod-security\.kubernetes\.io/enforce} {end}" | sed "s/ $//")"
echo "default_deny=$({ k get networkpolicy default-deny -n tool-services -o name; k get networkpolicy default-deny -n orchestration -o name; } | tr "\n" " " | sed "s/ $//")"
echo "tool_port_on_mesh=$(tcp "$(tailscale ip -4 2>/dev/null | head -n 1)" '"$TOOL_PORT"')"
echo "tool_cert_14_days=$(openssl x509 -in /etc/aisec/tool-service/tls.crt -noout -checkend 1209600 >/dev/null 2>&1 && echo yes || echo no)"
audit=/var/log/aisec/tool-audit.jsonl
echo "audit_copy_active=$(systemctl is-active aisec-audit-copy 2>/dev/null)"
echo "audit_copy_enabled=$(systemctl is-enabled aisec-audit-copy 2>/dev/null)"
echo "audit_file=$(stat -c "%U %G %a" $audit 2>/dev/null) $(lsattr $audit 2>/dev/null | cut -d " " -f 1 | tr -cd a)"
ok_time=$(stat -c %Y /var/lib/aisec-audit-copy/ok 2>/dev/null || echo 0)
echo "audit_copy_recent=$([ $(( $(date +%s) - ok_time )) -le 10 ] && echo yes || echo no)"
echo "audit_mounts=$(k get pods -A -o jsonpath="{range .items[*].spec.volumes[*]}{.hostPath.path}{\"\n\"}{end}" | grep -c -x -E "/|/var/?|/var/log/?|/var/log/aisec(/.*)?")"
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
'

probe_worker="$probe_common"'
code() { curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$@"; }
echo "internet=$(tcp 1.1.1.1 443)"
echo "targets_netbox=$(tcp 10.50.0.4 22)"
echo "targets_rehearsal=$(tcp 10.50.1.4 22)"
echo "azure_dns=$(tcp 168.63.129.16 53)"
timeout 6 getent hosts example.com >/dev/null 2>&1; echo "resolve_public_name_rc=$?"
echo "orchestrator_ssh=$(tcp '"$ORCH_IP"' 22)"
echo "orchestrator_api=$(tcp '"$ORCH_IP"' 6443)"
echo "orchestrator_kubelet=$(tcp '"$ORCH_IP"' 10250)"
echo "orchestrator_proxy=$(tcp '"$ORCH_IP"' 3128)"
echo "proxy_archive=$(code -x '"$PROXY"' http://archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "proxy_security=$(code -x '"$PROXY"' http://security.ubuntu.com/ubuntu/dists/resolute-security/InRelease)"
echo "proxy_other_host=$(code -x '"$PROXY"' http://example.com/)"
echo "proxy_post=$(code -x '"$PROXY"' -X POST -d x http://archive.ubuntu.com/ubuntu/)"
echo "proxy_other_port=$(code -x '"$PROXY"' http://archive.ubuntu.com:8080/)"
echo "proxy_connect=$(curl -s -o /dev/null -w "%{http_connect}" --max-time 8 -x '"$PROXY"' https://example.com/ 2>/dev/null)"
echo "apt_proxy=$(apt-config dump 2>/dev/null | grep -c "Acquire::http::Proxy \"'"$PROXY"'\"")"
echo "unattended_upgrades=$(systemctl is-enabled unattended-upgrades 2>/dev/null)"
echo "security_updates_pending=$(apt list --upgradable 2>/dev/null | grep -c -- -security)"
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
}

echo "== Orchestrator ($ORCH)"
if probe=$($SSH "$ORCH" 'sudo bash -s' <<<"$probe_orchestrator" 2>/dev/null) && [ -n "$probe" ]; then
  check A.1 "Reachable over the mesh VPN with the operator key" yes yes
  check A.2 "Mesh VPN node signing is enabled" "Tailnet Lock is ENABLED." "$(value lock)"
  check A.3 "The orchestrator's node key is signed" 1 "$(value lock_signed)"
  check A.4 "The spent auth key file is gone" 0 "$(value auth_key_file)"
  check A.5 "Only the operator key is authorized" 1 "$(value authorized_keys)"
  check K.1 "k3s is active" active "$(value unit_k3s)"
  check K.2 "The node is Ready" 1 "$(value node_ready)"
  check K.3 "Every pod is Running" 0 "$(value pods_not_running)"
  check K.4 "Secrets encryption is enabled" Enabled "$(value secrets_encryption)"
  check K.5 "Every certificate file is 600" 0 "$(value cert_modes_not_600)"
  check K.6 "No default service account mounts a token" 0 "$(value default_sa_automount)"
  check K.7 "The API server refuses anonymous requests" "--anonymous-auth=false" "$(value apiserver_anonymous)"
  check R.1 "The mesh VPN agent is active" active "$(value unit_tailscaled)"
  check R.2 "The segment size clamp is loaded" 2 "$(value mss_rules)"
  check R.3 "The orchestrator forwards packets" 1 "$(value ip_forward)"
  check E.1 "The orchestrator reaches the internet on 443" open "$(value egress_https)"
  check E.2 "The orchestrator reaches the worker on 22" open "$(value to_worker_ssh)"
  # Nothing listens on the worker's port 80. If its rules let the packet in,
  # the worker answers with a reset. Only a timeout shows the rules dropped it.
  check E.3 "The worker's rules drop the orchestrator on 80" timeout "$(value to_worker_http)"
  check E.4 "The feed key logs in to the worker" aisec-worker "$(value feed)"
  check P.1 "Squid is active" active "$(value unit_squid)"
  check P.2 "Squid listens on the private address only" "$ORCH_IP:3128" "$(value squid_listen)"
  check P.3 "Squid cannot gain privileges" yes "$(value squid_no_new_privileges)"
  check P.4 "Squid refuses a client outside the worker subnet" 403 "$(value squid_from_orchestrator)"
  # The model server listens on the worker's loopback address only (S.4), so
  # this is E.3 again on the port that matters: nothing answers on this
  # address, a packet the rules let in gets a reset, and only a timeout shows
  # the rules dropped it.
  check S.1 "The worker's rules drop the orchestrator on the model server port" timeout "$(value to_worker_model)"
  check U.1 "No security update is pending on the orchestrator" 0 "$(value security_updates_pending)"
  check U.2 "The mesh VPN agent is held at its pinned version" 1 "$(value tailscale_held)"
  # The hold stops apt. The agent has its own updater, which the hold does not stop.
  check U.6 "The mesh VPN agent does not install updates itself" false "$(value tailscale_auto_apply)"
  # The mesh agent's UDP rules are gone, so it cannot reach a STUN server.
  check E.5 "The orchestrator sends no UDP to the internet" false "$(value mesh_udp)"
  # The chain as nft lists it, with the counter's values taken out. It holds
  # a pod from its first packet, before kube-router writes the pod's policy.
  check E.6 "Forwarded traffic from pods goes only to pods" \
    "type filter hook forward priority filter + 10; policy accept;|ip saddr 10.42.0.0/16 ct state established,related accept|ip saddr 10.42.0.0/16 ip daddr 10.42.0.0/16 accept|ip saddr 10.42.0.0/16 counter drop|" \
    "$(value pod_egress)"
  check E.7 "The pod egress rule loads at boot" enabled "$(value pod_egress_unit)"
  check T.1 "The tool service pod is ready" 1 "$(value tool_ready)"
  # The digest that runs, against the digest the reviewed manifest names. An
  # empty manifest digest is a failure, not a match.
  check T.2 "The tool service runs the image its manifest names" "${TOOL_IMAGE_DIGEST:-no digest in the manifest}" "$(value tool_image)"
  check T.3 "The tool service pod has no token, no root, and nothing writable" "false true true false ALL" "$(value tool_pod_security)"
  check T.4 "Both namespaces enforce the restricted pod security level" "restricted restricted" "$(value pod_security_admission)"
  check T.5 "Both namespaces deny by default" "networkpolicy.networking.k8s.io/default-deny networkpolicy.networking.k8s.io/default-deny" "$(value default_deny)"
  # Node ports answer on the private address only. The mesh address is a
  # local address of this machine, so the mesh policy does not apply here.
  # Nothing listens: a reset, "refused", is the expected answer.
  check T.6 "The tool port does not answer on the mesh address" refused "$(value tool_port_on_mesh)"
  check T.7 "The tool service certificate has more than 14 days left" yes "$(value tool_cert_14_days)"
  # From inside the pod. K3s enforces network policies with kube-router, which
  # rejects with an ICMP port unreachable, so a blocked connection is
  # "refused", observed on 2026-10-15. The orchestrator itself reaches 443
  # (E.1), so without the policy this is "open". Any other end is a failure.
  check T.8 "The tool service pod cannot reach the internet" refused "$(value tool_egress)"
  check L.1 "The audit copier is active" active "$(value audit_copy_active)"
  check L.2 "The audit copier starts at boot" enabled "$(value audit_copy_enabled)"
  # Owner, group, mode, and the append-only attribute. The copier's group can
  # append, and nobody but root can remove the attribute.
  check L.3 "The audit file is root's and append-only" "root aisec-audit-copy 620 a" "$(value audit_file)"
  # Five times the copier's interval. A pass with nothing new still counts, and
  # a pass that finds no log file of the tool service does not (ADR 0019).
  check L.4 "The audit copier succeeded in the last 10 seconds" yes "$(value audit_copy_recent)"
  # A hostPath of the folder or anything above it would expose the file.
  check L.5 "No pod mounts the audit folder" 0 "$(value audit_mounts)"
  # Missing numbers within each start, plus lines that are not JSON. Lines
  # without a start, from the image before ADR 0019, are not counted.
  check L.6 "No audit line is missing" 0 "$(value audit_holes)"
  # A marker stands for a line the copier refused or a full file.
  check L.7 "The audit copier refused no line" 0 "$(value audit_markers)"
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
  common_checks HO
else
  check A.1 "Reachable over the mesh VPN with the operator key" yes no
fi

echo
echo "== Worker ($WORK)"
if probe=$($SSH "$WORK" 'sudo bash -s' <<<"$probe_worker" 2>/dev/null) && [ -n "$probe" ]; then
  check A.6 "Reachable through the subnet router with the operator key" yes yes
  check A.7 "Only the operator key and the feed key are authorized" 2 "$(value authorized_keys)"
  # C.1 and C.4 aim at ports that are known to listen, so a timeout is a drop.
  check C.1 "No connection to the internet" timeout "$(value internet)"
  # No target machine exists, so these two time out with or without the deny
  # rule. They prove no path today and nothing about the rule. Z.6 names it.
  check C.2 "No connection to the NetBox subnet" timeout "$(value targets_netbox)"
  check C.3 "No connection to the rehearsal subnet" timeout "$(value targets_rehearsal)"
  check C.4 "No connection to the platform resolver" timeout "$(value azure_dns)"
  check C.5 "A public name does not resolve" no "$([ "$(value resolve_public_name_rc)" = 0 ] && echo yes || echo no)"
  # All three ports listen on the orchestrator: E.2 and M.1 reach 22, M.2
  # reaches 6443, and the kubelet runs with k3s. A timeout is a drop.
  check C.6 "No connection to the orchestrator on 22" timeout "$(value orchestrator_ssh)"
  check C.7 "No connection to the Kubernetes API" timeout "$(value orchestrator_api)"
  check C.8 "No connection to the kubelet" timeout "$(value orchestrator_kubelet)"
  check C.9 "The worker does not forward packets" 0 "$(value ip_forward)"
  check P.5 "The worker reaches the proxy port" open "$(value orchestrator_proxy)"
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
  check U.3 "apt on the worker uses the proxy" 1 "$(value apt_proxy)"
  check U.4 "Unattended upgrades are enabled on the worker" enabled "$(value unattended_upgrades)"
  check U.5 "No security update is pending on the worker" 0 "$(value security_updates_pending)"
  common_checks HW
else
  check A.6 "Reachable through the subnet router with the operator key" yes no
fi

if [ "$workstation" = 1 ]; then
  echo
  echo "== Workstation, through the mesh VPN"
  eval "$tcp_fn"
  check M.1 "The mesh policy allows SSH to the orchestrator" open "$(tcp $ORCH_IP 22 6)"
  check M.2 "The mesh policy allows the Kubernetes API" open "$(tcp $ORCH_IP 6443 6)"
  # Squid and the kubelet both listen on this address (P.2, and C.8 above). The
  # mesh drops what its policy does not grant, so a timeout is the policy.
  # "refused" would mean the packet reached the orchestrator.
  check M.3 "The mesh policy drops the proxy port" timeout "$(tcp $ORCH_IP 3128 6)"
  check M.4 "The mesh policy drops the kubelet port" timeout "$(tcp $ORCH_IP 10250 6)"
  check M.5 "The mesh policy drops the tool port" timeout "$(tcp $ORCH_IP $TOOL_PORT 6)"
fi

if [ "$azure" = 1 ]; then
  echo
  echo "== Azure, as the operator"
  check Z.1 "No VM has a public address" 0 \
    "$(az vm list -g $RG -d --query "length([?publicIps!=''])" -o tsv 2>/dev/null)"
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
  # security group on the interface would still show up.
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
  n=4
  for vm in orchestrator worker; do
    claim="Effective rules on the $vm interface equal the configured rules"
    : >"$az_err"
    effective=$(az network nic list-effective-nsg -g $RG -n "nic-aisec-$vm" -o json 2>>"$az_err" |
      nsg_rules effective 2>>"$az_err")
    effective_rc=$?
    configured=$(az network nsg show -g $RG -n "nsg-aisec-platform-$vm" -o json 2>>"$az_err" |
      nsg_rules configured 2>>"$az_err")
    configured_rc=$?
    if [ "$effective_rc" != 0 ] || [ -z "$effective" ]; then
      check "Z.$n" "$claim" "effective rules from Azure" "no usable answer: $(head -n 1 "$az_err" | cut -c1-200)"
    elif [ "$configured_rc" != 0 ] || [ -z "$configured" ]; then
      check "Z.$n" "$claim" "configured rules from Azure" "no usable answer: $(head -n 1 "$az_err" | cut -c1-200)"
    elif [ "$effective" = "$configured" ]; then
      check "Z.$n" "$claim" equal equal
    else
      check "Z.$n" "$claim" equal different
      # "<" is configured only, ">" is effective only.
      diff <(printf '%s\n' "$configured") <(printf '%s\n' "$effective") | grep '^[<>]' | sed 's/^/            /'
    fi
    n=$((n + 1))
  done
  rm -f "$az_err"

  flow() { # remote address:port, printed as "Access rule"
    az network watcher test-ip-flow -g $RG --vm vm-aisec-worker --direction Outbound --protocol TCP \
      --local "$WORK_IP:50000" --remote "$1" --query "join(' ', [access, ruleName])" -o tsv 2>/dev/null |
      sed 's#securityRules/##'
  }
  check Z.6 "Worker to the target network is denied by its own rule" "Deny deny-to-targets" "$(flow 10.50.0.4:22)"
  check Z.7 "Worker to the internet is denied by its own rule" "Deny deny-to-internet" "$(flow 1.1.1.1:443)"
  check Z.8 "Worker to the proxy is allowed by its own rule" "Allow allow-package-proxy-to-orchestrator" "$(flow $ORCH_IP:3128)"
  check Z.9 "Worker to the Kubernetes API is denied" "Deny deny-all-outbound" "$(flow $ORCH_IP:6443)"
  check Z.13 "Worker to the tool port is allowed by its own rule" "Allow allow-tool-service-to-orchestrator" "$(flow $ORCH_IP:$TOOL_PORT)"

  # A network interface with a public address, validated and never deployed.
  sub=$(az account show --query id -o tsv 2>/dev/null)
  template=$(mktemp)
  n=10
  for side in platform targets; do
    subnet=$(az network vnet subnet list -g "rg-aisec-$side" --vnet-name "vnet-aisec-$side" --query "[0].id" -o tsv 2>/dev/null)
    cat >"$template" <<EOF
{"\$schema":"https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#","contentVersion":"1.0.0.0","resources":[{"type":"Microsoft.Network/networkInterfaces","apiVersion":"2024-05-01","name":"nic-policy-check","location":"[resourceGroup().location]","properties":{"ipConfigurations":[{"name":"c","properties":{"subnet":{"id":"$subnet"},"privateIPAllocationMethod":"Dynamic","publicIPAddress":{"id":"/subscriptions/$sub/resourceGroups/rg-aisec-$side/providers/Microsoft.Network/publicIPAddresses/pip-policy-check"}}}]}}]}
EOF
    check "Z.$n" "A public address on an interface is refused by policy in the $side group" 1 \
      "$(az deployment group validate -g "rg-aisec-$side" --template-file "$template" -o json 2>&1 | grep -c -m 1 RequestDisallowedByPolicy)"
    n=$((n + 1))
  done
  rm -f "$template"
  check Z.12 "The policy check left nothing behind" 0 \
    "$(az resource list --query "length([?contains(name,'policy-check')])" -o tsv 2>/dev/null)"
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
