"""Both of the collector's methods against a made-up NetBox.

The fake answers what NetBox's REST API answers, as read from its v4.7.3
source: lists with a count and a page of results, nested users and groups, and
a status code for a refusal. The paging is the collector's own.
"""

import http.server
import json
import os
import ssl
import sys
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import netbox_access as collector

CONTRACT = {
    "accounts": ["reader", "control"],
    "grants": [
        {"object_type": "dcim.device", "action": "view", "constraints": {"t": "a"}},
        {"object_type": "ipam.ipaddress", "action": "view", "constraints": {"t": "a"}},
    ],
    "reads": [
        {
            "path": "/api/dcim/devices/",
            "key": "name",
            "fields": ["id", "name"],
            "records": ["a-1", "a-2"],
        },
    ],
    "denials": [
        {"method": "GET", "path": "/api/dcim/sites/", "status": 403},
        {"method": "POST", "path": "/api/dcim/devices/", "status": 403},
    ],
}
TYPES = ["dcim.device", "ipam.ipaddress"]


def permission(pid, name, constraints, types=TYPES, actions=("view",), **extra):
    fields = {
        "id": pid,
        "name": name,
        "enabled": True,
        "object_types": list(types),
        "actions": list(actions),
        "constraints": constraints,
    }
    return fields | extra


class World:
    """What the fake NetBox holds, and what each token gets back."""

    def __init__(self):
        self.users = [
            {"id": 1, "username": "reader", "is_active": True, "groups": []},
            {"id": 2, "username": "control", "is_active": True, "groups": []},
        ]
        # Permissions by the user or group they apply to.
        self.by_user = {
            1: [
                permission(10, "reader scoped", {"t": "a"}),
                permission(11, "reader copy", None),
            ],
            2: [permission(12, "control scoped", {"t": "a"})],
        }
        self.by_group = {}
        # What each token's reads return, and its answer to anything else.
        self.devices = {
            "reader": [{"id": n, "name": f"{t}-{n}"} for t in "abc" for n in (1, 2)],
            "control": [{"id": n, "name": f"a-{n}"} for n in (1, 2)],
        }
        self.other = {"reader": 403, "control": 403}
        self.calls = []

    def answer(self, token, method, path, body):
        self.calls.append((token, method, path, body))
        url = urllib.parse.urlparse(path)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path == "/api/users/users/" and token == collector.COLLECTOR:
            found = [u for u in self.users if u["username"] == query["username"]]
            return 200, page(found, query)
        if url.path == "/api/users/permissions/" and token == collector.COLLECTOR:
            if "user_id" in query:
                found = self.by_user.get(int(query["user_id"]), [])
            else:
                found = self.by_group.get(int(query["group_id"]), [])
            return 200, page(found, query)
        if (
            url.path == "/api/dcim/devices/"
            and method == "GET"
            and token in self.devices
        ):
            return 200, page(self.devices[token], query)
        status = self.other.get(token, 403)
        return status, {"detail": "You do not have permission to perform this action."}


def page(found, query):
    """One page as NetBox's offset paging cuts it."""
    limit, offset = int(query["limit"]), int(query["offset"])
    return {"count": len(found), "results": found[offset : offset + limit]}


class Case(unittest.TestCase):
    def setUp(self):
        self.world = World()
        world = self.world

        class FakeNetBox(collector.NetBox):
            def __init__(self, token):
                self.token = token

            def call(self, method, path, body=None):
                status, answer = world.answer(self.token, method, path, body)
                return status, json.loads(json.dumps(answer))

        for name, value in [("NetBox", FakeNetBox), ("read_token", lambda a: a)]:
            patch = mock.patch.object(collector, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def verdicts(self, method):
        return {a: v["verdict"] for a, v in method(CONTRACT).items()}

    def why(self, method, account):
        return [r["why"] for r in method(CONTRACT)[account]["reasons"]]


class Configured(Case):
    def test_the_seeded_finding_and_the_unaffected_case(self):
        self.assertEqual(
            self.verdicts(collector.configured),
            {"reader": "excess", "control": "within"},
        )
        why = self.why(collector.configured, "reader")
        self.assertIn("view on dcim.device without a constraint (reader copy)", why)

    def test_the_evidence_names_each_permission_once(self):
        found = collector.configured(CONTRACT)["reader"]["permissions"]
        self.assertEqual(sorted(p["id"] for p in found), [10, 11])

    def test_a_permission_through_a_group_counts(self):
        self.world.users[1]["groups"] = [{"id": 7, "name": "readers"}]
        self.world.by_group[7] = [permission(13, "group copy", None)]
        result = collector.configured(CONTRACT)["control"]
        self.assertEqual(result["verdict"], "excess")
        self.assertIn("group readers", [p["via"] for p in result["permissions"]])

    def test_a_disabled_permission_does_not_count(self):
        self.world.by_user[1][1]["enabled"] = False
        self.assertEqual(self.verdicts(collector.configured)["reader"], "within")

    def test_an_empty_constraint_is_every_object(self):
        for empty in ({}, [], [{"t": "a"}, {}]):
            self.world.by_user[2][0]["constraints"] = empty
            self.assertEqual(self.verdicts(collector.configured)["control"], "excess")

    def test_a_constraint_in_a_list_equals_the_same_one_alone(self):
        self.world.by_user[2][0]["constraints"] = [{"t": "a"}]
        self.assertEqual(self.verdicts(collector.configured)["control"], "within")

    def test_another_type_or_action_is_excess(self):
        extra = permission(14, "sites", {"t": "a"}, types=["dcim.site"])
        self.world.by_user[2].append(extra)
        self.assertEqual(self.verdicts(collector.configured)["control"], "excess")
        self.world.by_user[2] = [
            permission(15, "change", {"t": "a"}, actions=["view", "change"])
        ]
        self.assertEqual(self.verdicts(collector.configured)["control"], "excess")

    def test_another_constraint_is_for_the_reads_to_decide(self):
        self.world.by_user[2][0]["constraints"] = {"t__in": ["a", "b"]}
        self.assertEqual(self.verdicts(collector.configured)["control"], "unknown")

    def test_a_grant_that_is_gone_breaks_the_contract(self):
        self.world.by_user[2][0]["object_types"] = ["dcim.device"]
        self.assertEqual(self.verdicts(collector.configured)["control"], "missing")
        self.world.by_user[2] = []
        self.assertEqual(self.verdicts(collector.configured)["control"], "missing")

    def test_an_account_that_is_gone_or_inactive_breaks_the_contract(self):
        self.world.users[1]["is_active"] = False
        self.assertEqual(self.verdicts(collector.configured)["control"], "missing")
        del self.world.users[1]
        self.assertEqual(self.verdicts(collector.configured)["control"], "missing")

    def test_excess_outranks_a_broken_contract(self):
        self.world.by_user[1] = [
            permission(16, "devices only", None, types=["dcim.device"])
        ]
        result = collector.configured(CONTRACT)["reader"]
        kinds = sorted({r["kind"] for r in result["reasons"]})
        self.assertEqual((result["verdict"], kinds), ("excess", ["excess", "missing"]))


class Observed(Case):
    def test_the_seeded_finding_and_the_unaffected_case(self):
        self.assertEqual(
            self.verdicts(collector.observed),
            {"reader": "excess", "control": "within"},
        )
        why = self.why(collector.observed, "reader")
        self.assertEqual(
            why, [f"/api/dcim/devices/: {t}-{n}" for t in "bc" for n in (1, 2)]
        )

    def test_a_record_that_is_gone_breaks_the_contract(self):
        del self.world.devices["control"][0]
        self.assertEqual(self.verdicts(collector.observed)["control"], "missing")

    def test_a_record_without_a_field_breaks_the_contract(self):
        del self.world.devices["control"][0]["id"]
        self.assertEqual(self.verdicts(collector.observed)["control"], "missing")

    def test_a_refused_read_breaks_the_contract(self):
        del self.world.devices["control"]
        result = collector.observed(CONTRACT)["control"]
        self.assertEqual(result["verdict"], "missing")
        self.assertIn("/api/dcim/devices/: 403", result["reasons"][0]["why"])

    def test_an_answered_denial_is_excess(self):
        self.world.other["control"] = 200
        self.assertEqual(self.verdicts(collector.observed)["control"], "excess")

    def test_a_denial_with_another_status_is_unknown(self):
        self.world.other["control"] = 404
        self.assertEqual(self.verdicts(collector.observed)["control"], "unknown")

    def test_a_write_goes_with_an_empty_body(self):
        collector.observed(CONTRACT)
        posts = [c for c in self.world.calls if c[1] == "POST"]
        self.assertEqual([c[3] for c in posts], [{}, {}])

    def test_every_page_is_read_with_offsets_the_collector_makes(self):
        self.world.devices["control"] = [
            {"id": n, "name": f"a-{n}"} for n in range(2500)
        ]
        result = collector.observed(CONTRACT)["control"]
        self.assertEqual(len(result["reads"]["/api/dcim/devices/"]), 2500)
        offsets = [
            c[2] for c in self.world.calls if c[0] == "control" and "devices" in c[2]
        ]
        self.assertEqual(
            [
                dict(urllib.parse.parse_qsl(urllib.parse.urlparse(o).query))["offset"]
                for o in offsets
                if "offset" in o
            ],
            ["0", "1000", "2000"],
        )

    def test_a_malformed_answer_is_not_a_read(self):
        for answer in (
            {"count": "2", "results": [{"name": "a-1"}]},
            {"count": 2, "results": ["a-1", "a-2"]},
            ["a-1", "a-2"],
        ):
            self.world.answer = lambda *call, answer=answer: (200, answer)
            reasons = collector.observed(CONTRACT)["control"]["reasons"]
            reads = [r for r in reasons if r["why"].startswith("/api/dcim/devices/")]
            self.assertEqual([r["kind"] for r in reads], ["missing"])
            self.assertIn("/api/dcim/devices/: 0 ", reads[0]["why"])


class Transport(unittest.TestCase):
    """The collector's own opener, against a local server in plain HTTP.

    The server answers every path but one with a redirect to that one. The
    environment names a proxy on a port where nothing listens, as the
    orchestrator's names Squid.
    """

    def setUp(self):
        seen = self.seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                moved = self.path != "/away"
                body = b'{"detail": "moved"}' if moved else b"{}"
                self.send_response(302 if moved else 200)
                if moved:
                    self.send_header("Location", "/away")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        proxy = "http://127.0.0.1:9"
        environment = {"http_proxy": proxy, "HTTP_PROXY": proxy}
        environment |= {"no_proxy": "", "NO_PROXY": ""}
        for patch in [
            mock.patch.object(
                collector, "URL", f"http://127.0.0.1:{server.server_port}"
            ),
            # The pinned certificate is the VM's. Plain HTTP needs none.
            mock.patch.object(
                collector.ssl,
                "create_default_context",
                lambda cafile: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
            ),
            mock.patch.dict(os.environ, environment),
        ]:
            patch.start()
            self.addCleanup(patch.stop)

    def test_a_redirect_is_an_answer_and_is_not_followed(self):
        status, answer = collector.NetBox("t").call("GET", "/api/status/")
        self.assertEqual((status, answer), (302, {"detail": "moved"}))
        self.assertEqual(self.seen, [("/api/status/", "Bearer t")])


class Main(unittest.TestCase):
    def test_the_summary_line(self):
        accounts = {"reader": {"verdict": "excess"}, "control": {"verdict": "within"}}
        with (
            mock.patch.object(collector, "configured", return_value=accounts),
            mock.patch.object(sys, "argv", ["x", "configured", "--summary"]),
            mock.patch.object(sys, "stdin", mock.Mock(read=lambda: "{}")),
            mock.patch("builtins.print") as printed,
        ):
            collector.main()
        printed.assert_called_once_with("reader:excess control:within")

    def test_an_unknown_mode_stops(self):
        with (
            mock.patch.object(sys, "argv", ["x", "both"]),
            self.assertRaises(SystemExit),
        ):
            collector.main()


if __name__ == "__main__":
    unittest.main()
