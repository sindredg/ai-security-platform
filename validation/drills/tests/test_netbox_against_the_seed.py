"""The seed comparison against a fake NetBox: the same, a missing and an
extra object, a changed permission, the token's own access, and the exit
codes."""

import contextlib
import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["AISEC_COLLECTOR_DIR"] = str(HERE.parents[2] / "collectors" / "netbox")

spec = importlib.util.spec_from_file_location(
    "netbox_against_the_seed", HERE.parent / "netbox_against_the_seed.py"
)
against = importlib.util.module_from_spec(spec)
spec.loader.exec_module(against)

DEVICES = "/api/dcim/devices/"
TENANTS = "/api/tenancy/tenants/"
USERS = "/api/users/users/"
PERMISSIONS = "/api/users/permissions/"

SEED = {
    "objects": [
        {
            "path": TENANTS,
            "key": "slug",
            "items": [{"name": "Tenant A", "slug": "tenant-a"}],
        },
        {
            "path": DEVICES,
            "key": "name",
            "items": [
                {"name": "sw-1", "status": "active", "tenant": {"slug": "tenant-a"}},
                {"name": "sw-2", "status": "active", "tenant": {"slug": "tenant-a"}},
            ],
        },
        {
            "path": USERS,
            "key": "username",
            "items": [
                {"username": "inventory-reader"},
                {"username": "aisec-collector"},
            ],
        },
        {
            "path": PERMISSIONS,
            "key": "name",
            "items": [
                {
                    "name": "inventory-reader: tenant-a inventory",
                    "enabled": True,
                    "object_types": ["dcim.device"],
                    "actions": ["view"],
                    "constraints": {"tenant__slug": "tenant-a"},
                    "users": ["inventory-reader"],
                },
                {
                    "name": "aisec-collector: inventory and access",
                    "enabled": True,
                    "object_types": [
                        "dcim.device",
                        "users.user",
                        "users.objectpermission",
                    ],
                    "actions": ["view"],
                    "constraints": None,
                    "users": ["aisec-collector"],
                },
            ],
        },
    ],
    "tokens": [],
}

FORBIDDEN = (403, {"detail": "You do not have permission to perform this action."})


def device(name):
    return {
        "id": 1,
        "name": name,
        "status": {"value": "active", "label": "Active"},
        "tenant": {"id": 1, "name": "Tenant A", "slug": "tenant-a"},
    }


def permission(name, users, constraints, object_types):
    return {
        "id": 7,
        "name": name,
        "enabled": True,
        "object_types": list(reversed(object_types)),
        "actions": ["view"],
        "constraints": constraints,
        "users": [{"id": 2, "username": u} for u in users],
    }


def netbox_answers():
    return {
        TENANTS: FORBIDDEN,
        DEVICES: (200, [device("sw-1"), device("sw-2")]),
        USERS: (
            200,
            [
                {"id": 2, "username": "inventory-reader"},
                {"id": 3, "username": "aisec-collector"},
            ],
        ),
        PERMISSIONS: (
            200,
            [
                permission(
                    "inventory-reader: tenant-a inventory",
                    ["inventory-reader"],
                    {"tenant__slug": "tenant-a"},
                    ["dcim.device"],
                ),
                permission(
                    "aisec-collector: inventory and access",
                    ["aisec-collector"],
                    None,
                    ["dcim.device", "users.user", "users.objectpermission"],
                ),
            ],
        ),
    }


class FakeNetBox:
    def __init__(self, answers):
        self.answers = answers
        self.listed = []

    def list(self, path, **query):
        self.listed.append(path)
        return self.answers[path]


def run(seed, answers):
    out = io.StringIO()
    result = against.compare(
        seed, FakeNetBox(answers), out=lambda line: print(line, file=out)
    )
    return result, out.getvalue()


class Compare(unittest.TestCase):
    def test_a_netbox_at_the_seed_has_no_difference(self):
        (compared, differences), out = run(SEED, netbox_answers())
        self.assertEqual((compared, differences), (3, 0))
        self.assertEqual(out.count(" same"), 3)
        self.assertIn(
            f"{TENANTS:<28} seed  1  netbox 403  not readable with this token, as the seed grants",
            out,
        )
        self.assertIn("== 3 groups compared, 0 differences", out)

    def test_a_missing_and_an_extra_object_are_differences(self):
        answers = netbox_answers()
        answers[DEVICES] = (200, [device("sw-1"), device("sw-9")])
        (_, differences), out = run(SEED, answers)
        self.assertEqual(differences, 2)
        self.assertIn("differs: no sw-2; extra sw-9", out)

    def test_a_changed_seed_count_is_a_difference(self):
        seed = copy.deepcopy(SEED)
        seed["objects"][1]["items"].append(
            {"name": "sw-3", "status": "active", "tenant": {"slug": "tenant-a"}}
        )
        (_, differences), out = run(seed, netbox_answers())
        self.assertEqual(differences, 1)
        self.assertIn("seed  3  netbox  2  differs: no sw-3", out)

    def test_a_permissions_constraints_and_users_are_compared(self):
        answers = netbox_answers()
        answers[PERMISSIONS][1][0]["constraints"] = None
        answers[PERMISSIONS][1][0]["users"] = []
        (_, differences), out = run(SEED, answers)
        self.assertEqual(differences, 1)
        self.assertIn(
            "inventory-reader: tenant-a inventory differs in constraints, users", out
        )

    def test_a_choice_and_a_related_object_are_compared_by_value(self):
        answers = netbox_answers()
        answers[DEVICES][1][0]["status"] = {"value": "offline", "label": "Offline"}
        answers[DEVICES][1][1]["tenant"]["slug"] = "tenant-b"
        (_, differences), out = run(SEED, answers)
        self.assertEqual(differences, 2)
        self.assertIn("sw-1 differs in status; sw-2 differs in tenant", out)

    def test_two_records_with_one_key_are_a_difference(self):
        answers = netbox_answers()
        answers[DEVICES] = (200, [device("sw-1"), device("sw-1"), device("sw-2")])
        (_, differences), out = run(SEED, answers)
        self.assertEqual(differences, 1)
        self.assertIn("differs: 3 records for 2 keys", out)

    def test_a_granted_group_the_token_cannot_read_is_a_difference(self):
        answers = netbox_answers()
        answers[DEVICES] = FORBIDDEN
        (compared, differences), out = run(SEED, answers)
        self.assertEqual((compared, differences), (2, 1))
        self.assertIn(
            "netbox 403  differs: not readable with this token, which the seed grants",
            out,
        )

    def test_an_ungranted_group_the_token_reads_is_a_difference(self):
        answers = netbox_answers()
        answers[TENANTS] = (200, [{"id": 1, "name": "Tenant A", "slug": "tenant-a"}])
        (compared, differences), out = run(SEED, answers)
        self.assertEqual((compared, differences), (3, 1))
        self.assertIn(
            "differs: readable with this token, which the seed does not grant", out
        )

    def test_another_status_is_a_difference(self):
        answers = netbox_answers()
        answers[USERS] = (0, "an answer that is not an object")
        (_, differences), out = run(SEED, answers)
        self.assertEqual(differences, 1)
        self.assertIn("netbox 0  differs: an answer that is not an object", out)

    def test_the_accounts_the_token_script_makes_are_not_extras(self):
        answers = netbox_answers()
        answers[USERS][1].extend(
            [
                {"id": 4, "username": "aisec-seed"},
                {"id": 5, "username": "aisec-address-probe"},
            ]
        )
        (_, differences), out = run(SEED, answers)
        self.assertEqual(differences, 0)
        self.assertIn(
            f"{USERS:<28} seed  2  netbox  4  same, beside aisec-address-probe, aisec-seed",
            out,
        )

    def test_a_seed_that_grants_the_collector_nothing_is_refused(self):
        seed = copy.deepcopy(SEED)
        seed["objects"][3]["items"][1]["users"] = []
        with self.assertRaisesRegex(
            against.Unreadable, "grants aisec-collector nothing"
        ):
            against.granted(seed)

    def test_an_object_type_without_a_known_endpoint_is_refused(self):
        seed = copy.deepcopy(SEED)
        seed["objects"][3]["items"][1]["object_types"].append("dcim.cable")
        with self.assertRaisesRegex(
            against.Unreadable, "no endpoint known for dcim.cable"
        ):
            against.granted(seed)


class Main(unittest.TestCase):
    def setUp(self):
        self.answers = netbox_answers()
        self.clients = []
        tests = self

        class Client(FakeNetBox):
            def __init__(self, token, url=None, cert=None):
                super().__init__(tests.answers)
                tests.clients.append((token, url, cert))

        self.real = against.netbox_access.NetBox
        against.netbox_access.NetBox = Client
        self.addCleanup(setattr, against.netbox_access, "NetBox", self.real)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.seed = Path(self.dir.name, "seed.json")
        self.seed.write_text(json.dumps(SEED))
        self.token = Path(self.dir.name, "token")
        self.token.write_text("nbt_abc.def\n")

    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = against.main(["netbox_against_the_seed.py", *argv])
        return code, out.getvalue()

    def test_the_same_exits_0_and_a_difference_1(self):
        code, out = self.main(str(self.seed), "--token", str(self.token))
        self.assertEqual(code, 0)
        self.assertIn("0 differences", out)
        self.assertEqual(self.clients, [("nbt_abc.def", against.URL, against.CERT)])
        self.answers[DEVICES] = (200, [device("sw-1")])
        code, out = self.main(str(self.seed), "--token", str(self.token))
        self.assertEqual(code, 1)
        self.assertIn("1 differences", out)

    def test_the_copys_address_certificate_and_token_are_options(self):
        code, _ = self.main(
            str(self.seed),
            "--token",
            str(self.token),
            "--url",
            "https://10.50.1.4:8443",
            "--cert",
            "/c.crt",
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.clients[0][1:], ("https://10.50.1.4:8443", "/c.crt"))

    def test_a_bad_seed_or_argument_exits_2(self):
        self.assertEqual(self.main()[0], 2)
        self.assertEqual(self.main(str(self.seed), "--token")[0], 2)
        self.assertEqual(
            self.main(str(self.seed), "--token", str(self.token), "--colour", "x")[0], 2
        )
        self.seed.write_text("{")
        code, out = self.main(str(self.seed), "--token", str(self.token))
        self.assertEqual(code, 2)
        self.assertIn("seed.json", out)
        self.seed.write_text(json.dumps({"objects": []}))
        code, out = self.main(str(self.seed), "--token", str(self.token))
        self.assertEqual(code, 2)
        self.assertIn("grants aisec-collector nothing", out)
        code, out = self.main(
            str(self.seed), "--token", str(Path(self.dir.name, "none"))
        )
        self.assertEqual(code, 2)
        self.assertIn("none", out)


if __name__ == "__main__":
    unittest.main()
