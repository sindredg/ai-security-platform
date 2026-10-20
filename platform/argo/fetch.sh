#!/usr/bin/env bash
# Runs on the orchestrator, during a fetch window. Downloads Argo's namespace
# install into a staging directory and checks it against its pin, then pulls
# every image the manifests name, by digest, so that pods start later with no
# window open. containerd goes through the edge on its own. Nothing is
# applied here.
#
# Usage: fetch.sh STAGE_DIR
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=${1:?usage: fetch.sh STAGE_DIR}
# shellcheck source=pins.env
. "$here/pins.env"

mkdir -p "$stage"
file=$stage/namespace-install.yaml
if [[ -f $file ]] && echo "$ARGO_INSTALL_SHA256  $file" | sha256sum --check --status; then
  echo "have  namespace-install.yaml"
else
  curl --fail --silent --show-error --location --proto '=https' --retry 3 \
    --output "$file.part" "$ARGO_INSTALL_URL"
  if ! echo "$ARGO_INSTALL_SHA256  $file.part" | sha256sum --check --status; then
    echo "namespace-install.yaml does not match ARGO_INSTALL_SHA256, removed" >&2
    rm -f "$file.part"
    exit 1
  fi
  mv "$file.part" "$file"
  echo "ok    namespace-install.yaml ($ARGO_VERSION)"
fi

# Every image reference with a digest in the manifests: the controller, the
# executor, and the dispatch image. A placeholder of zeros is not an image.
mapfile -t images < <(grep -hoE '[a-z0-9./-]+@sha256:[0-9a-f]{64}' "$here"/*.yaml | grep -v '@sha256:0\{64\}$' | sort -u)
[[ ${#images[@]} -gt 0 ]] || { echo "no pinned image in the manifests" >&2; exit 1; }
for image in "${images[@]}"; do
  sudo k3s crictl pull "$image" > /dev/null
  echo "ok    $image"
done
