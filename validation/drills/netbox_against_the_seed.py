#!/usr/bin/python3 -I
"""Compares a NetBox with the seed in the targets repository (milestone 6,
the incident response runbook).

    netbox_against_the_seed.py SEED [--token FILE] [--url URL] [--cert FILE]

Runs as root on the orchestrator with the collector's token, which views the
inventory, the accounts, and the permissions and nothing else. For each group
of objects in the seed it lists the group's endpoint and compares what NetBox
holds with the seed: the objects by the group's key, and every field of each
as the seed's own run judges them before it leaves an object alone. A
permission's users are compared by name. The seeding and probe accounts,
which make-netbox-token.sh makes and the seed does not hold, are not extras.

The token's own access is part of what the seed says: a group the collector's
permission in the seed grants has to answer 200, and one it does not grant
403. Either the other way is a difference. The last line counts the groups
compared and the differences. The exit is 1 on any difference, and 2 when
the seed, the token, or the arguments cannot be read.

The defaults are the live NetBox's address, certificate, and collector token
on the orchestrator; the copy's are given with the three options. Standard
library only, beside the collector's client in /usr/local/lib/aisec.
"""

import json
import os
import sys

sys.path.insert(0, os.environ.get("AISEC_COLLECTOR_DIR", "/usr/local/lib/aisec"))
import netbox_access

URL = "https://10.50.0.4:8443"
CERT = "/etc/aisec/netbox/tls.crt"
TOKEN = "/etc/aisec/netbox/tokens/aisec-collector"
COLLECTOR = "aisec-collector"
USERS = "/api/users/users/"
PERMISSIONS = "/api/users/permissions/"
# The accounts the token script makes on the NetBox VM (ADR 0037, ADR 0039).
PLATFORM_ACCOUNTS = ("aisec-seed", "aisec-address-probe")
# NetBox's endpoint for each object type a permission in the seed may name.
ENDPOINTS = {
    "tenancy.tenant": "/api/tenancy/tenants/",
    "dcim.site": "/api/dcim/sites/",
    "dcim.manufacturer": "/api/dcim/manufacturers/",
    "dcim.devicetype": "/api/dcim/device-types/",
    "dcim.devicerole": "/api/dcim/device-roles/",
    "dcim.device": "/api/dcim/devices/",
    "ipam.ipaddress": "/api/ipam/ip-addresses/",
    "users.user": USERS,
    "users.group": "/api/users/groups/",
    "users.objectpermission": PERMISSIONS,
}


class Unreadable(Exception):
    pass


def granted(seed):
    """The endpoints the collector's enabled permissions in the seed view."""
    paths = set()
    for group in seed.get("objects", []):
        if group["path"] != PERMISSIONS:
            continue
        for item in group["items"]:
            if COLLECTOR not in item.get("users", []) or not item.get("enabled"):
                continue
            if "view" not in item.get("actions", []):
                continue
            for object_type in item["object_types"]:
                if object_type not in ENDPOINTS:
                    raise Unreadable(f"no endpoint known for {object_type}")
                paths.add(ENDPOINTS[object_type])
    if not paths:
        raise Unreadable(f"the seed grants {COLLECTOR} nothing")
    return paths


def matches(want, have, field):
    """Whether NetBox's value for a field is the seed's: users by name, a
    related object by the attributes the seed names, a choice by its value,
    a list regardless of order, constraints and the rest as they are."""
    if field == "users":
        if not isinstance(have, list):
            return False
        names = [u.get("username") for u in have if isinstance(u, dict)]
        return sorted(want) == sorted(str(n) for n in names)
    if field == "constraints":
        return want == have
    if isinstance(want, dict):
        return isinstance(have, dict) and all(have.get(k) == v for k, v in want.items())
    if isinstance(have, dict):
        return want == have.get("value")
    if isinstance(want, list):
        return isinstance(have, list) and sorted(want) == sorted(have)
    return want == have


def differences(group, records):
    """The differences between a seed group and the records NetBox answered,
    as short lines, and the extras that are the platform's own accounts."""
    key = group["key"]
    want = {str(item[key]): item for item in group["items"]}
    have = {}
    for record in records:
        have.setdefault(str(record.get(key)), record)
    lines, beside = [], []
    if len(have) != len(records):
        lines.append(f"{len(records)} records for {len(have)} keys")
    for name in sorted(set(want) - set(have)):
        lines.append(f"no {name}")
    for name in sorted(set(have) - set(want)):
        if group["path"] == USERS and name in PLATFORM_ACCOUNTS:
            beside.append(name)
        else:
            lines.append(f"extra {name}")
    for name in sorted(set(want) & set(have)):
        differ = [
            f for f, v in want[name].items() if not matches(v, have[name].get(f), f)
        ]
        if differ:
            lines.append(f"{name} differs in {', '.join(differ)}")
    return lines, beside


def compare(seed, netbox, out=print):
    """Every group of the seed against NetBox. Returns the number of groups
    compared and the number of differences."""
    allowed = granted(seed)
    compared = found = 0
    for group in seed["objects"]:
        path, want = group["path"], len(group["items"])
        status, answer = netbox.list(path)
        head = f"{path:<28} seed {want:>2}  netbox"
        if status == 200 and path in allowed:
            lines, beside = differences(group, answer)
            compared += 1
            found += len(lines)
            if lines:
                verdict = "differs: " + "; ".join(lines)
            elif beside:
                verdict = "same, beside " + ", ".join(sorted(beside))
            else:
                verdict = "same"
            out(f"{head} {len(answer):>2}  {verdict}")
        elif status == 403 and path not in allowed:
            out(f"{head} 403  not readable with this token, as the seed grants")
        elif status == 200:
            found += 1
            out(
                f"{head} {len(answer):>2}  differs: readable with this token, which the seed does not grant"
            )
        elif status == 403:
            found += 1
            out(
                f"{head} 403  differs: not readable with this token, which the seed grants"
            )
        else:
            found += 1
            out(f"{head} {status}  differs: {str(answer)[:80]}")
    out(f"== {compared} groups compared, {found} differences")
    return compared, found


def arguments(argv):
    """SEED and the three options, or None for a usage error."""
    options = {"--token": TOKEN, "--url": URL, "--cert": CERT}
    rest = argv[1:]
    if not rest or rest[0].startswith("--"):
        return None
    seed, rest = rest[0], rest[1:]
    while rest:
        if len(rest) < 2 or rest[0] not in options:
            return None
        options[rest[0]] = rest[1]
        rest = rest[2:]
    return seed, options


def main(argv):
    parsed = arguments(argv)
    if parsed is None:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    seed_path, options = parsed
    try:
        with open(seed_path) as file:
            seed = json.load(file)
        with open(options["--token"]) as file:
            token = file.read().strip()
        netbox = netbox_access.NetBox(
            token, url=options["--url"], cert=options["--cert"]
        )
        _, found = compare(seed, netbox)
    except (OSError, ValueError, KeyError, TypeError, Unreadable) as error:
        print(f"failed: {seed_path}: {error}", file=sys.stderr)
        return 2
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
