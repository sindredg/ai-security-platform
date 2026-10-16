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

# artifacts.tsv comes from the operator's checkout, and the files it lists from
# the orchestrator (ADR 0026). This check catches a transfer that damaged or
# dropped a file, and an orchestrator that changed one. The converter takes a
# whole directory of wheels and a pattern for pip, so a file the list does not
# name is refused too, and so is anything that is not a plain file. The
# converter's source is packed on the orchestrator, so its pin is in pins.env.
echo "== verify the pushed files"
{
  awk -F'\t' '!/^#/ && NF { print $1 "  " $2 }' "$here/artifacts.tsv"
  echo "$CONVERTER_SRC_SHA256  converter-src.tar"
} | (cd "$stage" && sha256sum --check --quiet)
extra=$(comm -13 <({ awk -F'\t' '!/^#/ && NF { print $2 }' "$here/artifacts.tsv"; echo converter-src.tar; } | sort) \
  <(cd "$stage" && find . -mindepth 1 ! -type d | sed 's|^\./||' | sort))
if [[ -n $extra ]]; then
  printf 'not in artifacts.tsv:\n%s\n' "$extra" >&2
  exit 1
fi
echo "all files match artifacts.tsv and pins.env, and nothing else is staged"

echo "== llama.cpp $LLAMA_BUILD"
# The binaries link the OpenMP runtime, which the server image does not carry.
# It comes through the package proxy like every other package.
#
# The version is not pinned. The archive keeps only the current version of a
# package, so a pin to the one this was built with fails as soon as a security
# update replaces it, and a rebuilt worker could not build. apt checks the
# package against the archive's signed metadata, which is the same trust every
# other package on the machine gets. The version is printed so the build log
# records which one was used.
if ! ldconfig -p | grep -q 'libgomp\.so\.1'; then
  apt-get install -y -q -o DPkg::Lock::Timeout=120 libgomp1
fi
dpkg-query -W -f 'libgomp1 ${Version}\n' libgomp1
install -d -m 0755 "$(dirname "$LLAMA_DIR")" "$MODEL_DIR"
tar -xzf "$stage/llama/llama-$LLAMA_BUILD-bin-ubuntu-arm64.tar.gz" \
  -C "$(dirname "$LLAMA_DIR")" --no-same-owner --no-same-permissions
"$LLAMA_DIR/llama-server" --version

echo "== build the model file"
# The converter and its packages are the least trusted code in this build, so
# they get no network, no view of /home, an account of their own, and one
# directory to write in. The account is a real one: with DynamicUser the state
# directory cannot hold shared libraries, and PyTorch fails to load.
#
# The account and the directory go away however the build ends. A failed build
# would otherwise leave 8 GB of intermediate files, written by the converter,
# and an account nothing else uses. The unit is stopped first: an interrupted
# script leaves it running, and an account with live processes is not removed.
cleanup() {
  systemctl stop aisec-model-build.service 2> /dev/null || true
  rm -rf /var/lib/aisec-model-build
  if id -u aisec-build > /dev/null 2>&1; then
    userdel aisec-build || echo "could not remove the aisec-build account" >&2
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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
(cd "$MODEL_DIR" && sha256sum "$(basename "$MODEL_FILE")" | tee SHA256SUMS)
ls -l "$MODEL_FILE"
