#!/usr/bin/env bash
# Fails unless every commit in BASE..HEAD carries an SSH signature by a key in
# the allowed signers file. A commit signed by GitHub, by another key, or not
# at all fails. ADR 0024.
#
# Usage: check-signatures.sh ALLOWED_SIGNERS BASE HEAD
#
# The caller passes an allowed signers file read from the base branch, not the
# pull request's copy, so a pull request cannot add its own key.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 ALLOWED_SIGNERS BASE HEAD" >&2
  exit 2
fi
signers=$1
base=$2
head=$3

# An empty or unreadable file would make every signature "unknown key".
grep -Eq '^[^#[:space:]]+ +namespaces="git" +ssh-' "${signers}"

# rev-list fails on a commit that is not in the clone, so a short fetch fails
# here and does not pass as an empty range.
mapfile -t commits < <(git rev-list --reverse "${base}..${head}")
git rev-list --quiet "${base}..${head}"
if [ "${#commits[@]}" -eq 0 ]; then
  echo "No commits in ${base}..${head}" >&2
  exit 1
fi

# "fully" is the trust level Git gives a key the file names. A good signature
# by a key the file does not name scores "undefined". Git 2.43 refuses that
# without the setting. The setting keeps it refused if a release scores it
# differently.
gitv=(git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile="${signers}"
  -c gpg.minTrustLevel=fully)
failed=0
for commit in "${commits[@]}"; do
  if "${gitv[@]}" verify-commit "${commit}" 2>/dev/null; then
    echo "ok      ${commit}"
  else
    echo "FAILED  ${commit}  $("${gitv[@]}" log -1 --format='%G? %s' "${commit}")"
    failed=1
  fi
done
exit "${failed}"
