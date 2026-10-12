#!/usr/bin/env bash
# Runs on the orchestrator. Downloads every file in artifacts.tsv into a staging
# directory and checks each one against its pinned sha256. Nothing is unpacked,
# imported, or loaded here: the orchestrator hashes these files and never opens
# them.
#
# Usage: fetch.sh STAGE_DIR
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=${1:?usage: fetch.sh STAGE_DIR}
# shellcheck source=pins.env
. "$here/pins.env"

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

# The converter is source, not a release file. Fetch the pinned commit and pack
# the three paths the converter needs. Git names a commit by the hash of its
# content, so the commit ID is the check.
src=$stage/converter-src.git
rm -rf "$src"
git init --quiet "$src"
git -C "$src" fetch --quiet --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_COMMIT"
got=$(git -C "$src" rev-parse FETCH_HEAD)
if [[ $got != "$LLAMA_COMMIT" ]]; then
  echo "converter commit is $got, expected $LLAMA_COMMIT" >&2
  exit 1
fi
git -C "$src" archive --format=tar --prefix=converter/ "$LLAMA_COMMIT" \
  convert_hf_to_gguf.py conversion gguf-py LICENSE > "$stage/converter-src.tar"
rm -rf "$src"
echo "ok    converter-src.tar (commit $LLAMA_COMMIT)"
