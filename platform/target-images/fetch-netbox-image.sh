#!/usr/bin/env bash
# Runs on the orchestrator, as root, during a fetch window (ADR 0035). Pulls
# the NetBox image by the digest of its image index, for linux/amd64, and
# exports it as one archive for the NetBox VM to load.
#
# The pull goes into a containerd namespace of its own. The kubelet reads only
# k8s.io, so no pod can start the image. containerd goes through the edge on
# its own (U.11), and the variable covers a pull made by ctr itself.
#
# The archive is checked against the pins in image.env before it is kept: it
# holds the pinned index or manifest, the linux/amd64 manifest hashes to its
# pin, that manifest names the pinned config, and every blob it names is in
# the archive and hashes to its digest. The config's digest is the image ID
# the NetBox VM compares with after its load. The image is then removed from
# the namespace.
#
# Usage: fetch-netbox-image.sh IMAGE_ENV ARCHIVE
set -euo pipefail

pins=${1:?usage: fetch-netbox-image.sh IMAGE_ENV ARCHIVE}
archive=${2:?usage: fetch-netbox-image.sh IMAGE_ENV ARCHIVE}
# shellcheck source=/dev/null # image.env is in the targets repository
. "$pins"
namespace=aisec-targets
ref="$NETBOX_IMAGE@$NETBOX_INDEX_DIGEST"
ctr() { k3s ctr --namespace "$namespace" "$@"; }

HTTPS_PROXY=http://10.45.0.4:3128 ctr images pull --platform linux/amd64 "$ref" > /dev/null
pulled=$(ctr images ls | awk -v r="$ref" '$1 == r {print $3}')
if [ "$pulled" != "$NETBOX_INDEX_DIGEST" ]; then
  echo "containerd holds ${pulled:-nothing} for $ref, not $NETBOX_INDEX_DIGEST" >&2
  exit 1
fi
echo "ok    pulled $ref"

mkdir -p "$(dirname "$archive")"
ctr images export --platform linux/amd64 "$archive.part" "$ref"
ctr images rm --sync "$ref" > /dev/null

if ! python3 -I - "$archive.part" "$NETBOX_INDEX_DIGEST" "$NETBOX_MANIFEST_DIGEST" "$NETBOX_IMAGE_ID" << 'EOF'
import hashlib
import json
import sys
import tarfile

path, index_digest, manifest_digest, config_digest = sys.argv[1:]


def blob(archive, digest):
    data = archive.extractfile("blobs/sha256/" + digest.removeprefix("sha256:")).read()
    if "sha256:" + hashlib.sha256(data).hexdigest() != digest:
        sys.exit(f"blob {digest} does not hash to its digest")
    return data


with tarfile.open(path) as archive:
    roots = {d["digest"] for d in json.load(archive.extractfile("index.json"))["manifests"]}
    if index_digest in roots:
        index = json.loads(blob(archive, index_digest))
        listed = {
            m["digest"]
            for m in index["manifests"]
            if m.get("platform", {}).get("os") == "linux" and m["platform"].get("architecture") == "amd64"
        }
        if listed != {manifest_digest}:
            sys.exit(f"the index lists {sorted(listed)} for linux/amd64, not {manifest_digest}")
    elif manifest_digest not in roots:
        sys.exit(f"the archive's index names {sorted(roots)}, neither pin")
    manifest = json.loads(blob(archive, manifest_digest))
    if manifest["config"]["digest"] != config_digest:
        sys.exit(f"the manifest names config {manifest['config']['digest']}, not {config_digest}")
    blob(archive, config_digest)
    for layer in manifest["layers"]:
        blob(archive, layer["digest"])
    print(f"ok    archive: {len(manifest['layers'])} layers, config {config_digest}")
EOF
then
  rm -f "$archive.part"
  echo "the archive does not match image.env, removed" >&2
  exit 1
fi
chmod 644 "$archive.part"
mv "$archive.part" "$archive"
sha256sum "$archive"
