"""Which accounts NetBox's permissions are assigned to, read and changed.

A library on the orchestrator host, beside the collector, whose client it
uses. The rehearsal changes the copy with it (ADR 0044), and delivery the
live NetBox (ADR 0046). A change sets one permission's users, by name, and
touches no other field: a PATCH with the users list alone.

The seed in the targets repository is the expected state. Its permissions
name their users, and so does a plan. NetBox's answers are target side: a
permission or an account that is not there exactly once fails the run.
Standard library only.
"""

import netbox_access

PERMISSIONS = "/api/users/permissions/"
USERS = "/api/users/users/"


class Failed(Exception):
    pass


def client(url, cert, token_path):
    """A NetBox client for the copy or the live NetBox, with a token from a
    file root keeps."""
    with open(token_path) as file:
        return netbox_access.NetBox(file.read().strip(), url=url, cert=cert)


def client_for(url, cert, token):
    """A NetBox client with a token held in memory, never in a file."""
    return netbox_access.NetBox(token, url=url, cert=cert)


def seed_assignments(seed):
    """Each permission's users in a seed, by the permission's name."""
    for group in seed["objects"]:
        if group["path"] == PERMISSIONS:
            return {item["name"]: sorted(item["users"]) for item in group["items"]}
    raise Failed("the seed holds no permissions")


def the_one(netbox, path, what, **query):
    status, found = netbox.list(path, **query)
    if status != 200:
        raise Failed(f"{what}: {status} {found}")
    if len(found) != 1:
        raise Failed(f"{what}: {len(found)} found, 1 expected")
    return found[0]


def live_assignments(netbox, names):
    """Each named permission's ID and users in NetBox."""
    live = {}
    for name in names:
        found = the_one(netbox, PERMISSIONS, name, name=name)
        users = sorted(str(user["username"]) for user in found["users"])
        live[name] = {"id": int(found["id"]), "users": users}
    return live


def plan(live, wanted):
    """The permissions whose users differ from the wanted ones, with them."""
    changes = []
    for name in sorted(wanted):
        if name not in live:
            raise Failed(f"{name}: not read from NetBox")
        if live[name]["users"] != sorted(wanted[name]):
            changes.append(
                {
                    "permission": name,
                    "id": live[name]["id"],
                    "users": sorted(wanted[name]),
                }
            )
    return changes


def apply(netbox, changes):
    """Sets each changed permission's users, after every user is found."""
    ids = {
        user: the_one(netbox, USERS, user, username=user)["id"]
        for change in changes
        for user in change["users"]
    }
    for change in changes:
        body = {"users": [ids[user] for user in change["users"]]}
        status, answer = netbox.call("PATCH", f"{PERMISSIONS}{change['id']}/", body)
        if status != 200:
            raise Failed(f"{change['permission']}: {status} {answer}")


def remove_only(old, new):
    """Whether new holds the same permissions as old, each with users that
    old's has too: a change that adds nobody anywhere."""
    if set(old) != set(new):
        return False
    return all(set(new[name]) <= set(old[name]) for name in new)
