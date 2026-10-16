#!/usr/bin/env bash
# Runs on the orchestrator, as root. Deploys the tool service from a copy of
# the repository: the namespaces, the service accounts, the network policies,
# the config maps, the secret, and the pod. Safe to run again. It changes
# nothing outside the tool-services and orchestration namespaces.
#
# Before it applies anything, it asks the cluster for a token of the dispatch
# account and checks that the issuer, audience, and subject in it are the ones
# the policy file names. A mismatch would refuse every registration later, so
# it stops here instead.
#
# Usage: deploy.sh REPO_COPY
set -euo pipefail

repo=${1:?usage: deploy.sh REPO_COPY}
here=$repo/platform/tool-service
policy=$repo/policies/tool-service.json
tls=/etc/aisec/tool-service
k() { k3s kubectl "$@"; }

for f in "$here/tool-service.yaml" "$policy" "$tls/tls.crt" "$tls/tls.key"; do
  [ -r "$f" ] || { echo "missing: $f" >&2; exit 1; }
done
if ! grep -Eq '^ *image: [^ ]+@sha256:[0-9a-f]{64}$' "$here/tool-service.yaml" ||
  grep -Eq '@sha256:0{64}$' "$here/tool-service.yaml"; then
  echo "tool-service.yaml names no image digest" >&2
  exit 1
fi

k apply -f "$here/namespaces.yaml"
# Each namespace's default account comes from Kubernetes, moments after the
# namespace. Ours goes on top of it, not in a race with it.
for ns in tool-services orchestration; do
  k wait --for=create serviceaccount/default -n "$ns" --timeout=60s
done
k apply -f "$here/service-accounts.yaml"
k apply -f "$here/network-policies.yaml"

# The claims a dispatch token carries, against the policy file.
token=$(k create token dispatch -n orchestration --audience "$(python3 -c '
import json, sys
print(json.load(open(sys.argv[1]))["registration_caller"]["audience"])' "$policy")" --duration 10m)
python3 - "$policy" "$token" <<'PY'
import base64, json, sys
expected = json.load(open(sys.argv[1]))["registration_caller"]
part = sys.argv[2].split(".")[1]
claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
head = sys.argv[2].split(".")[0]
header = json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))
found = {"issuer": claims.get("iss"), "audience": claims.get("aud"), "subject": claims.get("sub")}
if isinstance(found["audience"], list) and len(found["audience"]) == 1:
    found["audience"] = found["audience"][0]
print("token: alg", header.get("alg"), "kid", header.get("kid"))
for name, value in found.items():
    print(f"token {name}: {value}")
wrong = [name for name in found if found[name] != expected[name]]
if wrong:
    sys.exit("the policy file does not match the cluster: " + ", ".join(wrong))
PY

apply_from() { "$@" --dry-run=client -o yaml | k apply -f -; }
apply_from k create configmap tool-service-policy -n tool-services --from-file=policy.json="$policy"
apply_from k create configmap tool-service-evidence -n tool-services \
  --from-file=ev-0001.json="$here/evidence/synthetic/ev-0001.json"
k get --raw /openid/v1/jwks >"$tls/sa-jwks.json"
apply_from k create configmap tool-service-jwks -n tool-services --from-file=sa-jwks.json="$tls/sa-jwks.json"
apply_from k create secret tls tool-service-tls -n tool-services --cert="$tls/tls.crt" --key="$tls/tls.key"
# The dispatch pods check the server against the same certificate.
apply_from k create configmap tool-service-cert -n orchestration --from-file=tls.crt="$tls/tls.crt"

# The old pod's log goes with the pod. Before it is replaced, the audit copier
# has to make a whole pass that starts after the log's last write (ADR 0019).
# Run this with no job active, so the old pod writes nothing after now. Two
# passes ending after now: the second one started after the first ended.
if ! systemctl is-active --quiet aisec-audit-copy; then
  echo "the audit copier is not running" >&2
  exit 1
fi
now=$(mktemp)
trap 'rm -f "$now"' EXIT
for pass in 1 2; do
  for _ in $(seq 1 15); do
    [ -n "$(find /var/lib/aisec-audit-copy/ok -newer "$now" 2>/dev/null)" ] && break
    sleep 1
  done
  [ -n "$(find /var/lib/aisec-audit-copy/ok -newer "$now" 2>/dev/null)" ] ||
    { echo "the audit copier made no pass in 15 seconds" >&2; exit 1; }
  touch "$now"
  echo "audit copier pass $pass after the last line: done"
done

k apply -f "$here/tool-service.yaml"
# Config maps and secrets do not restart a pod. This does.
k rollout restart deployment/tool-service -n tool-services
k rollout status deployment/tool-service -n tool-services --timeout=180s
k get pods -n tool-services -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID}{"\n"}{end}'
