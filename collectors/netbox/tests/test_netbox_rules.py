"""NetBox's port rules, judged for each viewpoint (ADR 0056).

The rules are exercise 2's seed as the targets repository holds it, with the
consumer's path open and the staging subnet's open too. The network part is
the contract's.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import netbox_rules

FIXTURE = json.loads((HERE / "network.json").read_text(encoding="utf-8"))
SEEDED, NETWORK = FIXTURE["rules"], FIXTURE["network"]


def rule(name, priority, direction, source, destination, access="Allow", ports="8443"):
    return {
        "name": name,
        "priority": priority,
        "direction": direction,
        "access": access,
        "protocol": "Tcp",
        "source_address_prefix": source,
        "destination_address_prefix": destination,
        "destination_port_range": ports,
        "description": "A test rule.",
    }


def without_seed():
    rules = copy.deepcopy(SEEDED)
    rules["netbox"] = [r for r in rules["netbox"] if r["priority"] != 1120]
    rules["rehearsal"] = []
    return rules


def verdicts(rules, network=NETWORK):
    return {n: v["verdict"] for n, v in netbox_rules.configured(rules, network).items()}


class Load(unittest.TestCase):
    def test_the_seed_loads_in_its_own_layout(self):
        text = netbox_rules.dump(SEEDED)
        self.assertEqual(netbox_rules.load(text), SEEDED)

    def broken(self, change):
        rules = copy.deepcopy(SEEDED)
        change(rules)
        return json.dumps(rules)

    def test_files_out_of_shape_are_refused(self):
        cases = {
            "not JSON": "{",
            "not an object of subnets": "[]",
            "a subnet's name out of pattern": json.dumps({"Net Box": []}),
            "not a list of rules": json.dumps({"netbox": {}}),
            "without the rule fields": self.broken(
                lambda r: r["netbox"][0].pop("access")
            ),
            "name out of pattern": self.broken(
                lambda r: r["netbox"][0].update(name="a rule; rm -rf")
            ),
            "not a priority": self.broken(
                lambda r: r["netbox"][0].update(priority="1110")
            ),
            "not a direction": self.broken(
                lambda r: r["netbox"][0].update(direction="In")
            ),
            "not an access": self.broken(
                lambda r: r["netbox"][0].update(access="allow")
            ),
            "not a protocol": self.broken(
                lambda r: r["netbox"][0].update(protocol="tcp")
            ),
            "source_address_prefix out of pattern": self.broken(
                lambda r: r["netbox"][0].update(source_address_prefix="10.50.0.32/27 x")
            ),
            "not a port range": self.broken(
                lambda r: r["netbox"][0].update(destination_port_range="8443,22")
            ),
            "not a description": self.broken(
                lambda r: r["netbox"][0].update(description="x" * 141)
            ),
            "Inbound 1110 twice": self.broken(
                lambda r: r["netbox"][1].update(priority=1110)
            ),
            "name allow-netbox-from-consumer twice": self.broken(
                lambda r: r["netbox"][1].update(name="allow-netbox-from-consumer")
            ),
            "more than": " " * (netbox_rules.MAX_BYTES + 1),
        }
        for why, text in cases.items():
            with self.subTest(why), self.assertRaisesRegex(netbox_rules.Invalid, why):
                netbox_rules.load(text)


class Decide(unittest.TestCase):
    def test_the_lowest_priority_that_matches_decides(self):
        rules = [
            rule("allow-wide", 200, "Inbound", "10.50.0.0/16", "*"),
            rule("deny-staging", 150, "Inbound", "10.50.1.0/27", "*", access="Deny"),
        ]
        access, found = netbox_rules.decide(
            rules, "Inbound", "10.50.1.4", "10.50.0.4", 8443
        )
        self.assertEqual((access, found["name"]), ("Deny", "deny-staging"))
        access, found = netbox_rules.decide(
            rules, "Inbound", "10.50.0.36", "10.50.0.4", 8443
        )
        self.assertEqual((access, found["name"]), ("Allow", "allow-wide"))

    def test_no_rule_is_the_baseline_deny(self):
        rules = [rule("allow-other-port", 200, "Inbound", "*", "*", ports="22")]
        self.assertEqual(
            netbox_rules.decide(rules, "Inbound", "10.50.1.4", "10.50.0.4", 8443),
            ("Deny", None),
        )

    def test_another_direction_or_protocol_does_not_match(self):
        udp = dict(rule("allow-udp", 200, "Inbound", "*", "*"), protocol="Udp")
        out = rule("allow-out", 210, "Outbound", "*", "*")
        self.assertEqual(
            netbox_rules.decide([udp, out], "Inbound", "10.50.1.4", "10.50.0.4", 8443),
            ("Deny", None),
        )

    def test_a_port_range_covers_its_ends(self):
        rules = [rule("allow-range", 200, "Inbound", "*", "*", ports="8000-8443")]
        self.assertEqual(
            netbox_rules.decide(rules, "Inbound", "10.50.1.4", "10.50.0.4", 8443)[0],
            "Allow",
        )
        self.assertEqual(
            netbox_rules.decide(rules, "Inbound", "10.50.1.4", "10.50.0.4", 8444)[0],
            "Deny",
        )

    def test_a_service_tag_that_may_match_cannot_be_read(self):
        rules = [rule("allow-vnet", 200, "Inbound", "VirtualNetwork", "*")]
        access, found = netbox_rules.decide(
            rules, "Inbound", "10.50.1.4", "10.50.0.4", 8443
        )
        self.assertEqual((access, found["name"]), (None, "allow-vnet"))

    def test_a_service_tag_on_a_rule_that_cannot_match_is_skipped(self):
        rules = [
            rule("allow-vnet-ssh", 200, "Inbound", "VirtualNetwork", "*", ports="22")
        ]
        self.assertEqual(
            netbox_rules.decide(rules, "Inbound", "10.50.1.4", "10.50.0.4", 8443),
            ("Deny", None),
        )


class Judge(unittest.TestCase):
    def test_the_seed_lets_staging_in(self):
        found = netbox_rules.configured(SEEDED, NETWORK)
        self.assertEqual(found["staging"]["verdict"], "excess")
        self.assertEqual(
            [(d["subnet"], d["name"], d["access"]) for d in found["staging"]["rules"]],
            [
                ("rehearsal", "allow-netbox-from-rehearsal", "Allow"),
                ("netbox", "allow-netbox-from-rehearsal", "Allow"),
            ],
        )
        self.assertEqual(found["consumer"]["verdict"], "within")

    def test_without_the_seed_both_are_within(self):
        self.assertEqual(
            verdicts(without_seed()), {"consumer": "within", "staging": "within"}
        )

    def test_one_half_of_the_path_is_not_enough(self):
        inbound_only = copy.deepcopy(SEEDED)
        inbound_only["rehearsal"] = []
        self.assertEqual(verdicts(inbound_only)["staging"], "within")
        outbound_only = copy.deepcopy(SEEDED)
        outbound_only["netbox"] = [r for r in SEEDED["netbox"] if r["priority"] != 1120]
        self.assertEqual(verdicts(outbound_only)["staging"], "within")

    def test_a_closed_open_path_is_missing(self):
        rules = without_seed()
        rules["consumer"] = []
        self.assertEqual(verdicts(rules)["consumer"], "missing")

    def test_a_deny_above_the_seed_closes_it(self):
        rules = copy.deepcopy(SEEDED)
        rules["netbox"].append(
            rule("deny-staging", 1050, "Inbound", "10.50.1.0/27", "*", access="Deny")
        )
        self.assertEqual(verdicts(rules)["staging"], "within")

    def test_an_unreadable_rule_is_unknown(self):
        rules = copy.deepcopy(SEEDED)
        rules["netbox"].insert(
            0, rule("allow-vnet", 1000, "Inbound", "VirtualNetwork", "*")
        )
        self.assertEqual(verdicts(rules)["staging"], "unknown")

    def test_a_subnet_the_file_does_not_hold_is_closed(self):
        network = copy.deepcopy(NETWORK)
        network["viewpoints"]["staging"]["subnet"] = "unintended"
        self.assertEqual(verdicts(SEEDED, network)["staging"], "within")


class Change(unittest.TestCase):
    def test_the_seed_and_its_outbound_half_are_removed(self):
        left, gone = netbox_rules.change(SEEDED, NETWORK, "staging", 1120)
        self.assertEqual(
            gone,
            [
                {
                    "subnet": "netbox",
                    "direction": "Inbound",
                    "name": "allow-netbox-from-rehearsal",
                    "priority": 1120,
                },
                {
                    "subnet": "rehearsal",
                    "direction": "Outbound",
                    "name": "allow-netbox-from-rehearsal",
                    "priority": 1120,
                },
            ],
        )
        self.assertEqual(left, without_seed())
        self.assertEqual(SEEDED["rehearsal"][0]["priority"], 1120, "the input is kept")

    def test_rules_that_are_not_the_viewpoints_way_in_are_refused(self):
        cases = {
            1110: "does not let staging in",
            1100: "no inbound rule of priority 1100",
            4096: "no inbound rule",
        }
        for priority, why in cases.items():
            with (
                self.subTest(priority),
                self.assertRaisesRegex(netbox_rules.Invalid, why),
            ):
                netbox_rules.change(SEEDED, NETWORK, "staging", priority)

    def test_a_deny_is_refused(self):
        rules = copy.deepcopy(SEEDED)
        rules["netbox"][1]["access"] = "Deny"
        with self.assertRaisesRegex(netbox_rules.Invalid, "a deny"):
            netbox_rules.change(rules, NETWORK, "staging", 1120)

    def test_an_unknown_viewpoint_is_refused(self):
        with self.assertRaisesRegex(netbox_rules.Invalid, "no viewpoint"):
            netbox_rules.change(SEEDED, NETWORK, "unintended", 1120)


class Network(unittest.TestCase):
    def test_the_contracts_network_part_is_in_shape(self):
        self.assertTrue(netbox_rules.network_in_shape(NETWORK))

    def test_network_parts_out_of_shape_are_refused(self):
        def broken(change):
            network = copy.deepcopy(NETWORK)
            change(network)
            return network

        cases = {
            "no viewpoints": broken(lambda n: n.pop("viewpoints")),
            "an extra key": broken(lambda n: n.update(extra=1)),
            "an address that is not one": broken(lambda n: n.update(address="netbox")),
            "a port as text": broken(lambda n: n.update(port="8443")),
            "port zero": broken(lambda n: n.update(port=0)),
            "a reach that is neither": broken(
                lambda n: n["viewpoints"]["staging"].update(reach="maybe")
            ),
            "a viewpoint's name out of pattern": broken(
                lambda n: n["viewpoints"].update(
                    {"Staging Net": n["viewpoints"]["staging"]}
                )
            ),
            "a name too long for the schema": broken(
                lambda n: n["viewpoints"].update({"a" * 55: n["viewpoints"]["staging"]})
            ),
            "no viewpoint": broken(lambda n: n.update(viewpoints={})),
            "not an object": "network",
        }
        for why, network in cases.items():
            with self.subTest(why):
                self.assertFalse(netbox_rules.network_in_shape(network))


class Facts(unittest.TestCase):
    def test_the_job_gets_no_description(self):
        facts = netbox_rules.facts(SEEDED)
        self.assertEqual(set(facts), set(SEEDED))
        self.assertNotIn("description", json.dumps(facts))
        self.assertEqual(facts["netbox"][1]["source"], "10.50.1.0/27")


if __name__ == "__main__":
    unittest.main()
