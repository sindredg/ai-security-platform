#!/usr/bin/env bash
# Runs on the worker, inside the sandbox that build-model.sh starts: no network,
# a throwaway account, and one writable directory. Installs the converter's
# packages there, converts the publisher's weights to GGUF, and quantizes.
set -euo pipefail

: "${STATE_DIRECTORY:?run through build-model.sh}"
stage=/run/aisec-model-stage
scripts=/run/aisec-model-scripts
# shellcheck source=pins.env
. "$scripts/pins.env"

work=$STATE_DIRECTORY
# pip unpacks into the temporary directory first. Keep that on the same disk.
mkdir -p "$work/tmp"
export HOME=$work TMPDIR=$work/tmp PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1

echo "== converter packages"
pip_wheel=$(echo "$stage"/pip/pip-*.whl)
python3 "$pip_wheel/pip" install --quiet --no-index --no-deps \
  --only-binary=:all: --find-links "$stage/wheels" --target "$work/site" \
  -r "$scripts/converter-requirements.txt"
tar -xf "$stage/converter-src.tar" -C "$work"

echo "== convert to GGUF, 16-bit float"
PYTHONPATH=$work/site:$work/converter/gguf-py \
  python3 "$work/converter/convert_hf_to_gguf.py" "$stage/qwen" \
  --outtype f16 --outfile "$work/$MODEL_NAME-F16.gguf"

echo "== quantize to $MODEL_QUANT"
"$LLAMA_DIR/llama-quantize" "$work/$MODEL_NAME-F16.gguf" \
  "$work/$MODEL_NAME-$MODEL_QUANT.gguf" "$MODEL_QUANT" "$(nproc)"

rm -f "$work/$MODEL_NAME-F16.gguf"
ls -l "$work/$MODEL_NAME-$MODEL_QUANT.gguf"
