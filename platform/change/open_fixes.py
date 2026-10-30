#!/usr/bin/python3 -I
"""Refuses to publish a fix that an open pull request holds already (ADR 0053).

    gh api 'repos/OWNER/REPO/pulls?state=open' | open_fixes.py PROPOSAL

Runs on the operator's machine before the pull request is opened, with the
bundle's proposal.json and the targets repository's open pull requests, as
the GitHub API lists them, on standard input. Each body is read for the rows
the propose command writes, one per account with `remove NAME (ID N)`, and a
row naming an account and permission ID of this bundle's changes is the same
fix. Nothing is fetched here, and nothing in a body is trusted beyond that
pattern.

Exits 0 when no open pull request holds this fix, 1 when one does, and 2 for
a call without the proposal or without a JSON list on standard input.
Standard library only.
"""

import json
import re
import sys
from pathlib import Path

ROW = re.compile(
    r"^\| `([a-z0-9][a-z0-9._-]{0,63})` \|[^|\n]*\|[^|\n]*\| remove `[^`\n]+` "
    r"\(ID ([0-9]+)\) \|$",
    re.MULTILINE,
)


def duplicates(changes, pulls):
    """Each open pull request's row that removes an account from a permission
    the changes remove it from too: number, branch, account, permission ID."""
    wanted = {(c["account"], int(c["permission_id"])) for c in changes}
    found = []
    for pull in pulls:
        for account, permission in ROW.findall(pull.get("body") or ""):
            if (account, int(permission)) in wanted:
                found.append(
                    (pull["number"], pull["head"]["ref"], account, int(permission))
                )
    return found


def main(argv, stdin=None):
    if len(argv) != 2:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    changes = json.loads(Path(argv[1]).read_text())["policy"]["changes"]
    pulls = json.load(sys.stdin if stdin is None else stdin)
    if not isinstance(pulls, list):
        print("standard input is not a list of pull requests", file=sys.stderr)
        return 2
    found = duplicates(changes, pulls)
    print(f"{len(pulls)} open pull request{'' if len(pulls) == 1 else 's'} read")
    for number, ref, account, permission in found:
        print(
            f"#{number} {ref}: `{account}` loses permission {permission} there already"
        )
    if found:
        return 1
    print("no open pull request with this fix")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
