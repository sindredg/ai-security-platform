"""Token revocation against a fake NetBox: each token deleted, an account
with none, an unknown account, a refused deletion, and the arguments."""

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["AISEC_COLLECTOR_DIR"] = str(HERE.parents[2] / "collectors" / "netbox")

spec = importlib.util.spec_from_file_location(
    "revoke_netbox_tokens", HERE.parent / "revoke_netbox_tokens.py"
)
revoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revoke)

USERS = "/api/users/users/"
TOKENS = "/api/users/tokens/"


class FakeNetBox:
    def __init__(self, users, tokens, deletes=204):
        self.users, self.tokens, self.deletes = users, tokens, deletes
        self.calls = []

    def list(self, path, **query):
        self.calls.append(("list", path, query))
        if path == USERS:
            return 200, [
                u for u in self.users if u["username"] == query.get("username")
            ]
        if path == TOKENS:
            return 200, [
                t for t in self.tokens if t["user"]["id"] == query.get("user_id")
            ]
        return 404, {"detail": "Not found."}

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        return self.deletes, None


def run(netbox, account):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = revoke.revoke_tokens(netbox, account)
    return code, out.getvalue()


class Revoke(unittest.TestCase):
    def setUp(self):
        self.users = [
            {"id": 3, "username": "aisec-collector"},
            {"id": 4, "username": "inventory-reader"},
        ]
        self.tokens = [
            {"id": 11, "user": {"id": 3, "username": "aisec-collector"}},
            {"id": 12, "user": {"id": 3, "username": "aisec-collector"}},
            {"id": 13, "user": {"id": 4, "username": "inventory-reader"}},
        ]

    def test_every_token_of_the_account_is_deleted_and_no_other(self):
        netbox = FakeNetBox(self.users, self.tokens)
        code, out = run(netbox, "aisec-collector")
        self.assertEqual(code, 0)
        deletes = [c for c in netbox.calls if c[0] == "DELETE"]
        self.assertEqual(
            deletes,
            [("DELETE", f"{TOKENS}11/", None), ("DELETE", f"{TOKENS}12/", None)],
        )
        self.assertIn("deleted token 11 of aisec-collector: 204", out)
        self.assertIn("deleted token 12 of aisec-collector: 204", out)
        self.assertIn("== 2 tokens of aisec-collector deleted", out)

    def test_an_account_without_a_token_is_not_a_failure(self):
        netbox = FakeNetBox(self.users, [])
        code, out = run(netbox, "aisec-collector")
        self.assertEqual(code, 0)
        self.assertIn("== 0 tokens of aisec-collector deleted", out)
        self.assertNotIn("DELETE", str(netbox.calls))

    def test_an_unknown_account_is_refused(self):
        code, out = run(FakeNetBox(self.users, self.tokens), "nobody")
        self.assertEqual(code, 1)
        self.assertIn("nobody: 0 found, 1 expected", out)

    def test_a_refused_deletion_fails_the_run(self):
        code, out = run(
            FakeNetBox(self.users, self.tokens, deletes=403), "aisec-collector"
        )
        self.assertEqual(code, 1)
        self.assertIn("deleted token 11 of aisec-collector: 403", out)
        self.assertIn("== 0 of 2 tokens of aisec-collector deleted", out)


class Main(unittest.TestCase):
    def setUp(self):
        self.clients = []
        tests = self

        class Client(FakeNetBox):
            def __init__(self, token, url=None, cert=None):
                super().__init__([{"id": 3, "username": "aisec-collector"}], [])
                tests.clients.append((token, url, cert))

        self.real = revoke.netbox_access.NetBox
        revoke.netbox_access.NetBox = Client
        self.addCleanup(setattr, revoke.netbox_access, "NetBox", self.real)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.seed_token = Path(self.dir.name, "seed-token")
        self.seed_token.write_text("nbt_seed.token\n")

    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = revoke.main(["revoke_netbox_tokens.py", *argv])
        return code, out.getvalue()

    def test_the_account_and_the_seed_token_file(self):
        code, out = self.main("aisec-collector", "--seed-token", str(self.seed_token))
        self.assertEqual(code, 0)
        self.assertEqual(self.clients, [("nbt_seed.token", revoke.URL, revoke.CERT)])
        self.assertIn("== 0 tokens", out)

    def test_the_copys_address_and_certificate_are_options(self):
        code, _ = self.main(
            "aisec-collector",
            "--seed-token",
            str(self.seed_token),
            "--url",
            "https://10.50.1.4:8443",
            "--cert",
            "/c",
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.clients[0][1:], ("https://10.50.1.4:8443", "/c"))

    def test_a_bad_argument_or_a_missing_seed_token_exits_2(self):
        self.assertEqual(self.main()[0], 2)
        self.assertEqual(self.main("aisec-collector", "--seed-token")[0], 2)
        self.assertEqual(self.main("aisec-collector", "--colour", "x")[0], 2)
        code, out = self.main(
            "aisec-collector", "--seed-token", str(Path(self.dir.name, "none"))
        )
        self.assertEqual(code, 2)
        self.assertIn("none", out)


if __name__ == "__main__":
    unittest.main()
