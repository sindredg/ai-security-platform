"""Reading and changing which accounts NetBox's permissions are assigned to.

The client is a fake at the level of netbox_access.NetBox's call() and list(),
as the collector's tests fake it. It answers as NetBox does: a permission's
users in their brief form, and a PATCH that sets the users it names.
"""

import sys
import unittest
from pathlib import Path
from typing import ClassVar

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "collectors" / "netbox"))
sys.path.insert(0, str(HERE))

import netbox_change

SEED = {
    "objects": [
        {"path": "/api/tenancy/tenants/", "key": "slug", "items": []},
        {
            "path": "/api/users/permissions/",
            "key": "name",
            "items": [
                {"name": "reader: tenant-a", "users": ["reader"]},
                {"name": "reader: all", "users": ["reader", "other"]},
            ],
        },
    ],
    "tokens": [],
}


class FakeNetBox:
    def __init__(self):
        self.users = {1: "reader", 2: "other", 3: "control"}
        self.permissions = {
            10: {"name": "reader: tenant-a", "users": [1]},
            11: {"name": "reader: all", "users": [1, 2]},
        }
        self.patches = []
        self.patch_status = 200

    def brief(self, user_id):
        return {
            "id": user_id,
            "display": self.users[user_id],
            "username": self.users[user_id],
        }

    def list(self, path, **query):
        if path == "/api/users/permissions/":
            found = [
                {
                    "id": i,
                    "name": p["name"],
                    "users": [self.brief(u) for u in p["users"]],
                }
                for i, p in self.permissions.items()
                if p["name"] == query["name"]
            ]
            return 200, found
        if path == "/api/users/users/":
            found = [
                {"id": i, "username": name}
                for i, name in self.users.items()
                if name == query["username"]
            ]
            return 200, found
        return 403, {"detail": "no"}

    def call(self, method, path, body=None):
        self.patches.append((method, path, body))
        if self.patch_status != 200:
            return self.patch_status, {"detail": "no"}
        permission_id = int(path.rstrip("/").rsplit("/", 1)[1])
        self.permissions[permission_id]["users"] = list(body["users"])
        return 200, {"id": permission_id}


class Assignments(unittest.TestCase):
    def test_the_seeds_assignments_are_by_permission_name(self):
        self.assertEqual(
            netbox_change.seed_assignments(SEED),
            {"reader: all": ["other", "reader"], "reader: tenant-a": ["reader"]},
        )

    def test_live_assignments_name_users_by_username(self):
        live = netbox_change.live_assignments(
            FakeNetBox(), ["reader: all", "reader: tenant-a"]
        )
        self.assertEqual(
            live,
            {
                "reader: all": {"id": 11, "users": ["other", "reader"]},
                "reader: tenant-a": {"id": 10, "users": ["reader"]},
            },
        )

    def test_a_permission_netbox_does_not_hold_fails(self):
        with self.assertRaisesRegex(netbox_change.Failed, "reader: gone: 0 found"):
            netbox_change.live_assignments(FakeNetBox(), ["reader: gone"])

    def test_the_plan_holds_only_the_permissions_whose_users_differ(self):
        netbox = FakeNetBox()
        live = netbox_change.live_assignments(
            netbox, ["reader: all", "reader: tenant-a"]
        )
        wanted = {"reader: all": ["other"], "reader: tenant-a": ["reader"]}
        self.assertEqual(
            netbox_change.plan(live, wanted),
            [{"permission": "reader: all", "id": 11, "users": ["other"]}],
        )

    def test_a_plan_for_a_permission_not_read_fails(self):
        with self.assertRaisesRegex(netbox_change.Failed, "not read from NetBox"):
            netbox_change.plan({}, {"reader: all": ["other"]})


class Apply(unittest.TestCase):
    def test_apply_patches_only_the_users_list(self):
        netbox = FakeNetBox()
        netbox_change.apply(
            netbox, [{"permission": "reader: all", "id": 11, "users": ["other"]}]
        )
        self.assertEqual(
            netbox.patches, [("PATCH", "/api/users/permissions/11/", {"users": [2]})]
        )
        self.assertEqual(netbox.permissions[11]["users"], [2])

    def test_a_refused_change_fails(self):
        netbox = FakeNetBox()
        netbox.patch_status = 403
        with self.assertRaisesRegex(netbox_change.Failed, "reader: all: 403"):
            netbox_change.apply(
                netbox, [{"permission": "reader: all", "id": 11, "users": ["other"]}]
            )

    def test_a_user_netbox_does_not_hold_fails_before_any_change(self):
        netbox = FakeNetBox()
        with self.assertRaisesRegex(netbox_change.Failed, "nobody: 0 found"):
            netbox_change.apply(
                netbox, [{"permission": "reader: all", "id": 11, "users": ["nobody"]}]
            )
        self.assertEqual(netbox.patches, [])


class RemoveOnly(unittest.TestCase):
    OLD: ClassVar[dict] = {
        "reader: all": ["other", "reader"],
        "reader: tenant-a": ["reader"],
    }

    def test_a_removal_is_remove_only(self):
        new = {"reader: all": ["other"], "reader: tenant-a": ["reader"]}
        self.assertTrue(netbox_change.remove_only(self.OLD, new))

    def test_remove_only_refuses_an_added_user(self):
        new = {
            "reader: all": ["other", "reader"],
            "reader: tenant-a": ["control", "reader"],
        }
        self.assertFalse(netbox_change.remove_only(self.OLD, new))

    def test_remove_only_refuses_another_set_of_permissions(self):
        new = {"reader: all": ["other"]}
        self.assertFalse(netbox_change.remove_only(self.OLD, new))
        new = dict(self.OLD, **{"control: new": []})
        self.assertFalse(netbox_change.remove_only(self.OLD, new))


if __name__ == "__main__":
    unittest.main()
