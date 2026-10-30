#!/usr/bin/env bash
# The same fix twice drill (milestone 6). Runs on the orchestrator, as root,
# and proposes, for a kept matched job, a fix that an earlier allowed and
# rehearsed bundle holds already. The earlier bundle is a fixture the drill
# writes, named after the stamp, removing inventory-reader from its tenant-a
# permission by the live ID the job's collection holds. The proposal is the
# operator's (--proposals), since no job on the seed finds a fix to propose.
# What the drill reads is the propose command's refusal (ADR 0053), and
# that the refusal lifts once a delivery result for the earlier bundle says
# passed. The second proposal then reaches the policy, which refuses it
# since the account is within, after the staging test on the copy that
# every named proposal gets.
#
#   the-same-fix-twice.sh JOB
#
# JOB matched, its collection is kept, and it was not proposed. Prints both
# proposals' output, three probes with PASS or FAIL, and exits 1 when any
# failed. Nothing stays: the fixture bundle, the delivery result fixture,
# the proposals file, and the bundle the second proposal wrote for JOB are
# removed at the end. A bundle with pr-body.md for JOB, from a proposal the
# policy allowed, is not the drill's to remove: it stays, and the rule then
# holds that fix until it is delivered.
set -uo pipefail

PROPOSALS=/var/lib/aisec/proposals
DELIVERIES=/var/lib/aisec/delivery/results
EVIDENCE=/var/lib/aisec/evidence/netbox
ACCOUNT=inventory-reader
PERMISSION="inventory-reader: tenant-a inventory"
JOB=${1:-}
failed=0

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 2; }
[[ $JOB =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] || { echo "usage: the-same-fix-twice.sh JOB" >&2; exit 2; }
[ -f "$EVIDENCE/$JOB/configured.json" ] || { echo "no collection for $JOB" >&2; exit 2; }
[ -e "$PROPOSALS/$JOB" ] && { echo "$JOB was proposed already" >&2; exit 2; }
command -v propose-netbox-fix >/dev/null || { echo "no propose-netbox-fix" >&2; exit 2; }
STAMP=$(date -u +%m%d%H%M)
FIRST=nb-$STAMP-first
[ -e "$PROPOSALS/$FIRST" ] && { echo "$PROPOSALS/$FIRST exists" >&2; exit 2; }
ID=$(python3 -I -c 'import json, sys
found = json.load(open(sys.argv[1]))["accounts"][sys.argv[2]]["permissions"]
print(next(p["id"] for p in found if p["name"] == sys.argv[3]))' \
  "$EVIDENCE/$JOB/configured.json" "$ACCOUNT" "$PERMISSION") || { echo "the permission is not in the collection" >&2; exit 2; }
echo "the fixture $FIRST removes $ACCOUNT from '$PERMISSION' (ID $ID)"

work=$(mktemp -d /run/aisec-drill.XXXXXX)
# Invoked by the trap below.
# shellcheck disable=SC2329
cleanup() {
  [[ $work =~ ^/run/aisec-drill\.[A-Za-z0-9]{6}$ ]] && rm -r -- "$work"
  [[ $FIRST =~ ^nb-[0-9]{8}-first$ ]] && rm -r -f -- "${PROPOSALS:?}/$FIRST"
  rm -f -- "$DELIVERIES/approve_netbox_$FIRST.json"
  # The job's bundle, when the drill's second proposal wrote it: one file.
  if [ -d "$PROPOSALS/$JOB" ] && [ "$(ls -A "$PROPOSALS/$JOB")" = "proposal.json" ]; then
    rm -r -- "${PROPOSALS:?}/${JOB:?}"
  fi
}
trap cleanup EXIT

indent() { while IFS= read -r line; do printf '   %s\n' "$line"; done; }

probe() {
  local name=$1 expected=$2 got=$3
  if [ "$got" = "$expected" ]; then
    echo "PASS  $name: $got"
  else
    echo "FAIL  $name: expected '$expected', got '$got'"
    failed=$((failed + 1))
  fi
}

# The fixture bundle: an allowed, rehearsed fix, as the propose command
# writes one, with pr-body.md marking it as the drill's.
mkdir -m 700 "$PROPOSALS/$FIRST" || exit 2
python3 -I -c 'import json, sys, time
first, account, permission, pid = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
proposal = {"account": account, "action": "remove", "permission": pid, "references": ["ev-0002"]}
bundle = {
    "job": first, "case": "seed", "collected": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "source": "drill",
    "comparison": {"outcome": "match", "accounts": [], "proposals": [proposal], "unread_proposals": 0},
    "policy": {"allowed": True, "reasons": [], "changes": [
        {"account": account, "permission_id": pid, "permission": permission}]},
    "rehearsal": {"passed": True, "verdicts": {}},
}
json.dump(bundle, open(sys.argv[5] + "/proposal.json", "w"), indent=2)
open(sys.argv[5] + "/pr-body.md", "w").write("## A fixture of the same fix twice drill\n")
json.dump([proposal], open(sys.argv[6], "w"))' "$FIRST" "$ACCOUNT" "$PERMISSION" "$ID" "$PROPOSALS/$FIRST" "$work/proposals.json" || exit 2

echo "-- the first proposal for $JOB, with the fixture undelivered"
out=$(propose-netbox-fix "$JOB" --proposals "$work/proposals.json" 2>&1)
indent <<<"$out"
case "$out" in
  *"the same fix as $FIRST, not delivered"*) echo "PASS  the proposal is refused as the same fix" ;;
  *) echo "FAIL  the proposal is refused as the same fix: not in the output"; failed=$((failed + 1)) ;;
esac
probe "no bundle written for $JOB" absent "$([ -e "$PROPOSALS/$JOB" ] && echo present || echo absent)"

printf '{"tag": "approve/netbox/%s", "passed": true, "source": "the same fix twice drill"}\n' "$FIRST" \
  >"$DELIVERIES/approve_netbox_$FIRST.json"
chmod 600 "$DELIVERIES/approve_netbox_$FIRST.json"
echo "-- the second proposal, with a passed delivery result for the fixture"
out=$(propose-netbox-fix "$JOB" --proposals "$work/proposals.json" 2>&1)
indent <<<"$out"
case "$out" in
  *"the same fix"*) echo "FAIL  the proposal reaches the policy: still refused as the same fix"; failed=$((failed + 1)) ;;
  *"policy: refused"*) echo "PASS  the proposal reaches the policy: policy: refused, bundle $([ -f "$PROPOSALS/$JOB/proposal.json" ] && echo written || echo missing)" ;;
  *) echo "FAIL  the proposal reaches the policy: neither line in the output"; failed=$((failed + 1)) ;;
esac
echo "== $failed failed"
exit "$((failed > 0))"
