#!/usr/bin/env bash
# Runs on the worker, as root. Checks the pushed archive against its pin again,
# unpacks Goose, and installs the fixture with install-fixture.sh. It
# starts nothing: the agent is not a service, it runs once per job.
#
# Usage: install-agent.sh STAGE_DIR
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=$(cd "${1:?usage: install-agent.sh STAGE_DIR}" && pwd)
# shellcheck source=pins.env
. "$here/pins.env"

# The orchestrator checked this file. Check it again here, against the pin
# list from the operator's checkout (ADR 0026), so that a file changed on the
# orchestrator, on the way, or on this disk does not get unpacked as root.
#
# The stage is the feed account's, so the feed key can replace the archive at
# any moment, also between a check and an unpack that each open it by name.
# Root copies it first, into a directory only root can write, refuses anything
# that is not a plain file, and checks and unpacks that copy and nothing else.
sum=$(awk -F '\t' -v path="goose/$GOOSE_ARCHIVE" '$2 == path {print $1}' "$here/artifacts.tsv")
if [[ -z $sum ]]; then
  echo "artifacts.tsv has no line for goose/$GOOSE_ARCHIVE" >&2
  exit 1
fi
work=$(mktemp -d -p "${TMPDIR:-/var/tmp}" aisec-install-agent.XXXXXX)
trap 'rm -rf "$work"' EXIT
cp --no-dereference "$stage/goose/$GOOSE_ARCHIVE" "$work/archive.tar.gz"
if [[ -L $work/archive.tar.gz || ! -f $work/archive.tar.gz ]]; then
  echo "goose/$GOOSE_ARCHIVE in the stage is not a plain file" >&2
  exit 1
fi
echo "$sum  $work/archive.tar.gz" | sha256sum --check --quiet
echo "the archive matches artifacts.tsv"

# The archive holds one file. Take that file and nothing else, whatever else
# a changed archive might carry. It has to be a plain file, and it is checked
# against its own pin before root gives it an owner and a mode.
mkdir "$work/unpacked"
tar -xzf "$work/archive.tar.gz" -C "$work/unpacked" --no-same-owner --no-same-permissions ./goose
if [[ -L $work/unpacked/goose || ! -f $work/unpacked/goose ]]; then
  echo "the archive's goose is not a plain file, refused" >&2
  exit 1
fi
# The binary itself, against the pin read from the archive on the workstation.
# A matching archive with another binary inside is refused here, before it is
# installed, so nothing can run it.
if ! echo "$GOOSE_BINARY_SHA256  $work/unpacked/goose" | sha256sum --check --quiet; then
  echo "the binary does not match GOOSE_BINARY_SHA256 in pins.env, refused" >&2
  exit 1
fi
echo "the binary matches GOOSE_BINARY_SHA256"
install -d -m 0755 -o root -g root "$GOOSE_DIR"
install -m 0755 -o root -g root "$work/unpacked/goose" "$GOOSE_DIR/goose"
(cd "$GOOSE_DIR" && sha256sum goose | tee SHA256SUMS)

"$here/install-fixture.sh"

# Goose is not run here. This script is root, and the first thing to execute
# that binary should be the sandboxed unit in run-agent.sh.
