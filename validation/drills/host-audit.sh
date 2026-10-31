#!/bin/bash
# Milestone 6, slice 8: does the host audit catch what it is there for? Runs
# as root on the orchestrator or the worker, in an operator's session (ADR
# 0054). Four probes, each PASS or FAIL, then "== N failed":
#   write  a file made and removed under /etc/aisec: records with the key
#          aisec-config, in the audit daemon's log and in the journal, one of
#          them naming the file
#   exec   a program run as a dynamic user: a record with the key aisec-exec
#   root   this script's own commands, run as root in a login session:
#          records with the key aisec-root
#   aide   a file added under /usr/local/lib/aisec: the check reports one
#          added entry and logs it; removed again, it reports none
# Nothing stays: both files are removed, and the baseline is not rewritten.
# The fail side is a machine without the install: every probe FAIL.
#   sudo bash host-audit.sh
set -uo pipefail
failed=0
at_least() { # NAME MIN ACTUAL
  if [[ ${3:-} =~ ^[0-9]+$ ]] && [ "$3" -ge "$2" ]; then
    echo "PASS  $1: $3"
  else
    echo "FAIL  $1: expected at least $2, got '${3:-nothing}'"; failed=$((failed + 1))
  fi
}
equals() { # NAME EXPECTED ACTUAL
  if [ -n "${3:-}" ] && [ "$2" = "$3" ]; then
    echo "PASS  $1: $3"
  else
    echo "FAIL  $1: expected '$2', got '${3:-nothing}'"; failed=$((failed + 1))
  fi
}
# Records since this script started, from the daemon's own log (ausearch) and
# from the journal, where the syslog plugin's lines land on both VMs.
stamp=$(date -u +%s)
start=$(date -u -d "@$stamp" +%H:%M:%S)
daemon() { ausearch --input-logs -ts "$start" "$@" 2>/dev/null | grep -c "^type=SYSCALL"; }
journal() { journalctl --since "@$stamp" -o cat 2>/dev/null | grep -F "$1" | grep -c -F "$2"; }

echo "== write: a file under /etc/aisec, made and removed"
echo "Expected: at least 2 SYSCALL records with the key aisec-config in the daemon's log and in the journal, and a PATH record naming the file in each"
file=/etc/aisec/host-audit-drill-$stamp
install -m 0600 /dev/null "$file" && rm -f "$file"
sleep 3
at_least "write: records in the daemon's log" 2 "$(daemon -k aisec-config)"
at_least "write: records naming the file in the daemon's log" 1 "$(ausearch --input-logs -ts "$start" -k aisec-config 2>/dev/null | grep -c -F "name=\"$file\"")"
at_least "write: records in the journal" 2 "$(journal 'key="aisec-config"' 'type=SYSCALL')"
at_least "write: records naming the file in the journal" 1 "$(journal 'type=PATH' "name=\"$file\"")"

echo "== exec: a program run as a dynamic user"
echo "Expected: at least 1 SYSCALL record with the key aisec-exec for comm \"true\", in the daemon's log and in the journal"
systemd-run --quiet --wait --collect -p DynamicUser=yes --unit "host-audit-drill-$stamp" /bin/true
sleep 3
at_least "exec: records in the daemon's log" 1 "$(daemon -k aisec-exec -c true)"
at_least "exec: records in the journal" 1 "$(journal 'key="aisec-exec"' 'comm="true"')"

echo "== root: this script's own commands, as root in a login session"
echo "Expected: at least 1 SYSCALL record with the key aisec-root for comm \"install\", in the daemon's log and in the journal"
at_least "root: records in the daemon's log" 1 "$(daemon -k aisec-root -c install)"
at_least "root: records in the journal" 1 "$(journal 'key="aisec-root"' 'comm="install"')"

echo "== aide: a file added under /usr/local/lib/aisec, then removed"
echo "Expected: a check line 'added=1 removed=0 changed=0' and the report naming the file; after the removal 'added=0 removed=0 changed=0'"
added=/usr/local/lib/aisec/host-audit-drill-$stamp
echo drill > "$added"
report=$(aisec-aide-check 2>&1)
last() { journalctl -t aisec-aide --since "@$stamp" -o cat 2>/dev/null | grep "^check " | tail -n 1 | cut -d " " -f 1-4; }
equals "aide: the check's line with the file" "check added=1 removed=0 changed=0" "$(last)"
at_least "aide: the report names the file" 1 "$(printf '%s\n' "$report" | grep -c -F "$added")"
rm -f "$added"
aisec-aide-check >/dev/null 2>&1
equals "aide: the check's line after the removal" "check added=0 removed=0 changed=0" "$(last)"

echo "== $failed failed"
[ "$failed" -eq 0 ]
