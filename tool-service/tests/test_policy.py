"""The policy file as it ships. The rules are data, so the data is checked."""

import json
from pathlib import Path

import jsonschema

FILE = Path(__file__).parent.parent.parent / "policies" / "tool-service.json"
POLICY = json.loads(FILE.read_text(encoding="utf-8"))


def schemas():
    yield POLICY["message_schema"]
    yield POLICY["registration_schema"]
    for tool in POLICY["tools"].values():
        yield tool["input_schema"]


def test_every_schema_is_a_valid_schema():
    for schema in schemas():
        jsonschema.Draft202012Validator.check_schema(schema)


def test_every_object_schema_refuses_fields_it_does_not_name():
    assert POLICY["registration_schema"]["additionalProperties"] is False
    for tool in POLICY["tools"].values():
        assert tool["input_schema"]["additionalProperties"] is False


def test_every_pattern_is_anchored_at_both_ends():
    """`$` lets a trailing newline through in Python. The patterns end with
    a lookahead that nothing follows."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("pattern"), str):
                found.append(node["pattern"])
            for value in node.values():
                walk(value)

    for schema in schemas():
        walk(schema)
    assert found
    for pattern in found:
        assert pattern.startswith("^")
        assert pattern.endswith("(?![\\s\\S])")


def test_every_target_names_tools_the_policy_has():
    for target in POLICY["targets"].values():
        assert target["tools"]
        assert set(target["tools"]) <= set(POLICY["tools"])


def test_the_limits_are_small_positive_numbers():
    assert set(POLICY["limits"]) == {"request_bytes", "result_bytes", "calls_per_job"}
    for value in POLICY["limits"].values():
        assert type(value) is int
        assert 0 < value <= 65536
