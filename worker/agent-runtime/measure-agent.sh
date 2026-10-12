#!/usr/bin/env bash
# Runs on the worker, as root. Runs the fixture question through the agent a
# few times. For each run it prints the wall time, the verdict of
# check_answer.py, what systemd said about the unit, the model server's own
# timing lines for the requests the run made, and what the run left behind.
#
# Usage: measure-agent.sh [--runs N]
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=pins.env
. "$here/pins.env"

runs=3
if [[ ${1:-} == --runs ]]; then
  runs=${2:?usage: measure-agent.sh [--runs N]}
fi

out=$(mktemp)
err=$(mktemp)
trap 'rm -f "$out" "$err"' EXIT

correct=0
for run in $(seq 1 "$runs"); do
  # A cursor marks the exact place in the journal. A timestamp has one-second
  # steps, and the last request of the run before lands inside them.
  cursor=$(journalctl --no-pager --unit=aisec-llama-server --lines=0 --show-cursor | sed -n 's/^-- cursor: //p')
  if [[ -z $cursor ]]; then
    echo "no journal cursor for aisec-llama-server" >&2
    exit 1
  fi
  start=$(date +%s%N)
  rc=0
  "$here/run-agent.sh" < "$FIXTURE_DIR/question.txt" > "$out" 2> "$err" || rc=$?
  wall=$(( ($(date +%s%N) - start) / 1000000 ))
  echo "== run $run: rc=$rc wall_ms=$wall"
  # A run that failed has no transcript worth checking, and counts as wrong.
  if [[ $rc == 0 ]] && /usr/bin/python3 -I "$FIXTURE_DIR/check_answer.py" < "$out"; then
    correct=$((correct + 1))
  else
    echo "-- output of the failed run"
    head -c 4000 "$out"
  fi
  # What the agent's messages are made of. A thinking block is a part of its
  # own, so this line shows whether the model server had thinking on.
  echo "-- parts of the agent's messages"
  /usr/bin/python3 -I -c '
import collections, json, sys
try:
    messages = json.load(sys.stdin)["messages"]
except (ValueError, KeyError, TypeError):
    sys.exit("(no transcript)")
print(dict(collections.Counter(
    part.get("type") for m in messages if m.get("role") == "assistant" for part in m.get("content", [])
)))' < "$out" || true
  echo "-- unit"
  cat "$err"
  echo "-- model server timings"
  journalctl --no-pager --output=cat --unit=aisec-llama-server --after-cursor="$cursor" | grep -E 'eval time|total time' || echo "(no timing lines)"
  # The run is over, so the unit and its private /tmp have to be gone.
  echo "-- left behind"
  echo "unit: $(systemctl is-active aisec-agent-job 2>/dev/null || true)"
  echo "private tmp directories: $(find /tmp /var/tmp -maxdepth 1 -name 'systemd-private-*aisec-agent-job*' | wc -l)"
done

echo
echo "$correct of $runs runs correct"
[[ $correct == "$runs" ]]
