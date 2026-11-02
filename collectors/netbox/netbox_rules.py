"""NetBox's port rules from the targets repository, judged for each viewpoint
of the contract's network part (ADR 0056).

The configured half of exercise 2. The rules file is
infra/targets/netbox-rules.json in the targets repository: for each target
subnet, the security rules about NetBox's port. Azure reads a subnet's rules
by priority, lowest first, and the first rule that matches decides. Every
subnet ends in a deny of everything at 4096, the network module's baseline. So
a connection from a viewpoint reaches the port only when the viewpoint's
subnet lets it out and NetBox's subnet lets it in.

The file holds the rules that name a target subnet. The rules main.tf keeps
(the orchestrator's, SSH, and the denies of the internet and Azure DNS) match
no target address on NetBox's port, so the file and the baseline decide. A
rule that would decide but has an address this module cannot read, such as a
service tag, makes the viewpoint's verdict unknown.

The file is target side: a pull request from a compromised worker could have
shaped it. So it is read with limits, and nothing in it but names and
addresses that match a pattern goes on.

Standard library only.
"""

import ipaddress
import json
import re

FIELDS = {
    "name",
    "priority",
    "direction",
    "access",
    "protocol",
    "source_address_prefix",
    "destination_address_prefix",
    "destination_port_range",
    "description",
}
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
SUBNET = re.compile(r"[a-z][a-z0-9-]{0,31}")
# viewpoint-NAME is a name in the job's schema, which takes 64 characters.
VIEW = re.compile(r"[a-z0-9][a-z0-9-]{0,53}")
PREFIX = re.compile(r"\*|[A-Za-z0-9./:]{1,64}")
PORTS = re.compile(r"\*|([0-9]{1,5})(?:-([0-9]{1,5}))?")
PROTOCOLS = ("Tcp", "Udp", "Icmp", "Esp", "Ah", "*")
MAX_SUBNETS = 16
MAX_RULES = 50
MAX_BYTES = 64 << 10
VIEWPOINT = "viewpoint-"


class Invalid(Exception):
    pass


def load(text):
    """The rules file as an object of subnets, each a list of rules, if it is
    in shape. Raises Invalid with the first thing that is not."""
    if len(text) > MAX_BYTES:
        raise Invalid(f"more than {MAX_BYTES} bytes")
    try:
        rules = json.loads(text)
    except ValueError:
        raise Invalid("not JSON") from None
    if not isinstance(rules, dict) or not 0 < len(rules) <= MAX_SUBNETS:
        raise Invalid("not an object of subnets")
    for subnet, found in rules.items():
        if not SUBNET.fullmatch(subnet):
            raise Invalid("a subnet's name out of pattern")
        if not isinstance(found, list) or len(found) > MAX_RULES:
            raise Invalid(f"{subnet}: not a list of rules")
        seen = set()
        for rule in found:
            if not (isinstance(rule, dict) and set(rule) == FIELDS):
                raise Invalid(f"{subnet}: a rule without the rule fields")
            if not (isinstance(rule["name"], str) and NAME.fullmatch(rule["name"])):
                raise Invalid(f"{subnet}: a rule's name out of pattern")
            name, priority = rule["name"], rule["priority"]
            if not (type(priority) is int and 100 <= priority <= 4096):
                raise Invalid(f"{subnet} {name}: not a priority")
            if rule["direction"] not in ("Inbound", "Outbound"):
                raise Invalid(f"{subnet} {name}: not a direction")
            if rule["access"] not in ("Allow", "Deny"):
                raise Invalid(f"{subnet} {name}: not an access")
            if rule["protocol"] not in PROTOCOLS:
                raise Invalid(f"{subnet} {name}: not a protocol")
            for field in ("source_address_prefix", "destination_address_prefix"):
                if not (isinstance(rule[field], str) and PREFIX.fullmatch(rule[field])):
                    raise Invalid(f"{subnet} {name}: {field} out of pattern")
            ports = rule["destination_port_range"]
            if not (isinstance(ports, str) and PORTS.fullmatch(ports)):
                raise Invalid(f"{subnet} {name}: not a port range")
            if not (
                isinstance(rule["description"], str) and len(rule["description"]) <= 140
            ):
                raise Invalid(f"{subnet} {name}: not a description")
            # Azure refuses two rules with one name, or one direction's
            # priority twice, in a group.
            for key in (("name", name), (rule["direction"], priority)):
                if key in seen:
                    raise Invalid(f"{subnet}: {key[0]} {key[1]} twice")
                seen.add(key)
    return rules


def network_in_shape(network):
    """Whether a contract's network part is in shape: NetBox's address, port,
    and subnet, and viewpoints, each an address in a subnet that the contract
    says should reach the port (open) or not (closed)."""

    def address(value):
        try:
            return isinstance(value, str) and bool(ipaddress.ip_address(value))
        except ValueError:
            return False

    views = network.get("viewpoints") if isinstance(network, dict) else None
    return (
        isinstance(network, dict)
        and set(network) == {"address", "port", "subnet", "viewpoints"}
        and address(network["address"])
        and type(network["port"]) is int
        and 0 < network["port"] < 65536
        and isinstance(network["subnet"], str)
        and bool(SUBNET.fullmatch(network["subnet"]))
        and isinstance(views, dict)
        and 0 < len(views) <= 8
        and all(
            isinstance(name, str)
            and VIEW.fullmatch(name)
            and isinstance(view, dict)
            and set(view) == {"address", "subnet", "reach"}
            and address(view["address"])
            and isinstance(view["subnet"], str)
            and SUBNET.fullmatch(view["subnet"])
            and view["reach"] in ("open", "closed")
            for name, view in views.items()
        )
    )


def holds(prefix, address):
    """Whether an address prefix holds an address: True, False, or None for a
    prefix this module cannot read, such as a service tag."""
    if prefix == "*":
        return True
    try:
        return ipaddress.ip_address(address) in ipaddress.ip_network(
            prefix, strict=False
        )
    except ValueError:
        return None


def covers(ports, port):
    if ports == "*":
        return True
    found = PORTS.fullmatch(ports)
    return int(found[1]) <= port <= int(found[2] or found[1])


def decide(rules, direction, source, destination, port):
    """The access that decides a TCP connection in one direction, and the rule
    that gave it: (Allow or Deny, rule), (Deny, None) for the baseline, or
    (None, rule) for a rule that may match and cannot be read."""
    for rule in sorted(
        (r for r in rules if r["direction"] == direction), key=lambda r: r["priority"]
    ):
        if rule["protocol"] not in ("Tcp", "*"):
            continue
        matches = (
            holds(rule["source_address_prefix"], source),
            holds(rule["destination_address_prefix"], destination),
            covers(rule["destination_port_range"], port),
        )
        if False in matches:
            continue
        if None in matches:
            return None, rule
        return rule["access"], rule
    return "Deny", None


def judge(rules, network, name):
    """The configured verdict for one viewpoint: its reasons and the rules that
    decided, each with its subnet, name, priority, and access."""
    view = network["viewpoints"][name]
    target, port = network["address"], network["port"]
    decided, reasons, admitted = [], [], True
    for subnet, direction in (
        (view["subnet"], "Outbound"),
        (network["subnet"], "Inbound"),
    ):
        access, rule = decide(
            rules.get(subnet, []), direction, view["address"], target, port
        )
        if access is None:
            why = f"{subnet} {rule['name']}: an address this check cannot read"
            reasons.append({"kind": "unknown", "why": why})
            admitted = None
            continue
        decided.append(
            {
                "subnet": subnet,
                "direction": direction,
                "name": rule["name"] if rule else "the baseline",
                "priority": rule["priority"] if rule else 4096,
                "access": access,
            }
        )
        if access == "Deny" and admitted is not None:
            admitted = False
    expected = view["reach"] == "open"
    path = f"{view['address']} to {target}:{port}"
    if admitted is None:
        pass
    elif admitted and not expected:
        reasons.append({"kind": "excess", "why": f"the rules let {path} through"})
    elif not admitted and expected:
        reasons.append({"kind": "missing", "why": f"the rules stop {path}"})
    kinds = [r["kind"] for r in reasons]
    found = next((k for k in ("excess", "missing", "unknown") if k in kinds), "within")
    return {"verdict": found, "reasons": reasons, "rules": decided}


def configured(rules, network):
    return {name: judge(rules, network, name) for name in network["viewpoints"]}


def change(rules, network, name, priority):
    """The rules without the inbound allow of that priority on NetBox's subnet,
    and without its outbound half: the rule of the same name that lets the
    viewpoint's subnet out to the port. Returns the new rules and what was
    removed. Raises Invalid when the priority names no such rule."""
    view = network["viewpoints"].get(name)
    if view is None:
        raise Invalid(f"no viewpoint {name} in the contract")
    target, port = network["address"], network["port"]
    inbound = [
        r
        for r in rules.get(network["subnet"], [])
        if r["direction"] == "Inbound" and r["priority"] == priority
    ]
    if len(inbound) != 1:
        raise Invalid(f"no inbound rule of priority {priority} on {network['subnet']}")
    rule = inbound[0]
    if rule["access"] != "Allow":
        raise Invalid(f"rule {priority} is a deny")
    if not (
        holds(rule["source_address_prefix"], view["address"])
        and holds(rule["destination_address_prefix"], target)
        and covers(rule["destination_port_range"], port)
    ):
        raise Invalid(f"rule {priority} does not let {name} in to the port")
    removed = [(network["subnet"], rule)]
    if view["subnet"] != network["subnet"]:
        removed += [
            (view["subnet"], r)
            for r in rules.get(view["subnet"], [])
            if r["direction"] == "Outbound"
            and r["name"] == rule["name"]
            and r["access"] == "Allow"
            and holds(r["destination_address_prefix"], target)
            and covers(r["destination_port_range"], port)
        ]
    left = {
        subnet: [
            r for r in found if not any(r is gone for s, gone in removed if s == subnet)
        ]
        for subnet, found in rules.items()
    }
    gone = [
        {
            "subnet": subnet,
            "direction": r["direction"],
            "name": r["name"],
            "priority": r["priority"],
        }
        for subnet, r in removed
    ]
    return left, gone


def facts(rules):
    """The rules as the job reads them: no description, which is free text."""
    return {
        subnet: [
            {
                "name": r["name"],
                "priority": r["priority"],
                "direction": r["direction"],
                "access": r["access"],
                "protocol": r["protocol"],
                "source": r["source_address_prefix"],
                "destination": r["destination_address_prefix"],
                "ports": r["destination_port_range"],
            }
            for r in found
        ]
        for subnet, found in rules.items()
    }


def dump(rules):
    """The rules file's own layout, so an edit changes only its lines."""
    return json.dumps(rules, indent=2) + "\n"
