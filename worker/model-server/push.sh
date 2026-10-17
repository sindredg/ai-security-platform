#!/usr/bin/env bash
# Runs on the orchestrator. Copies the staged files to the worker over SSH with
# the feed key, which can only unpack them into the feed account's directory
# (ADR 0026). The scripts and the pin list reach the worker from the operator's
# checkout, not from here.
#
# Usage: push.sh STAGE_DIR [WORKER]
set -euo pipefail

stage=${1:?usage: push.sh STAGE_DIR [WORKER]}
worker=${2:-aisec-feed@aisec-worker}
key=${AISEC_FEED_KEY:-$HOME/.ssh/aisec-feed}

tar -C "$stage" -cf - . | ssh -i "$key" "$worker" receive model-server
ssh -i "$key" "$worker" size model-server
