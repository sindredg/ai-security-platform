"""The policy file as it ships. The rules are data, so the data is checked."""

import json
import re
from pathlib import Path

import jsonschema
import pytest

FILE = Path(__file__).parent.parent.parent / "policies" / "tool-service.json"
POLICY = json.loads(FILE.read_text(encoding="utf-8"))
REFERENCE = re.compile(r"ev-[0-9]{4}")


def schemas():
    yield POLICY["message_schema"]
    yield POLICY["registration_schema"]
    for tool in POLICY["tools"].values():
        yield tool["input_schema"]
    yield from POLICY["evidence_schemas"].values()


def nodes(node):
    """Every object inside a schema, lists included."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from nodes(value)


def test_every_schema_is_a_valid_schema():
    for schema in schemas():
        jsonschema.Draft202012Validator.check_schema(schema)


def test_every_object_schema_refuses_fields_it_does_not_name():
    assert POLICY["registration_schema"]["additionalProperties"] is False
    for tool in POLICY["tools"].values():
        assert tool["input_schema"]["additionalProperties"] is False
    found = 0
    for schema in POLICY["evidence_schemas"].values():
        for node in nodes(schema):
            if node.get("type") == "object" or "properties" in node:
                assert node.get("additionalProperties") is False, node
                found += 1
    assert found


def test_every_pattern_is_anchored_at_both_ends():
    """`$` lets a trailing newline through in Python. The patterns end with
    a lookahead that nothing follows. A key of patternProperties is a pattern
    too."""
    found = []
    for schema in schemas():
        for node in nodes(schema):
            if isinstance(node.get("pattern"), str):
                found.append(node["pattern"])
            found.extend(node.get("patternProperties", {}))
    assert found
    for pattern in found:
        assert pattern.startswith("^")
        assert pattern.endswith("(?![\\s\\S])")


def test_every_target_names_tools_the_policy_has():
    for target in POLICY["targets"].values():
        assert target["tools"]
        assert set(target["tools"]) <= set(POLICY["tools"])


def test_every_target_names_a_store_and_kinds_the_policy_has():
    used = set()
    for target in POLICY["targets"].values():
        assert target["store"] in ("shared", "per-job")
        assert target["evidence"]
        for reference, kind in target["evidence"].items():
            assert REFERENCE.fullmatch(reference)
            assert kind in POLICY["evidence_schemas"]
            used.add(kind)
    assert used == set(POLICY["evidence_schemas"])


def test_a_netbox_kind_accepts_its_own_reference_only():
    evidence = POLICY["targets"]["netbox"]["evidence"]
    for reference, kind in evidence.items():
        schema = POLICY["evidence_schemas"][kind]["properties"]["reference"]
        jsonschema.validate(reference, schema)
        for other in set(evidence) - {reference}:
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(other, schema)


def test_the_limits_are_small_positive_numbers():
    assert set(POLICY["limits"]) == {
        "request_bytes",
        "result_bytes",
        "calls_per_job",
        "untrusted_per_minute",
    }
    for value in POLICY["limits"].values():
        assert type(value) is int
        assert 0 < value <= 65536
