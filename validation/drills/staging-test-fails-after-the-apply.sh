#!/usr/bin/env bash
# The interrupted staging test drill (milestone 6). Runs on the orchestrator,
# as root, and breaks a staging test after its change is applied on the copy:
# the copy's collector token is moved aside, so the configured half fails
# after the apply, and is moved back afterwards. What the drill reads is the
# library's reset after the failure. With it, the copy rests at the seed when
# the test has failed; without it, the copy holds the change until the next
# staging test's first reset, which Q.3 shows as drift.
#
#   staging-test-fails-after-the-apply.sh
#
# The change removes inventory-reader from its one permission, so a copy left
# changed answers `missing` for that account. The drill prints the copy's
# configured half before, the staging test's result, and six probes with
# their expected values and PASS or FAIL, and exits 1 when any probe failed.
# Nothing stays changed: the token goes back, and the change on the copy is
# undone by the reset after it.
set -uo pipefail

COPY=/etc/aisec/netbox-rehearsal
LIB=/usr/local/lib/aisec
TOKEN=$COPY/tokens/aisec-collector
CONTRACT=/etc/aisec/netbox/contract.json
CHANGE='{"account": "inventory-reader", "permission_id": 0, "permission": "inventory-reader: tenant-a inventory"}'
WITHIN="inventory-reader:within inventory-reader-control:within"
failed=0

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 2; }
for f in "$TOKEN" "$CONTRACT" "$LIB/rehearse.py" "$LIB/netbox_access.py" "$COPY/reset/seed.sha256"; do
  [ -f "$f" ] || { echo "missing: $f" >&2; exit 2; }
done
[ -e "$TOKEN.drill" ] && { echo "$TOKEN.drill exists: an earlier drill did not put the token back" >&2; exit 2; }

probe() {
  local name=$1 expected=$2 got=$3
  if [ "$got" = "$expected" ]; then
    echo "PASS  $name: $got"
  else
    echo "FAIL  $name: expected '$expected', got '$got'"
    failed=$((failed + 1))
  fi
}

configured() {
  # The copy's configured half, as the staging test runs it.
  env AISEC_NETBOX_URL=https://10.50.1.4:8443 AISEC_NETBOX_CERT="$COPY/tls.crt" \
    AISEC_NETBOX_TOKENS="$COPY/tokens" python3 -I "$LIB/netbox_access.py" configured --summary \
    <"$CONTRACT" 2>/dev/null || echo "not read"
}

field() {
  # One field of the result: a string as is, anything else as JSON.
  printf %s "$result" | python3 -I -c 'import json, sys
value = json.load(sys.stdin).get(sys.argv[1])
print(value if isinstance(value, str) else json.dumps(value))' "$1"
}

seed=$(cat "$COPY/reset/seed.sha256")
echo "the copy's configured half before: $(configured)"

mv "$TOKEN" "$TOKEN.drill"
trap 'mv -n "$TOKEN.drill" "$TOKEN" 2>/dev/null' EXIT
result=$(python3 -I -c 'import json, sys
sys.path.insert(0, sys.argv[1])
import rehearse
change = json.loads(sys.argv[2])
print(json.dumps(rehearse.rehearse([change], json.load(open(sys.argv[3])))))' "$LIB" "$CHANGE" "$CONTRACT")
mv "$TOKEN.drill" "$TOKEN"
trap - EXIT
[ -n "$result" ] || { echo "the staging test printed nothing" >&2; exit 2; }
echo "result: $result"

probe "the first reset restored the seed" "$seed" "$(field reset)"
probe "one change applied on the copy" 1 "$(field applied | python3 -I -c 'import json, sys; print(len(json.load(sys.stdin)))')"
probe "the test failed" false "$(field passed)"
reason=$(field reason)
case "$reason" in
  *"configured half"*) echo "PASS  the reason names the configured half: $reason" ;;
  *) echo "FAIL  the reason names the configured half: got '$reason'"; failed=$((failed + 1)) ;;
esac
probe "the reset after it restored the seed" "$seed" "$(field reset_after)"
probe "the copy's configured half after" "$WITHIN" "$(configured)"
echo "== $failed failed"
exit "$((failed > 0))"
