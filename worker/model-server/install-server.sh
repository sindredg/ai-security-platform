#!/usr/bin/env bash
# Runs on the worker, as root, after build-model.sh. Installs the unit, starts
# the server, and waits until it answers.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=pins.env
. "$here/pins.env"

(cd "$MODEL_DIR" && sha256sum --check --quiet SHA256SUMS)

sed -e "s|@LLAMA_DIR@|$LLAMA_DIR|g" -e "s|@MODEL_FILE@|$MODEL_FILE|g" \
  "$here/aisec-llama-server.service" > /etc/systemd/system/aisec-llama-server.service
chmod 0644 /etc/systemd/system/aisec-llama-server.service
systemctl daemon-reload
systemctl enable --quiet aisec-llama-server.service
systemctl restart aisec-llama-server.service

for _ in $(seq 1 120); do
  if curl --silent --fail --max-time 2 http://127.0.0.1:8080/health > /dev/null; then
    systemctl --no-pager --lines=0 status aisec-llama-server.service
    exit 0
  fi
  sleep 1
done
echo "the server did not answer on 127.0.0.1:8080 within 120 s" >&2
journalctl --no-pager -n 30 -u aisec-llama-server.service >&2
exit 1
