#!/usr/bin/env bash
# What a job leaves (milestone 6). Runs on the worker, as root, and reads
# everything a dispatched job makes on this machine: its unit instance, the
# unit's private directories and the files in them, the job account's
# processes and session, the unit's processes and dynamic user, the model
# server's slot, the journal's job lines, and every file changed since the
# unit started. The same reads run in two phases with opposite expectations.
#
#   what-a-job-leaves.sh during   # while a job's agent works: each read shows the job
#   what-a-job-leaves.sh after    # once its workflow has ended: each read shows nothing
#
# The checks G.3, G.4, G.9, G.10, and G.12 read the same things between jobs,
# where they pass. The during phase is their fail side: a read that shows
# nothing while a job runs would prove nothing when it shows nothing after.
# Nothing is changed in either phase.
#
# Every probe prints its name, the expected value, the value read, and PASS or
# FAIL, and the script exits 1 when any probe failed. Lines without a verdict
# are for the record: the files in the unit's directories, the unit's
# processes, the slot, systemd's lines about the unit, and the changed files.
set -uo pipefail

UNITS='aisec-agent-job@*'
MODEL_URL=http://127.0.0.1:8080
# Paths the system writes on its own, left out of the changed files read: the
# journal and logs, systemd's state, apt and its cache, the clock, the cloud
# agent, Ubuntu's own reports, and the operator's and root's shells, which
# write their history when a session ends. A job writes to none of these: its
# file system is read-only outside its private directories.
SYSTEM_PATHS=(/var/log /var/lib/systemd /var/lib/apt /var/cache /var/lib/chrony /var/lib/waagent
  /var/lib/landscape /var/lib/update-notifier /var/lib/ubuntu-advantage /home/aisec /root)
failed=0

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 2; }

# report PROBE EXPECTED VALUE [MODE]: one line, and the failed count. MODE
# "not" passes on any value but EXPECTED. An empty value fails in every mode.
report() {
  local probe=$1 expected=$2 value=$3 mode=${4:-equal} verdict=""
  value=${value//$'\n'/ }
  case $mode in
    not) expected="not $expected" ;;&
    *) [ -z "$value" ] && verdict=FAIL ;;&
    not) [ -z "$verdict" ] && { [ "$value" != "${expected#not }" ] && verdict=PASS || verdict=FAIL; } ;;
    *) [ -z "$verdict" ] && { [ "$value" = "$expected" ] && verdict=PASS || verdict=FAIL; } ;;
  esac
  [ "$verdict" = PASS ] || failed=$((failed + 1))
  printf '%-44s expected %-18s read %-40s %s\n' "$probe" "$expected" "${value:0:40}" "$verdict"
}

note() { printf '%-44s %s\n' "$1" "${2//$'\n'/; }"; }

value() { sed -n "s/^$1=//p" <<< "$probe" | head -n 1; }

# The unit's start, as the job program's first journal line, for the changed
# files read. Without one, the read takes the last hour.
started() {
  local line
  line=$(journalctl --no-pager -o short-unix -u "$UNITS" 2>/dev/null | grep '"erase": "before"' | tail -n 1)
  [ -n "$line" ] && echo "@${line%%.*}" || echo "1 hour ago"
}

# The slot, read ten times over twenty seconds: whether it processed a prompt
# in any of them. The agent waits on the tool service between prompts, so one
# read can find the slot idle during a job.
slot_busy() {
  local i
  for i in $(seq 1 10); do
    curl -s --max-time 3 "$MODEL_URL/slots" 2>/dev/null | grep -q '"is_processing":true' && { echo true; return; }
    [ "$i" -lt 10 ] && sleep 2
  done
  echo false
}

reads() {
  local since prune=() path
  for path in "${SYSTEM_PATHS[@]}"; do prune+=(-o -path "$path"); done
  since=$(started)
  echo "instances=$(systemctl list-units --all --no-legend "$UNITS" 2>/dev/null | wc -l)"
  echo "instance_state=$(systemctl list-units --all --no-legend "$UNITS" 2>/dev/null | awk '{print $3, $4}' | head -n 1)"
  echo "by_hand_unit=$(systemctl show aisec-agent-job -p LoadState --value 2>/dev/null)"
  echo "private_dirs=$(find /tmp /var/tmp -maxdepth 1 -name 'systemd-private-*-aisec-agent-job@*.service-*' 2>/dev/null | wc -l)"
  echo "work_files=$(find /tmp/systemd-private-*-aisec-agent-job@*.service-*/tmp -type f 2>/dev/null | sed 's|.*/tmp/job/||' | sort | tr '\n' ' ')"
  echo "work_present=$([ -n "$(find /tmp/systemd-private-*-aisec-agent-job@*.service-*/tmp -type f 2>/dev/null | head -n 1)" ] && echo present || echo none)"
  echo "job_account_processes=$(pgrep -c -u aisec-job 2>/dev/null)"
  echo "unit_processes=$(grep -l 'aisec-agent-job@' /proc/[0-9]*/cgroup 2>/dev/null | wc -l)"
  echo "unit_process_list=$(grep -l 'aisec-agent-job@' /proc/[0-9]*/cgroup 2>/dev/null | while read -r f; do p=${f#/proc/}; ps -o user:32=,comm= -p "${p%/cgroup}" 2>/dev/null | tr -s ' '; done | tr '\n' ';')"
  echo "goose_processes=$(pgrep -c -x goose 2>/dev/null)"
  echo "dynamic_users=$(find /run/systemd/dynamic-uid -maxdepth 1 -name '*aisec-agent-job*' 2>/dev/null | wc -l)"
  echo "job_sessions=$(loginctl list-sessions --no-legend 2>/dev/null | grep -c -w aisec-job)"
  echo "shm_entries=$(find /dev/shm -mindepth 1 2>/dev/null | wc -l)"
  echo "slot_busy=$(slot_busy)"
  echo "slot=$(curl -s --max-time 3 "$MODEL_URL/slots" 2>/dev/null | python3 -I -c 'import json, sys
s = json.load(sys.stdin)[0]
print({k: s.get(k) for k in ("is_processing", "id_task", "n_prompt_tokens", "n_prompt_tokens_processed", "n_prompt_tokens_cache")})' 2>/dev/null)"
  echo "journal_last=$(journalctl --no-pager -o cat -u "$UNITS" 2>/dev/null | grep '"slot_erased"' | tail -n 1 |
    sed -n 's/.*"\(erase\|outcome\)": "\([a-z]*\)".*"slot_erased": \([a-z]*\).*/\2 \3/p')"
  echo "unit_lines=$(journalctl --no-pager -o short-iso -u "$UNITS" --since -2h 2>/dev/null | grep -E 'Started|Deactivated|Consumed|Failed|Stopping' | tail -n 4 | cut -c12- | tr '\n' ';')"
  echo "changed_since=$since"
  echo "changed_files=$(find / /tmp -xdev \( -false "${prune[@]}" \) -prune -o -type f -newermt "$since" -print 2>/dev/null | sort | tr '\n' ' ')"
  echo "changed_count=$(find / /tmp -xdev \( -false "${prune[@]}" \) -prune -o -type f -newermt "$since" -print 2>/dev/null | wc -l)"
}

case ${1:-} in
  during)
    echo "== what a job leaves, during, $(date -u +%FT%TZ), $(hostname)"
    probe=$(reads)
    report "job unit instances (G.9 reads 0 between jobs)" 1 "$(value instances)"
    report "the instance's state" "active running" "$(value instance_state)"
    report "the unit a run by hand makes (G.3)" not-found "$(value by_hand_unit)"
    report "private directories (G.4 reads 0 between jobs)" 2 "$(value private_dirs)"
    report "files in the job's directory" present "$(value work_present)"
    note "  the files" "$(value work_files)"
    report "processes of the job account" 0 "$(value job_account_processes)" not
    report "processes in the unit" 0 "$(value unit_processes)" not
    note "  the processes" "$(value unit_process_list)"
    report "Goose processes" 0 "$(value goose_processes)" not
    report "the unit's dynamic user" 1 "$(value dynamic_users)"
    report "sessions of the job account" 1 "$(value job_sessions)"
    report "entries in /dev/shm" 0 "$(value shm_entries)"
    report "the slot processed a prompt within 20 s" true "$(value slot_busy)"
    note "  the slot" "$(value slot)"
    report "the journal's last job line" "before true" "$(value journal_last)"
    report "files changed since the unit started" 0 "$(value changed_count)" not
    note "  since" "$(value changed_since)"
    note "  the files" "$(value changed_files)"
    ;;
  after)
    echo "== what a job leaves, after, $(date -u +%FT%TZ), $(hostname)"
    probe=$(reads)
    report "job unit instances (G.9)" 0 "$(value instances)"
    report "the unit a run by hand makes (G.3)" not-found "$(value by_hand_unit)"
    report "private directories (G.4)" 0 "$(value private_dirs)"
    report "files in the job's directory" none "$(value work_present)"
    report "processes of the job account (G.12)" 0 "$(value job_account_processes)"
    report "processes in the unit" 0 "$(value unit_processes)"
    report "Goose processes" 0 "$(value goose_processes)"
    report "the unit's dynamic user (G.12)" 0 "$(value dynamic_users)"
    report "sessions of the job account (G.12)" 0 "$(value job_sessions)"
    report "entries in /dev/shm" 0 "$(value shm_entries)"
    report "the slot processed a prompt within 20 s" false "$(value slot_busy)"
    note "  the slot" "$(value slot)"
    report "the journal's last job line (G.10)" "ended true" "$(value journal_last)"
    note "  systemd's lines about the unit" "$(value unit_lines)"
    report "files changed since the unit started" 0 "$(value changed_count)"
    note "  since" "$(value changed_since)"
    note "  the files" "$(value changed_files)"
    ;;
  *) echo "usage: $0 during|after" >&2; exit 2 ;;
esac
echo "== $failed failed"
[ "$failed" -eq 0 ]
