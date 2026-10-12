#!/usr/bin/env bash
# Runs on the worker, as root. Checks the pushed files against artifacts.tsv
# again, unpacks the llama.cpp binaries, and builds the model file in a
# sandboxed transient unit.
#
# Usage: build-model.sh STAGE_DIR
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=$(cd "${1:?usage: build-model.sh STAGE_DIR}" && pwd)
# shellcheck source=pins.env
. "$here/pins.env"

echo "== verify the pushed files"
awk -F'\t' '!/^#/ && NF { print $1 "  " $2 }' "$here/artifacts.tsv" |
  (cd "$stage" && sha256sum --check --quiet)
echo "all files match artifacts.tsv"

echo "== llama.cpp $LLAMA_BUILD"
# The binaries link the OpenMP runtime, which the server image does not carry.
# It comes through the package proxy like every other package.
if ! ldconfig -p | grep -q 'libgomp\.so\.1'; then
  apt-get install -y -q -o DPkg::Lock::Timeout=120 libgomp1
fi
install -d -m 0755 "$(dirname "$LLAMA_DIR")" "$MODEL_DIR"
tar -xzf "$stage/llama/llama-$LLAMA_BUILD-bin-ubuntu-arm64.tar.gz" \
  -C "$(dirname "$LLAMA_DIR")" --no-same-owner --no-same-permissions
"$LLAMA_DIR/llama-server" --version

echo "== build the model file"
# The converter and its packages are the least trusted code in this build, so
# they get no network, no view of /home, an account of their own, and one
# directory to write in. The account is a real one: with DynamicUser the state
# directory cannot hold shared libraries, and PyTorch fails to load.
id -u aisec-build > /dev/null 2>&1 ||
  useradd --system --no-create-home --shell /usr/sbin/nologin aisec-build
systemd-run --unit=aisec-model-build --wait --collect --pipe --quiet \
  -p User=aisec-build \
  -p StateDirectory=aisec-model-build \
  -p PrivateNetwork=yes \
  -p ProtectSystem=strict \
  -p ProtectHome=tmpfs \
  -p PrivateDevices=yes \
  -p PrivateTmp=yes \
  -p NoNewPrivileges=yes \
  -p BindReadOnlyPaths="$stage:/run/aisec-model-stage" \
  -p BindReadOnlyPaths="$here:/run/aisec-model-scripts" \
  -p MemoryAccounting=yes \
  -p RuntimeMaxSec=7200 \
  /bin/bash /run/aisec-model-scripts/convert.sh

echo "== install"
built=/var/lib/aisec-model-build/$MODEL_NAME-$MODEL_QUANT.gguf
install -m 0644 -o root -g root "$built" "$MODEL_FILE"
rm -rf /var/lib/aisec-model-build
userdel aisec-build
(cd "$MODEL_DIR" && sha256sum "$(basename "$MODEL_FILE")" | tee SHA256SUMS)
ls -l "$MODEL_FILE"
