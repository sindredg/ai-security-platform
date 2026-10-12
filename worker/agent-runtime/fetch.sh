#!/usr/bin/env bash
# Runs on the orchestrator. Downloads every file in artifacts.tsv into a staging
# directory and checks each one against its pinned sha256. Nothing is unpacked
# or run here: the orchestrator hashes these files and never opens them.
#
# Usage: fetch.sh STAGE_DIR
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=${1:?usage: fetch.sh STAGE_DIR}

mkdir -p "$stage"

while IFS=$'\t' read -r sum path url; do
  [[ -z $sum || $sum == \#* ]] && continue
  dest=$stage/$path
  mkdir -p "$(dirname "$dest")"
  if [[ -f $dest ]] && echo "$sum  $dest" | sha256sum --check --status; then
    echo "have  $path"
    continue
  fi
  curl --fail --silent --show-error --location --proto '=https' --retry 3 \
    --continue-at - --output "$dest.part" "$url"
  if ! echo "$sum  $dest.part" | sha256sum --check --status; then
    echo "checksum mismatch, removed: $path" >&2
    rm -f "$dest.part"
    exit 1
  fi
  mv "$dest.part" "$dest"
  echo "ok    $path"
done < "$here/artifacts.tsv"
