#!/usr/bin/env bash
# Runs on the worker, as root, after build-model.sh. Installs the unit, starts
# the server, and waits until it answers. AISEC_MODEL picks the model, as in
# pins.env, so a comparison can run another model and then go back.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=pins.env
. "$here/pins.env"

# The line the build wrote for this file. No line is a failure, not a pass.
(cd "$MODEL_DIR" && awk -v name="$(basename "$MODEL_FILE")" '$2 == name' SHA256SUMS | sha256sum --check --strict)

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
