"""The policy check on a job's proposals (ADR 0043).

The permissions are the seed's, as the configured check reports them, with
IDs of the tests' own. The contract is the seed's, and the sites case's from
the case file.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "collectors" / "netbox"))
sys.path.insert(0, str(HERE))

import policy

TYPES = ["dcim.device", "ipam.ipaddress"]
TENANT_A = {"tenant__slug": "tenant-a"}


def permission(id_, name, constraints, via="user", types=TYPES, actions=("view",)):
    return {
        "id": id_,
        "name": name,
        "object_types": list(types),
        "actions": list(actions),
        "constraints": constraints,
        "via": via,
    }


SCOPED = permission(1, "inventory-reader: tenant-a inventory", TENANT_A)
UNSCOPED = permission(2, "inventory-reader: inventory", None)
CONTROL = permission(3, "inventory-reader-control: tenant-a inventory", TENANT_A)
CONTRACT = {
    "accounts": ["inventory-reader", "inventory-reader-control"],
    "grants": [
        {"object_type": t, "action": "view", "constraints": TENANT_A} for t in TYPES
    ],
}
CONFIGURED = {
    "check": "configured",
    "accounts": {
        "inventory-reader": {"verdict": "excess", "permissions": [SCOPED, UNSCOPED]},
        "inventory-reader-control": {"verdict": "within", "permissions": [CONTROL]},
    },
}


def row(account, verdict):
    return {
        "account": account,
        "model": verdict,
        "references": ["ev-0002"],
        "configured": verdict,
        "observed": verdict,
        "outcome": "match",
    }


def proposal(account="inventory-reader", permission_id=2, action="remove"):
    return {
        "account": account,
        "action": action,
        "permission": permission_id,
        "references": ["ev-0002"],
    }


def comparison(*proposals, outcome="match", unread=0):
    return {
        "job": "nb-1",
        "outcome": outcome,
        "reasons": [] if outcome == "match" else ["inventory-reader: a reason"],
        "accounts": [
            row("inventory-reader", "excess"),
            row("inventory-reader-control", "within"),
        ],
        "proposals": list(proposals),
        "unread_proposals": unread,
    }


class Policy(unittest.TestCase):
    def assert_refused(self, result, reason):
        self.assertFalse(result["allowed"], result)
        self.assertEqual(result["changes"], [])
        self.assertTrue(
            any(reason in r for r in result["reasons"]),
            f"no reason with {reason!r} in {result['reasons']}",
        )

    def test_the_seeds_fix_is_allowed(self):
        result = policy.check(comparison(proposal()), CONFIGURED, CONTRACT)
        self.assertEqual(
            result,
            {
                "allowed": True,
                "reasons": [],
                "changes": [
                    {
                        "account": "inventory-reader",
                        "permission_id": 2,
                        "permission": "inventory-reader: inventory",
                    }
                ],
            },
        )

    def test_a_permission_of_an_account_outside_the_contract_is_refused(self):
        # The delivery account's change permission, which no contract names.
        result = policy.check(
            comparison(proposal(), proposal("aisec-deliver", 7)), CONFIGURED, CONTRACT
        )
        self.assert_refused(result, "aisec-deliver: not an account the checks name")

    def test_a_permission_through_a_group_is_refused(self):
        configured = copy.deepcopy(CONFIGURED)
        reader = configured["accounts"]["inventory-reader"]
        reader["permissions"][1] = dict(UNSCOPED, via="group inventory-readers")
        result = policy.check(comparison(proposal()), configured, CONTRACT)
        self.assert_refused(result, "comes through group inventory-readers")

    def test_removing_the_scoped_permission_is_refused(self):
        result = policy.check(
            comparison(proposal(permission_id=1)), CONFIGURED, CONTRACT
        )
        self.assert_refused(result, "not one the checks call excess")

    def test_a_fix_that_leaves_the_account_missing_is_refused(self):
        cases = json.loads((REPO / "collectors" / "netbox" / "cases.json").read_text())
        sites = dict(cases["cases"])["sites"]["contract"]
        result = policy.check(comparison(proposal()), CONFIGURED, sites)
        self.assert_refused(result, "without permission 2 it is missing, not within")

    def test_a_proposal_for_a_within_account_is_refused(self):
        result = policy.check(
            comparison(proposal(), proposal("inventory-reader-control", 3)),
            CONFIGURED,
            CONTRACT,
        )
        self.assert_refused(
            result, "inventory-reader-control: the checks do not call it excess"
        )

    def test_two_proposals_for_one_account_are_refused(self):
        result = policy.check(
            comparison(proposal(), proposal(permission_id=1)), CONFIGURED, CONTRACT
        )
        self.assert_refused(result, "inventory-reader: 2 proposals, one expected")

    def test_an_excess_account_without_a_proposal_is_refused(self):
        result = policy.check(comparison(), CONFIGURED, CONTRACT)
        self.assert_refused(
            result, "inventory-reader: excess by both checks, and no proposal"
        )

    def test_unread_proposal_lines_refuse_all(self):
        result = policy.check(comparison(proposal(), unread=1), CONFIGURED, CONTRACT)
        self.assert_refused(result, "proposal lines that could not be read: 1")

    def test_a_stop_is_never_a_fix(self):
        result = policy.check(
            comparison(proposal(), outcome="stop"), CONFIGURED, CONTRACT
        )
        self.assert_refused(result, "the comparison's outcome is stop")

    def test_the_same_proposal_twice_counts_once(self):
        # As two agreeing verdict lines count as one.
        result = policy.check(comparison(proposal(), proposal()), CONFIGURED, CONTRACT)
        self.assertTrue(result["allowed"], result)
        self.assertEqual(len(result["changes"]), 1)

    def test_only_remove_is_an_action(self):
        result = policy.check(comparison(proposal(action="add")), CONFIGURED, CONTRACT)
        self.assert_refused(result, "inventory-reader: the action add, not remove")

    def test_a_permission_the_account_does_not_hold_is_refused(self):
        result = policy.check(
            comparison(proposal(permission_id=3)), CONFIGURED, CONTRACT
        )
        self.assert_refused(
            result, "inventory-reader: permission 3 is not one it holds"
        )

    def test_the_checks_must_both_call_an_account_excess(self):
        disagreeing = comparison(proposal())
        disagreeing["accounts"][0] = dict(
            row("inventory-reader", "excess"), observed="within"
        )
        result = policy.check(disagreeing, CONFIGURED, CONTRACT)
        self.assert_refused(
            result, "inventory-reader: the checks do not call it excess"
        )

    def test_nothing_to_fix_is_not_allowed_and_says_so(self):
        within = comparison()
        within["accounts"][0] = row("inventory-reader", "within")
        result = policy.check(within, CONFIGURED, CONTRACT)
        self.assert_refused(result, "no account the checks call excess")


class ImpliedFix(unittest.TestCase):
    def test_the_excess_permissions_are_the_unscoped_one(self):
        self.assertEqual(policy.excess_permissions([SCOPED, UNSCOPED], CONTRACT), [2])
        self.assertEqual(policy.excess_permissions([CONTROL], CONTRACT), [])

    def test_the_seeds_implied_fix_removes_the_unscoped_permission(self):
        self.assertEqual(policy.implied_fix([SCOPED, UNSCOPED], CONTRACT), [2])

    def test_no_fix_is_implied_where_removal_leaves_the_account_missing(self):
        cases = json.loads((REPO / "collectors" / "netbox" / "cases.json").read_text())
        sites = dict(cases["cases"])["sites"]["contract"]
        self.assertIsNone(policy.implied_fix([SCOPED, UNSCOPED], sites))

    def test_a_within_account_needs_no_fix(self):
        self.assertEqual(policy.implied_fix([CONTROL], CONTRACT), [])


FIXTURE = json.loads(
    (REPO / "collectors" / "netbox" / "tests" / "network.json").read_text(
        encoding="utf-8"
    )
)
NETWORK_CONTRACT = dict(CONTRACT, network=FIXTURE["network"])
RULES = {"commit": "c" * 40, "sha256": "d" * 64, "rules": FIXTURE["rules"]}
WITHIN = {
    "check": "configured",
    "accounts": {
        "inventory-reader": {"verdict": "within", "permissions": [SCOPED]},
        "inventory-reader-control": {"verdict": "within", "permissions": [CONTROL]},
    },
}


def viewpoints(*proposals, staging="excess", accounts="within"):
    return {
        "job": "nb-1",
        "outcome": "match",
        "reasons": [],
        "accounts": [
            row("inventory-reader", accounts),
            row("inventory-reader-control", "within"),
            row("viewpoint-consumer", "within"),
            row("viewpoint-staging", staging),
        ],
        "proposals": list(proposals),
        "unread_proposals": 0,
    }


class Viewpoints(unittest.TestCase):
    """A fix for NetBox's port rules (ADR 0056)."""

    assert_refused = Policy.assert_refused

    def test_the_seeds_rule_and_its_outbound_half_are_allowed(self):
        result = policy.check(
            viewpoints(proposal("viewpoint-staging", 1120)),
            WITHIN,
            NETWORK_CONTRACT,
            RULES,
        )
        self.assertTrue(result["allowed"], result["reasons"])
        (change,) = result["changes"]
        self.assertEqual(
            (change["account"], change["rule"], change["priority"], change["commit"]),
            ("viewpoint-staging", "allow-netbox-from-rehearsal", 1120, "c" * 40),
        )
        self.assertEqual(
            [(r["subnet"], r["direction"]) for r in change["removed"]],
            [("netbox", "Inbound"), ("rehearsal", "Outbound")],
        )

    def test_the_consumers_rule_is_refused(self):
        self.assert_refused(
            policy.check(
                viewpoints(proposal("viewpoint-staging", 1110)),
                WITHIN,
                NETWORK_CONTRACT,
                RULES,
            ),
            "does not let staging in",
        )

    def test_a_priority_that_names_no_rule_is_refused(self):
        self.assert_refused(
            policy.check(
                viewpoints(proposal("viewpoint-staging", 1130)),
                WITHIN,
                NETWORK_CONTRACT,
                RULES,
            ),
            "no inbound rule of priority 1130",
        )

    def test_a_rule_whose_removal_cuts_another_viewpoint_is_refused(self):
        rules = json.loads(json.dumps(RULES))
        # One wide rule lets both in: removing it cuts the consumer too.
        wide = dict(rules["rules"]["netbox"][1], source_address_prefix="10.50.0.0/20")
        rules["rules"]["netbox"] = [wide]
        self.assert_refused(
            policy.check(
                viewpoints(proposal("viewpoint-staging", 1120)),
                WITHIN,
                NETWORK_CONTRACT,
                rules,
            ),
            "viewpoint-consumer is missing, not within",
        )

    def test_a_rule_that_leaves_the_viewpoint_open_is_refused(self):
        rules = json.loads(json.dumps(RULES))
        # A second pair of rules keeps the path open without the first.
        for subnet, at in (("netbox", 1), ("rehearsal", 0)):
            second = dict(
                rules["rules"][subnet][at], name="allow-netbox-again", priority=1130
            )
            rules["rules"][subnet].append(second)
        self.assert_refused(
            policy.check(
                viewpoints(proposal("viewpoint-staging", 1120)),
                WITHIN,
                NETWORK_CONTRACT,
                rules,
            ),
            "without rule 1120 it is excess, not within",
        )

    def test_a_viewpoint_the_checks_do_not_call_excess_is_refused(self):
        self.assert_refused(
            policy.check(
                viewpoints(proposal("viewpoint-consumer", 1110), staging="within"),
                WITHIN,
                NETWORK_CONTRACT,
                RULES,
            ),
            "the checks do not call it excess",
        )

    def test_a_job_without_its_rules_is_refused(self):
        self.assert_refused(
            policy.check(
                viewpoints(proposal("viewpoint-staging", 1120)),
                WITHIN,
                NETWORK_CONTRACT,
                None,
            ),
            "no rules",
        )

    def test_another_action_is_refused(self):
        self.assert_refused(
            policy.check(
                viewpoints(proposal("viewpoint-staging", 1120, action="add")),
                WITHIN,
                NETWORK_CONTRACT,
                RULES,
            ),
            "not remove",
        )

    def test_a_fix_for_permissions_and_rules_together_is_refused(self):
        self.assert_refused(
            policy.check(
                viewpoints(
                    proposal("viewpoint-staging", 1120),
                    proposal("inventory-reader", 2),
                    accounts="excess",
                ),
                CONFIGURED,
                NETWORK_CONTRACT,
                RULES,
            ),
            "not both",
        )


if __name__ == "__main__":
    unittest.main()
