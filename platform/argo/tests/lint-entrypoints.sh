#!/usr/bin/env bash
# Which entrypoints a workflow from the investigate template can name (#203,
# ADR 0048). A workflow that references the template may set its own
# entrypoint, also under templateReferencing: Secure. Argo's linter checks
# each workflow in this directory against the template, offline, with the
# validation the controller runs at submission: investigate has to pass, and
# dispatch and compare, the template's inline steps, have to fail as
# templates Argo cannot find.
#
#   platform/argo/tests/lint-entrypoints.sh ARGO [ARG...]
#
# ARGO and its arguments run Argo's command line from the repository's root:
# a local binary, or docker run with the image, as the pipeline does.
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: $0 ARGO [ARG...]" >&2
  exit 2
fi
argo=("$@")
template=platform/argo/workflow-template.yaml
fixtures=platform/argo/tests

lint() {
  "${argo[@]}" lint --offline --no-color --kinds=workflows,workflowtemplates \
    "$template" "$fixtures/entrypoint-$1.yaml" 2>&1
}

if ! out=$(lint investigate); then
  echo "$out"
  echo "investigate: refused, and it is how the operator submits a job" >&2
  exit 1
fi
echo "investigate: passes"

for entrypoint in dispatch compare; do
  if out=$(lint "$entrypoint"); then
    echo "$out"
    echo "$entrypoint: passes, so a workflow can run it alone" >&2
    exit 1
  fi
  # Any other failure, such as a fixture Argo cannot read, proves nothing.
  if ! grep -qF "template reference investigate.$entrypoint not found" <<<"$out"; then
    echo "$out"
    echo "$entrypoint: refused, but not as a template Argo cannot find" >&2
    exit 1
  fi
  echo "$entrypoint: refused, no such template"
done
