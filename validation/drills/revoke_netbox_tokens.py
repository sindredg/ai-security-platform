#!/usr/bin/python3 -I
"""Deletes every API token of one NetBox account, with the seeding token
(milestone 6, the incident response runbook).

    revoke_netbox_tokens.py ACCOUNT [--seed-token FILE] [--url URL] [--cert FILE]

Runs as root on the orchestrator when a token has leaked. The seeding token
comes from make-netbox-token.sh seed on the NetBox VM, may write from the
orchestrator's address for an hour, and sits in /etc/aisec/netbox/seed-token
until the NetBox runbook's step 17 removes it. The account keeps its
permissions and gets no new token here: the seed run makes one (the NetBox
runbook, steps 16 and 17).

Prints each token's ID and NetBox's status, then a count. The exit is 1 when
the account was not found or a deletion was refused, 2 when the seeding
token or the arguments cannot be read. Standard library only, beside the
collector's client in /usr/local/lib/aisec.
"""

import os
import sys

sys.path.insert(0, os.environ.get("AISEC_COLLECTOR_DIR", "/usr/local/lib/aisec"))
import netbox_access

URL = "https://10.50.0.4:8443"
CERT = "/etc/aisec/netbox/tls.crt"
SEED_TOKEN = "/etc/aisec/netbox/seed-token"
USERS = "/api/users/users/"
TOKENS = "/api/users/tokens/"


def the_one(netbox, path, what, **query):
    status, found = netbox.list(path, **query)
    if status != 200:
        raise LookupError(f"{what}: {status} {found}")
    if len(found) != 1:
        raise LookupError(f"{what}: {len(found)} found, 1 expected")
    return found[0]


def revoke_tokens(netbox, account):
    """Deletes the account's tokens one by one. Returns the exit code."""
    try:
        user = the_one(netbox, USERS, account, username=account)
        status, tokens = netbox.list(TOKENS, user_id=user["id"])
        if status != 200:
            raise LookupError(f"tokens of {account}: {status} {tokens}")
    except LookupError as error:
        print(f"failed: {error}", file=sys.stderr)
        return 1
    deleted = 0
    for token in tokens:
        status, _ = netbox.call("DELETE", f"{TOKENS}{token['id']}/")
        print(f"deleted token {token['id']} of {account}: {status}")
        deleted += status == 204
    if deleted == len(tokens):
        print(f"== {deleted} tokens of {account} deleted")
        return 0
    print(f"== {deleted} of {len(tokens)} tokens of {account} deleted")
    return 1


def arguments(argv):
    """ACCOUNT and the three options, or None for a usage error."""
    options = {"--seed-token": SEED_TOKEN, "--url": URL, "--cert": CERT}
    rest = argv[1:]
    if not rest or rest[0].startswith("--"):
        return None
    account, rest = rest[0], rest[1:]
    while rest:
        if len(rest) < 2 or rest[0] not in options:
            return None
        options[rest[0]] = rest[1]
        rest = rest[2:]
    return account, options


def main(argv):
    parsed = arguments(argv)
    if parsed is None:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    account, options = parsed
    try:
        with open(options["--seed-token"]) as file:
            token = file.read().strip()
    except OSError as error:
        print(f"failed: {error}", file=sys.stderr)
        return 2
    netbox = netbox_access.NetBox(token, url=options["--url"], cert=options["--cert"])
    return revoke_tokens(netbox, account)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
