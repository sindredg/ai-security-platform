#!/usr/bin/env bash
# Runs on the orchestrator, as root. Starts one short-lived pod in the
# orchestration namespace, as the dispatch account, that registers or revokes
# a job with the tool service and prints the answer. The pod runs the tool
# service's own image, which has Python, and is removed when it exits.
#
# The arguments and the client go in on standard input, not in the pod's spec.
#
# Usage: register.sh register JOB TOKEN_SHA256 [TOKEN_OVERRIDE|-] [SECONDS] [TARGET]
#        register.sh revoke JOB [- TOKEN_OVERRIDE]
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
image=$(sed -n 's/^ *image: \(ghcr.io[^ ]*\)$/\1/p' "$here/tool-service.yaml")
name=register-$(date +%s)
overrides=$(python3 - "$name" "$image" <<'PY'
import json, sys
name, image = sys.argv[1:]
print(json.dumps({"spec": {
    "serviceAccountName": "dispatch",
    "automountServiceAccountToken": False,
    "securityContext": {"runAsNonRoot": True, "runAsUser": 65532,
                        "seccompProfile": {"type": "RuntimeDefault"}},
    "containers": [{
        "name": name, "image": image, "stdin": True, "stdinOnce": True,
        "command": ["python", "-c", "import sys; exec(sys.stdin.read())"],
        "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                            "capabilities": {"drop": ["ALL"]}},
        "volumeMounts": [{"name": "token", "mountPath": "/var/run/secrets/aisec", "readOnly": True},
                         {"name": "cert", "mountPath": "/etc/aisec", "readOnly": True}],
    }],
    "volumes": [
        {"name": "token", "projected": {"sources": [{"serviceAccountToken": {
            "audience": "aisec-tool-service", "expirationSeconds": 600, "path": "token"}}]}},
        {"name": "cert", "configMap": {"name": "tool-service-cert"}},
    ],
}}))
PY
)

# The client source, then a line that the client reads as its arguments.
{
  printf 'import sys\nsys.stdin = __import__("io").StringIO(%s)\n' "$(python3 -c 'import json,sys; print(json.dumps(" ".join(sys.argv[1:]) + "\n"))' "$@")"
  cat "$here/register.py"
} | k3s kubectl run "$name" -n orchestration -i --rm --quiet --restart=Never \
  --labels=app.kubernetes.io/name=dispatch --image="$image" --overrides="$overrides"
