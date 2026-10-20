#!/usr/bin/env bash
# Runs on the orchestrator, as root. Makes the dispatch key pair and puts it,
# with the worker's host key, into the dispatch-ssh secret in orchestration
# (ADR 0012, ADR 0030). The private half is written to a memory-backed
# directory, put into the secret, and removed. The public half is printed, for
# install-job.sh on the worker. An existing secret is replaced: that is the
# rotation.
#
# The host key comes from the operator, read over the operator's own session
# to the worker, not from the network here:
#
#   make-dispatch-key.sh "ssh-ed25519 AAAA..."
set -euo pipefail

host_key=${1:?usage: make-dispatch-key.sh "ssh-ed25519 AAAA..." (the worker host key)}
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
if ! [[ $host_key =~ ^ssh-ed25519\ [A-Za-z0-9+/]+={0,2}(\ .*)?$ ]]; then
  echo "not an ed25519 host key" >&2
  exit 1
fi

dir=$(mktemp -d -p /dev/shm aisec-dispatch.XXXXXX)
trap 'rm -rf "$dir"' EXIT
ssh-keygen -q -t ed25519 -N '' -C aisec-dispatch -f "$dir/id_ed25519"
printf '10.40.0.36 %s\n' "$(cut -d ' ' -f 1,2 <<< "$host_key")" > "$dir/known_hosts"
k3s kubectl -n orchestration create secret generic dispatch-ssh \
  --from-file=id_ed25519="$dir/id_ed25519" --from-file=known_hosts="$dir/known_hosts" \
  --dry-run=client -o yaml | k3s kubectl apply -f - > /dev/null
cat "$dir/id_ed25519.pub"
