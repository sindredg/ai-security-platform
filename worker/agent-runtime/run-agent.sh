#!/usr/bin/env bash
# Runs on the worker, as root. One headless agent run: the task comes in on
# standard input, the run's transcript goes out on standard output as one JSON
# document, and what systemd says about the run goes to standard error.
#
# The agent runs in a transient unit with a throwaway account, a read-only
# file system, no address beyond localhost, and a time limit. Everything it
# writes lands in the unit's private /tmp, which systemd deletes when the unit
# stops. The unit has a fixed name, so a second run cannot start while one
# exists.
#
# The agent gets one tool, the fixture. --no-profile keeps Goose from loading
# any extension of its own, and the developer extension, which runs shell
# commands, is never named.
#
# Usage: run-agent.sh [--max-turns N] [--seconds N] < TASK
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=pins.env
. "$here/pins.env"

turns=6
seconds=900
while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-turns) turns=${2:?} ; shift 2 ;;
    --seconds) seconds=${2:?} ; shift 2 ;;
    *) echo "usage: run-agent.sh [--max-turns N] [--seconds N] < TASK" >&2; exit 2 ;;
  esac
done

exec systemd-run --unit=aisec-agent-job --wait --pipe --collect \
  --property=DynamicUser=yes \
  --property=NoNewPrivileges=yes \
  --property=ProtectSystem=strict \
  --property=ProtectHome=yes \
  --property=PrivateTmp=yes \
  --property=PrivateDevices=yes \
  --property=ProtectKernelTunables=yes \
  --property=ProtectKernelModules=yes \
  --property=ProtectKernelLogs=yes \
  --property=ProtectControlGroups=yes \
  --property=ProtectClock=yes \
  --property=ProtectHostname=yes \
  --property=ProtectProc=invisible \
  --property="RestrictAddressFamilies=AF_INET AF_UNIX" \
  --property=RestrictNamespaces=yes \
  --property=RestrictRealtime=yes \
  --property=RestrictSUIDSGID=yes \
  --property=LockPersonality=yes \
  --property=MemoryDenyWriteExecute=yes \
  --property=SystemCallArchitectures=native \
  --property=SystemCallFilter=@system-service \
  --property=CapabilityBoundingSet= \
  --property=AmbientCapabilities= \
  --property=IPAddressDeny=any \
  --property=IPAddressAllow=localhost \
  --property=UMask=0077 \
  --property=MemoryAccounting=yes \
  --property=MemoryMax=2G \
  --property=RuntimeMaxSec="$seconds" \
  --working-directory=/tmp \
  --setenv=HOME=/tmp \
  --setenv=GOOSE_PATH_ROOT=/tmp/goose \
  --setenv=GOOSE_DISABLE_KEYRING=1 \
  --setenv=GOOSE_TELEMETRY_ENABLED=false \
  --setenv=GOOSE_DISABLE_SESSION_NAMING=true \
  --setenv=GOOSE_MODE=auto \
  --setenv=GOOSE_PROVIDER=openai \
  --setenv=GOOSE_MODEL="$MODEL_ALIAS" \
  --setenv=GOOSE_CONTEXT_LIMIT=8192 \
  --setenv=OPENAI_HOST="$MODEL_URL" \
  --setenv=OPENAI_API_KEY=none \
  "$GOOSE_DIR/goose" run --no-session --no-profile --quiet --output-format json \
  --max-turns "$turns" \
  --with-extension "evidence:/usr/bin/python3 -I $FIXTURE_DIR/evidence_tool.py" \
  --system "$(cat "$FIXTURE_DIR/system.txt")" \
  --instructions -
