#!/usr/bin/env bash
# Runs on the orchestrator. Copies this directory and the staged files to the
# worker over SSH with the feed key.
#
# Usage: push.sh STAGE_DIR [WORKER]
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=${1:?usage: push.sh STAGE_DIR [WORKER]}
worker=${2:-aisec@aisec-worker}
key=${AISEC_FEED_KEY:-$HOME/.ssh/aisec-feed}

ssh -i "$key" "$worker" 'mkdir -p feed/model-server/scripts feed/model-server/stage'
tar -C "$here" -cf - . | ssh -i "$key" "$worker" 'tar -C feed/model-server/scripts -xf -'
tar -C "$stage" -cf - . | ssh -i "$key" "$worker" 'tar -C feed/model-server/stage -xf -'
ssh -i "$key" "$worker" 'du -sh feed/model-server/stage'
