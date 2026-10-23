#!/usr/bin/env bash
# Runs on the worker, as root. Installs the fixture tool, the fixture check,
# and the two prompt files of the fixture run. install-agent.sh runs it after
# Goose. Run it alone after a change to any of them or to the system text: it
# needs no staged files.
#
# Usage: install-fixture.sh
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=pins.env
. "$here/pins.env"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

install -d -m 0755 -o root -g root "$FIXTURE_DIR"
install -m 0755 -o root -g root "$here/fixture/evidence_tool.py" "$here/fixture/check_answer.py" "$FIXTURE_DIR/"
# The system text is the job's own, one file for both (install-job.sh).
install -m 0644 -o root -g root "$here/system.txt" "$here/fixture/question.txt" "$FIXTURE_DIR/"
(cd "$FIXTURE_DIR" && sha256sum check_answer.py evidence_tool.py question.txt system.txt)
