#!/usr/bin/env bash
# Runs on the worker, as root. Checks the pushed archive against its pin again,
# unpacks Goose, and installs the fixture tool and its two prompt files. It
# starts nothing: the agent is not a service, it runs once per job.
#
# Usage: install-agent.sh STAGE_DIR
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=$(cd "${1:?usage: install-agent.sh STAGE_DIR}" && pwd)
# shellcheck source=pins.env
. "$here/pins.env"

# The orchestrator checked this file. Check it again here, so that a file
# changed on the way or on this disk does not get unpacked as root.
sum=$(awk -F '\t' -v path="goose/$GOOSE_ARCHIVE" '$2 == path {print $1}' "$here/artifacts.tsv")
if [[ -z $sum ]]; then
  echo "artifacts.tsv has no line for goose/$GOOSE_ARCHIVE" >&2
  exit 1
fi
echo "$sum  $stage/goose/$GOOSE_ARCHIVE" | sha256sum --check --quiet
echo "the archive matches artifacts.tsv"

# The archive holds one file. Take that file and nothing else, whatever else
# a changed archive might carry.
install -d -m 0755 -o root -g root "$GOOSE_DIR" "$FIXTURE_DIR"
tar -xzf "$stage/goose/$GOOSE_ARCHIVE" -C "$GOOSE_DIR" --no-same-owner --no-same-permissions ./goose
chown root:root "$GOOSE_DIR/goose"
chmod 0755 "$GOOSE_DIR/goose"
(cd "$GOOSE_DIR" && sha256sum goose | tee SHA256SUMS)

install -m 0755 -o root -g root "$here/fixture/evidence_tool.py" "$here/fixture/check_answer.py" "$FIXTURE_DIR/"
install -m 0644 -o root -g root "$here/fixture/system.txt" "$here/fixture/question.txt" "$FIXTURE_DIR/"

# Goose is not run here. This script is root, and the first thing to execute
# that binary should be the sandboxed unit in run-agent.sh.
