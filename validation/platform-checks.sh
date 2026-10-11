#!/usr/bin/env bash
# Checks the claims the platform side makes, against the running system.
#
# Read-only. It opens connections that should fail and reads settings. The one
# thing it sends to Azure is a template validation, which deploys nothing.
#
# Run it from a workstation that is on the mesh VPN and signed in to Azure as
# the operator. What each check proves is in docs/validation/.
#
#   AISEC_SSH   The ssh command, with host key and identity options.
#               Default: ssh
#   AISEC_ORCH  Orchestrator address or host alias. Default: 10.40.0.4
#   AISEC_WORK  Worker address or host alias. Default: 10.40.0.36
#
#   validation/platform-checks.sh [--no-azure] [--no-workstation]
set -uo pipefail

SSH=${AISEC_SSH:-ssh}
ORCH=${AISEC_ORCH:-10.40.0.4}
WORK=${AISEC_WORK:-10.40.0.36}
ORCH_IP=10.40.0.4
WORK_IP=10.40.0.36
PROXY="http://$ORCH_IP:3128"
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

# The probes run on the VMs and print key=value lines. Nothing in them changes
# the machine.
probe_common='
tcp() { timeout 5 bash -c "</dev/tcp/$1/$2" 2>/dev/null && echo open || echo closed; }
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
echo "ip_forward=$(sysctl -n net.ipv4.ip_forward)"
echo "squid_listen=$(ss -ltn | awk "{print \$4}" | grep ":3128$" | tr "\n" " " | sed "s/ $//")"
echo "squid_no_new_privileges=$(systemctl show squid -p NoNewPrivileges --value)"
echo "squid_from_orchestrator=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 -x '"$PROXY"' http://archive.ubuntu.com/ubuntu/dists/resolute/InRelease)"
echo "lock=$(tailscale lock status 2>/dev/null | head -n 1)"
echo "lock_signed=$(tailscale lock status 2>/dev/null | grep -c "This node is accessible under Tailnet Lock")"
echo "tailscale_held=$(apt-mark showhold | grep -c "^tailscale$")"
echo "auth_key_file=$(ls /run/aisec 2>/dev/null | wc -l)"
echo "egress_https=$(tcp 1.1.1.1 443)"
echo "to_worker_ssh=$(tcp '"$WORK_IP"' 22)"
echo "to_worker_http=$(tcp '"$WORK_IP"' 80)"
echo "feed=$(sudo -u aisec ssh -n -i /home/aisec/.ssh/aisec-feed -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 aisec@aisec-worker hostname 2>/dev/null)"
echo "security_updates_pending=$(apt list --upgradable 2>/dev/null | grep -c -- -security)"
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
  check E.3 "The orchestrator does not reach the worker on 80" closed "$(value to_worker_http)"
  check E.4 "The feed key logs in to the worker" aisec-worker "$(value feed)"
  check P.1 "Squid is active" active "$(value unit_squid)"
  check P.2 "Squid listens on the private address only" "$ORCH_IP:3128" "$(value squid_listen)"
  check P.3 "Squid cannot gain privileges" yes "$(value squid_no_new_privileges)"
  check P.4 "Squid refuses a client outside the worker subnet" 403 "$(value squid_from_orchestrator)"
  check U.1 "No security update is pending on the orchestrator" 0 "$(value security_updates_pending)"
  check U.2 "The mesh VPN agent is held at its pinned version" 1 "$(value tailscale_held)"
  common_checks HO
else
  check A.1 "Reachable over the mesh VPN with the operator key" yes no
fi

echo
echo "== Worker ($WORK)"
if probe=$($SSH "$WORK" 'sudo bash -s' <<<"$probe_worker" 2>/dev/null) && [ -n "$probe" ]; then
  check A.6 "Reachable through the subnet router with the operator key" yes yes
  check A.7 "Only the operator key and the feed key are authorized" 2 "$(value authorized_keys)"
  check C.1 "No connection to the internet" closed "$(value internet)"
  check C.2 "No connection to the NetBox subnet" closed "$(value targets_netbox)"
  check C.3 "No connection to the rehearsal subnet" closed "$(value targets_rehearsal)"
  check C.4 "No connection to the platform resolver" closed "$(value azure_dns)"
  check C.5 "A public name does not resolve" no "$([ "$(value resolve_public_name_rc)" = 0 ] && echo yes || echo no)"
  check C.6 "No connection to the orchestrator on 22" closed "$(value orchestrator_ssh)"
  check C.7 "No connection to the Kubernetes API" closed "$(value orchestrator_api)"
  check C.8 "No connection to the kubelet" closed "$(value orchestrator_kubelet)"
  check C.9 "The worker does not forward packets" 0 "$(value ip_forward)"
  check P.5 "The worker reaches the proxy port" open "$(value orchestrator_proxy)"
  check P.6 "The proxy serves archive.ubuntu.com" 200 "$(value proxy_archive)"
  check P.7 "The proxy serves security.ubuntu.com" 200 "$(value proxy_security)"
  check P.8 "The proxy refuses another host" 403 "$(value proxy_other_host)"
  check P.9 "The proxy refuses an upload" 403 "$(value proxy_post)"
  check P.10 "The proxy refuses another port" 403 "$(value proxy_other_port)"
  check P.11 "The proxy refuses a tunnel" 403 "$(value proxy_connect)"
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
  tcp() { timeout 6 bash -c "</dev/tcp/$1/$2" 2>/dev/null && echo open || echo closed; }
  check M.1 "The mesh policy allows SSH to the orchestrator" open "$(tcp $ORCH_IP 22)"
  check M.2 "The mesh policy allows the Kubernetes API" open "$(tcp $ORCH_IP 6443)"
  check M.3 "The mesh policy refuses the proxy port" closed "$(tcp $ORCH_IP 3128)"
  check M.4 "The mesh policy refuses the kubelet port" closed "$(tcp $ORCH_IP 10250)"
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

  # Effective rules equal configured rules. The platform adds one IPv6 deny of
  # its own, which is the only difference allowed.
  n=4
  for vm in orchestrator worker; do
    effective=$(az network nic list-effective-nsg -g $RG -n "nic-aisec-$vm" \
      --query "value[].effectiveSecurityRules[].[direction,to_string(priority),access,name]" -o tsv 2>/dev/null |
      grep -v defaultSecurityRules | awk '{sub(/.*\//, "", $4); print $1, $2, $3, $4}' |
      grep -v ' DefaultIPv6OutboundDeny$' | sort)
    configured=$(az network nsg show -g $RG -n "nsg-aisec-platform-$vm" \
      --query "securityRules[].[direction,to_string(priority),access,name]" -o tsv 2>/dev/null |
      awk '{print $1, $2, $3, $4}' | sort)
    check "Z.$n" "Effective rules on the $vm interface equal the configured rules" \
      "$(printf '%s' "$configured" | sha256sum | cut -c1-12)" "$(printf '%s' "$effective" | sha256sum | cut -c1-12)"
    n=$((n + 1))
  done

  flow() { # remote address:port, printed as "Access rule"
    az network watcher test-ip-flow -g $RG --vm vm-aisec-worker --direction Outbound --protocol TCP \
      --local "$WORK_IP:50000" --remote "$1" --query "join(' ', [access, ruleName])" -o tsv 2>/dev/null |
      sed 's#securityRules/##'
  }
  check Z.6 "Worker to the target network is denied by its own rule" "Deny deny-to-targets" "$(flow 10.50.0.4:22)"
  check Z.7 "Worker to the internet is denied by its own rule" "Deny deny-to-internet" "$(flow 1.1.1.1:443)"
  check Z.8 "Worker to the proxy is allowed by its own rule" "Allow allow-package-proxy-to-orchestrator" "$(flow $ORCH_IP:3128)"
  check Z.9 "Worker to the Kubernetes API is denied" "Deny deny-all-outbound" "$(flow $ORCH_IP:6443)"

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
