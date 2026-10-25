#!/usr/bin/env bash
# Runs on the orchestrator, as root, after fetch.sh. Applies Argo's custom
# resource definitions from the checked release file, the controller, the
# accounts and Roles in orchestration, the network policies, and the workflow
# template (ADR 0029), and makes the comparison step's config map once (ADR
# 0041). Run it again after a change to any of them. The dispatch key is a
# separate step: make-dispatch-key.sh.
#
# Usage: install.sh STAGE_DIR
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=${1:?usage: install.sh STAGE_DIR}
# shellcheck source=pins.env
. "$here/pins.env"
kubectl() { k3s kubectl "$@"; }

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
file=$stage/namespace-install.yaml
echo "$ARGO_INSTALL_SHA256  $file" | sha256sum --check --quiet

echo "== custom resource definitions, $ARGO_VERSION"
# The definitions are too large for client-side apply's annotation.
/usr/bin/python3 -I "$here/crds.py" "$file" | kubectl apply --server-side --force-conflicts -f -
kubectl wait --for condition=established --timeout=60s crd/workflows.argoproj.io crd/workflowtemplates.argoproj.io crd/workflowtaskresults.argoproj.io

echo "== the namespace, and its default account without a token"
kubectl apply -f <(sed -n '1,/^---$/p' "$here/argo.yaml" | sed '$d')
# Kubernetes makes the default account moments after the namespace (K.6).
for _ in $(seq 30); do
  kubectl -n argo get serviceaccount default > /dev/null 2>&1 && break
  sleep 1
done
kubectl -n argo patch serviceaccount default -p '{"automountServiceAccountToken": false}'

echo "== the controller, the accounts, the policies, and the template"
kubectl apply -f "$here/network-policies.yaml"
kubectl apply -f "$here/argo.yaml"
kubectl apply -f "$here/rbac.yaml"
# The collect command adds each NetBox job's verdicts to this one, and the
# comparison step mounts its job's key. It is made empty once and never
# applied over, which would drop every job's verdicts.
kubectl -n orchestration get configmap netbox-verdicts >/dev/null 2>&1 ||
  kubectl -n orchestration create configmap netbox-verdicts
kubectl apply -f "$here/workflow-template.yaml"
kubectl -n argo rollout status deployment/workflow-controller --timeout=180s
kubectl -n argo get pods -l app=workflow-controller \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.phase} {.status.containerStatuses[0].imageID}{"\n"}{end}'
