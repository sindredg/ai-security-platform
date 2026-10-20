#!/usr/bin/env bash
# Runs on the orchestrator. Copies the staged files to the worker over SSH with
# the feed key, which can only unpack them into the feed account's directory
# (ADR 0026). The scripts and the pin list reach the worker from the operator's
# checkout, not from here.
#
# Only the files one build needs go: the ones in artifacts.tsv, the model's list
# in models/, and the converter's source. The stage here can hold more than one
# model, and the build refuses a file its lists do not name. AISEC_MODEL picks
# the model, as in pins.env.
#
# Usage: push.sh STAGE_DIR [WORKER]
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=${1:?usage: push.sh STAGE_DIR [WORKER]}
worker=${2:-aisec-feed@aisec-worker}
key=${AISEC_FEED_KEY:-$HOME/.ssh/aisec-feed}
# shellcheck source=pins.env
. "$here/pins.env"
models=$here/models/$MODEL_NAME.tsv
if [[ ! -f $models ]]; then
  echo "no list for $MODEL_NAME in models/" >&2
  exit 1
fi

{
  awk -F'\t' '!/^#/ && NF { print $2 }' "$here/artifacts.tsv" "$models"
  echo converter-src.tar
} | tar -C "$stage" -cf - --verbatim-files-from --files-from=- |
  ssh -i "$key" "$worker" receive model-server
ssh -i "$key" "$worker" size model-server
