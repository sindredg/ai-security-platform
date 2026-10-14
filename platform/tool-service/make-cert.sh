#!/usr/bin/env bash
# Runs on the orchestrator, as root. Makes the tool service's one certificate:
# self-signed, not an authority, P-256, 90 days (ADR 0016). The key never
# leaves this machine. The certificate goes to the worker, which trusts it and
# nothing else.
#
# Refuses to replace a certificate that exists, unless told to rotate.
#
# Usage: make-cert.sh [--rotate]
set -euo pipefail

dir=/etc/aisec/tool-service
names="DNS:tool-service.aisec.internal,DNS:tool-service.tool-services.svc,DNS:tool-service.tool-services.svc.cluster.local"

if [ -e "$dir/tls.crt" ] && [ "${1:-}" != --rotate ]; then
  echo "$dir/tls.crt exists. Pass --rotate to replace it." >&2
  exit 1
fi

install -d -m 700 "$dir"
umask 077
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
  -keyout "$dir/tls.key.new" -out "$dir/tls.crt.new" -days 90 \
  -subj "/CN=tool-service.aisec.internal" \
  -addext "subjectAltName=$names" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature" \
  -addext "extendedKeyUsage=serverAuth" 2>/dev/null
mv "$dir/tls.key.new" "$dir/tls.key"
mv "$dir/tls.crt.new" "$dir/tls.crt"
chmod 600 "$dir/tls.key"
chmod 644 "$dir/tls.crt"

openssl x509 -in "$dir/tls.crt" -noout -subject -enddate -ext subjectAltName,basicConstraints
openssl x509 -in "$dir/tls.crt" -noout -fingerprint -sha256
