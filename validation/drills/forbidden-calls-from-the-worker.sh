#!/usr/bin/env bash
# The forbidden calls drill (milestone 6). Runs on the worker, as root, and
# tries from inside a job's sandbox what a compromised job would try: a
# connection to the internet, the targets, the resolver, the API server, and
# the registration port; a read of the host's files and of other units'
# private /tmp; an edit of a unit file, the firewall, a kernel setting, and
# the model file; and calls to the tool service without a token, with a
# made-up one, on the registration path, and with the tokens given on
# standard input.
#
# The sandbox is the installed job unit's: every [Service] line of
# /etc/systemd/system/aisec-agent-job@.service except the program, its
# standard streams, and its environment goes to systemd-run as a property,
# so the drill runs under the same settings as a job, as a dynamic user. The
# connection probes also run as root for comparison. Nothing is changed: each
# edit probe is expected to fail, and a probe that succeeds is the finding.
#
#   forbidden-calls-from-the-worker.sh sandbox   # connections, files, edits, tokenless calls
#   forbidden-calls-from-the-worker.sh tokens    # one call per NAME=TOKEN=EXPECTED line on standard input
#
# Every probe prints its name, the expected value, the value read, and PASS or
# FAIL, and the script exits 1 when any probe failed. A connection probe
# passes on anything but "open"; two control probes to addresses the job
# needs show that the same function reads "open" where the sandbox may
# connect. An edit probe passes when the command fails, and prints the error.
# The tokens phase calls get_evidence for ev-0001 with each token inside the
# sandbox, with the token on the sandbox's standard input and never on a
# command line, and passes when the HTTP status and the result equal EXPECTED,
# for example "200 allowed", "200 refused: nothing by that reference", or
# '401 {"error": "refused"}'.
#
# The probe scripts are built in single quotes on purpose: they expand in the
# sandbox, not here.
# shellcheck disable=SC2016
set -uo pipefail

UNIT=/etc/systemd/system/aisec-agent-job@.service
TOOL=https://tool-service.aisec.internal:30443
CERT=/etc/aisec/tool-service.crt
ORCH=10.40.0.4
MODEL_FILE=$(systemctl show aisec-llama-server -p ExecStart --value 2>/dev/null | sed -n 's/.* --model \([^ ]*\) .*/\1/p')
MODEL_FILE=${MODEL_FILE:-/nonexistent}
failed=0

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 2; }
[ -f "$UNIT" ] || { echo "no job unit at $UNIT" >&2; exit 2; }

# The unit's [Service] lines as systemd-run properties. The program, the
# streams, the environment, and the working directory are the drill's own.
# systemd-run reads a symbolic address such as "localhost" only when it is
# the whole value, so an address list becomes one property per address.
mapfile -t props < <(sed -n '/^\[Service\]/,/^\[/p' "$UNIT" |
  grep -E '^[A-Za-z]+=' | grep -v -E '^(ExecStart|Standard(Input|Output|Error)|Environment|WorkingDirectory)=' |
  awk -F= '/^IPAddress(Allow|Deny)=/ { n = split($2, a, " "); for (i = 1; i <= n; i++) print $1 "=" a[i]; next } { print }' |
  sed 's/^/--property=/')

# sandbox NAME SCRIPT [INPUT]: runs SCRIPT with bash in a transient unit with
# the job unit's properties, INPUT on its standard input, and prints its output.
sandbox() {
  local name=$1 script=$2 input=${3:-}
  printf '%s' "$input" | systemd-run --quiet --wait --pipe --collect --unit "aisec-drill-$name" \
    --description "Forbidden calls drill: $name" "${props[@]}" \
    /bin/bash -c "$script" 2>&1
}

# report PROBE EXPECTED VALUE [MODE]: one line, and the failed count. MODE
# "not" passes on any value but EXPECTED; "starts" when VALUE starts with it.
report() {
  local probe=$1 expected=$2 value=$3 mode=${4:-equal} verdict
  value=${value//$'\n'/ }
  case $mode in
    not) [ "$value" != "$expected" ] && verdict=PASS || verdict=FAIL; expected="not $expected" ;;
    starts) [ "${value#"$expected"}" != "$value" ] && verdict=PASS || verdict=FAIL ;;
    *) [ "$value" = "$expected" ] && verdict=PASS || verdict=FAIL ;;
  esac
  [ "$verdict" = PASS ] || failed=$((failed + 1))
  printf '%-46s expected %-36s read %-44s %s\n' "$probe" "$expected" "${value:0:44}" "$verdict"
}

value() { sed -n "s/^$1=//p" <<< "$2" | head -n 1; }

# A connection probe. "open" is the one value that fails a containment probe.
tcp_fn='
tcp() {
  local out rc
  out=$(LC_ALL=C timeout "${3:-5}" bash -c "</dev/tcp/$1/$2" 2>&1); rc=$?
  case "$rc:$out" in
    0:*) echo open ;;
    124:*) echo timeout ;;
    *"Connection refused"*) echo refused ;;
    *"Operation not permitted"*) echo denied ;;
    *"No route to host"*|*"Network is unreachable"*) echo unreachable ;;
    *) echo error ;;
  esac
}
'
connection_probes="$tcp_fn"'
echo "internet=$(tcp 1.1.1.1 443)"
echo "netbox_api=$(tcp 10.50.0.4 8443)"
echo "rehearsal_api=$(tcp 10.50.1.4 8443)"
echo "resolver_tcp=$(tcp 168.63.129.16 53)"
echo "api_server=$(tcp '"$ORCH"' 6443)"
echo "kubelet=$(tcp '"$ORCH"' 10250)"
echo "registration_port=$(tcp '"$ORCH"' 8444)"
echo "orchestrator_ssh=$(tcp '"$ORCH"' 22)"
echo "tool_port=$(tcp '"$ORCH"' 30443)"
echo "model_server=$(tcp 127.0.0.1 8080)"
echo "public_name=$(timeout 6 getent hosts example.com >/dev/null 2>&1 && echo resolves || echo no)"
'

# connections WHO OUTPUT: the same addresses as the C checks, read from WHO.
connections() {
  local who=$1 out=$2 key
  for key in internet netbox_api rehearsal_api resolver_tcp api_server kubelet registration_port orchestrator_ssh; do
    report "$who: $key" open "$(value "$key" "$out")" not
  done
  report "$who: public_name" no "$(value public_name "$out")"
  report "$who: tool_port (control)" open "$(value tool_port "$out")"
  report "$who: model_server (control)" open "$(value model_server "$out")"
}

# A read's outcome: "readable", "absent", or "denied".
read_fn='
readable() {
  if head -c 1 "$1" >/dev/null 2>&1; then echo readable
  elif ls -d "$1" 2>&1 | grep -q "No such"; then echo absent
  else echo denied; fi
}
'
files() {
  local out
  out=$(sandbox files "$read_fn"'
echo "model_file=$(readable '"$MODEL_FILE"')"
echo "tool_cert=$(readable '"$CERT"')"
echo "system_text=$(readable /usr/local/lib/aisec/job/system.txt)"
echo "job_key=$(readable /home/aisec-job/.ssh/authorized_keys)"
echo "shadow=$(readable /etc/shadow)"
echo "journal=$(journalctl -n 1 --no-pager -q 2>/dev/null | grep -c .)"
echo "host_private_tmp=$(ls -d /tmp/systemd-private-* /var/tmp/systemd-private-* 2>/dev/null | wc -l)"
echo "job_socket=$(python3 -I -c "import socket
s = socket.socket(socket.AF_UNIX)
try:
    s.connect(\"/run/aisec-job/agent.sock\"); print(\"connected\")
except OSError as e:
    print(e.strerror.lower().replace(\" \", \"-\"))" 2>&1)"
')
  report "sandbox: the model file" readable "$(value model_file "$out")"
  report "sandbox: the tool certificate" readable "$(value tool_cert "$out")"
  report "sandbox: the system text" readable "$(value system_text "$out")"
  report "sandbox: the dispatch key's line" readable "$(value job_key "$out")" not
  report "sandbox: /etc/shadow" denied "$(value shadow "$out")"
  report "sandbox: journal lines readable" 0 "$(value journal "$out")"
  report "sandbox: other units' private /tmp seen" 0 "$(value host_private_tmp "$out")"
  report "sandbox: a connection to the job socket" permission-denied "$(value job_socket "$out")"
}

# An edit's outcome: "fails: " and the error's last clause, or "succeeds". The
# kernel setting is written as a file: sysctl exits 0 when it is ignored.
edit_fn='
attempt() {  # attempt COMMAND...: the command may not succeed
  local err
  if err=$("$@" 2>&1); then echo succeeds; else echo "fails: $(echo "$err" | head -n 1 | sed "s/.*: //" | tr "A-Z " "a-z-")"; fi
}
'
edits() {
  local out
  out=$(sandbox edits "$edit_fn"'
echo "unit_file=$(attempt touch /etc/systemd/system/aisec-drill.service)"
echo "firewall=$(attempt nft list ruleset)"
echo "ip_forward=$(attempt bash -c "echo 1 > /proc/sys/net/ipv4/ip_forward")"
echo "socket_unit=$(attempt systemctl stop aisec-agent-job.socket)"
echo "model_file_write=$(attempt bash -c "printf x >> '"$MODEL_FILE"'")"
')
  report "sandbox: write a unit file" fails "$(value unit_file "$out")" starts
  report "sandbox: read the firewall" fails "$(value firewall "$out")" starts
  report "sandbox: set ip_forward" fails "$(value ip_forward "$out")" starts
  report "sandbox: stop the job socket" fails "$(value socket_unit "$out")" starts
  report "sandbox: write the model file" fails "$(value model_file_write "$out")" starts
}

# A tool call: the HTTP status, then "allowed", "refused: REASON", or the
# body's first 80 characters. One request per probe: the four tokenless calls
# stay far under the service's limit of 30 untrusted requests a minute.
call_fn='
call() {  # call TOKEN PATH
  local out status body
  out=$(curl -s --max-time 10 --cacert '"$CERT"' -w "\n%{http_code}" -X POST \
    ${1:+-H "Authorization: Bearer $1"} -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_evidence\",\"arguments\":{\"reference\":\"ev-0001\"}}}" \
    "'"$TOOL"'$2" 2>/dev/null)
  status=$(tail -n 1 <<< "$out"); body=$(head -n -1 <<< "$out")
  case $body in
    *\"isError\":\ false*|*\"isError\":false*) echo "$status allowed" ;;
    *refused:\ *) echo "$status $(echo "$body" | sed -n "s/.*\(refused: [^\"\\\\]*\).*/\1/p" | head -n 1)" ;;
    *) echo "$status ${body:0:80}" ;;
  esac
}
'
tokenless() {
  local out
  out=$(sandbox tokenless "$call_fn"'
echo "no_token=$(call "" /mcp)"
echo "made_up_token=$(call 0000000000000000000000000000000000000000000000000000000000000000 /mcp)"
echo "registration_path=$(call "" /jobs)"
echo "tls_untrusted=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" -X POST -d "{}" '"$TOOL"'/mcp)"
')
  report "sandbox: a call without a token" '401 {"error": "refused"}' "$(value no_token "$out")"
  report "sandbox: a call with a made-up token" '401 {"error": "refused"}' "$(value made_up_token "$out")"
  report "sandbox: a call on the registration path" '404 {"error": "refused"}' "$(value registration_path "$out")"
  report "sandbox: the system's trust store" 000 "$(value tls_untrusted "$out")"
}

tokens() {
  local line name rest token expected out
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    name=${line%%=*}; rest=${line#*=}; token=${rest%%=*}; expected=${rest#*=}
    out=$(sandbox "token-$name" "$call_fn"'read -r t; call "$t" /mcp' "$token"$'\n')
    report "sandbox: get_evidence ev-0001 as $name" "$expected" "$out"
  done
}

case ${1:-} in
  sandbox)
    echo "== forbidden calls drill, $(date -u +%FT%TZ), $(hostname), ${#props[@]} unit properties"
    connections root "$(bash -c "$connection_probes" 2>&1)"
    connections sandbox "$(sandbox connections "$connection_probes")"
    files
    edits
    tokenless
    ;;
  tokens) tokens ;;
  *) echo "usage: $0 sandbox|tokens" >&2; exit 2 ;;
esac
echo "== $failed failed"
[ "$failed" -eq 0 ]
