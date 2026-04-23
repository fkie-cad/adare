from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from adare.core.result import Result
from adare.webapi.adapters import (
    actions_to_yaml,
    result_to_response,
    serialize_value,
    yaml_to_actions,
)


# ---------------------------------------------------------------------------
# serialize_value
# ---------------------------------------------------------------------------
class TestSerializeValuePrimitives:
    def test_none(self):
        assert serialize_value(None) is None

    def test_string(self):
        assert serialize_value("hello") == "hello"

    def test_int(self):
        assert serialize_value(42) == 42

    def test_float(self):
        assert serialize_value(3.14) == 3.14

    def test_bool(self):
        assert serialize_value(True) is True
        assert serialize_value(False) is False


class TestSerializeValuePath:
    def test_path(self):
        p = Path("/tmp/test.txt")
        assert serialize_value(p) == str(p)

    def test_path_in_dict(self):
        d = {"file": Path("/data/file.csv")}
        result = serialize_value(d)
        assert result == {"file": str(Path("/data/file.csv"))}


class TestSerializeValueDatetime:
    def test_naive_datetime(self):
        dt = datetime(2025, 1, 15, 10, 30, 0)
        assert serialize_value(dt) == "2025-01-15T10:30:00"

    def test_aware_datetime(self):
        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = serialize_value(dt)
        assert result == "2025-06-01T12:00:00+00:00"

    def test_datetime_with_microseconds(self):
        dt = datetime(2025, 3, 20, 8, 15, 30, 123456)
        assert serialize_value(dt) == "2025-03-20T08:15:30.123456"


class TestSerializeValueDict:
    def test_empty_dict(self):
        assert serialize_value({}) == {}

    def test_simple_dict(self):
        d = {"a": 1, "b": "two"}
        assert serialize_value(d) == {"a": 1, "b": "two"}

    def test_nested_dict(self):
        d = {"outer": {"inner": "value"}}
        assert serialize_value(d) == {"outer": {"inner": "value"}}

    def test_dict_with_mixed_types(self):
        dt = datetime(2025, 1, 1, 0, 0, 0)
        d = {
            "name": "test",
            "path": Path("/tmp/x"),
            "when": dt,
            "count": 5,
        }
        result = serialize_value(d)
        assert result["name"] == "test"
        assert result["path"] == str(Path("/tmp/x"))
        assert result["when"] == "2025-01-01T00:00:00"
        assert result["count"] == 5

    def test_deeply_nested_dict(self):
        d = {"a": {"b": {"c": {"d": Path("/deep")}}}}
        result = serialize_value(d)
        assert result == {"a": {"b": {"c": {"d": str(Path("/deep"))}}}}


class TestSerializeValueList:
    def test_empty_list(self):
        assert serialize_value([]) == []

    def test_simple_list(self):
        assert serialize_value([1, 2, 3]) == [1, 2, 3]

    def test_list_with_paths(self):
        items = [Path("/a"), Path("/b")]
        result = serialize_value(items)
        assert result == [str(Path("/a")), str(Path("/b"))]

    def test_tuple_converted_to_list(self):
        result = serialize_value((1, 2, 3))
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_list_of_dicts(self):
        items = [{"x": 1}, {"y": Path("/z")}]
        result = serialize_value(items)
        assert result == [{"x": 1}, {"y": str(Path("/z"))}]


class TestSerializeValueObjects:
    def test_dataclass(self):
        @dataclass
        class Info:
            name: str
            count: int

        obj = Info(name="test", count=7)
        result = serialize_value(obj)
        assert result == {"name": "test", "count": 7}

    def test_dataclass_with_path_field(self):
        @dataclass
        class FileInfo:
            path: Path
            size: int

        obj = FileInfo(path=Path("/data/file.bin"), size=1024)
        result = serialize_value(obj)
        assert result["path"] == str(Path("/data/file.bin"))
        assert result["size"] == 1024

    def test_dataclass_with_nested_dataclass(self):
        @dataclass
        class Inner:
            value: int

        @dataclass
        class Outer:
            inner: Inner
            label: str

        obj = Outer(inner=Inner(value=42), label="wrap")
        result = serialize_value(obj)
        assert result == {"inner": {"value": 42}, "label": "wrap"}

    def test_plain_object(self):
        class Bag:
            def __init__(self):
                self.x = 10
                self.y = "hello"

        result = serialize_value(Bag())
        assert result == {"x": 10, "y": "hello"}


# ---------------------------------------------------------------------------
# result_to_response
# ---------------------------------------------------------------------------
class TestResultToResponseSuccess:
    def test_simple_data(self):
        r = Result.ok("hello")
        resp = result_to_response(r)
        assert resp["success"] is True
        assert resp["data"] == "hello"
        assert "error" not in resp

    def test_none_data(self):
        r = Result.ok(None)
        resp = result_to_response(r)
        assert resp["success"] is True
        assert resp["data"] is None

    def test_dict_data(self):
        r = Result.ok({"key": "value", "num": 3})
        resp = result_to_response(r)
        assert resp["data"] == {"key": "value", "num": 3}

    def test_data_with_path(self):
        r = Result.ok({"file": Path("/tmp/out.log")})
        resp = result_to_response(r)
        assert resp["data"]["file"] == str(Path("/tmp/out.log"))

    def test_data_with_datetime(self):
        dt = datetime(2025, 5, 10, 14, 30, 0)
        r = Result.ok(dt)
        resp = result_to_response(r)
        assert resp["data"] == "2025-05-10T14:30:00"


class TestResultToResponseFailure:
    def test_basic_error(self):
        r = Result.fail("NOT_FOUND", "Item not found")
        resp = result_to_response(r)
        assert resp["success"] is False
        assert "error" in resp
        assert resp["error"]["code"] == "NOT_FOUND"
        assert resp["error"]["message"] == "Item not found"
        assert "data" not in resp

    def test_error_with_solutions(self):
        r = Result.fail("DUPLICATE", "Already exists", solutions=["Rename it"])
        resp = result_to_response(r)
        assert resp["error"]["solutions"] == ["Rename it"]

    def test_error_without_solutions(self):
        r = Result.fail("ERR", "Something went wrong")
        resp = result_to_response(r)
        assert resp["error"]["solutions"] == []

    def test_error_with_none_error_object(self):
        """Result with success=False but error=None should produce safe defaults."""
        r = Result(success=False, error=None)
        resp = result_to_response(r)
        assert resp["success"] is False
        assert resp["error"]["code"] == "UNKNOWN"
        assert resp["error"]["message"] == "Unknown error"


# ---------------------------------------------------------------------------
# actions_to_yaml / yaml_to_actions round-trip
# ---------------------------------------------------------------------------
class TestActionsToYaml:
    def test_basic_conversion(self):
        actions = [{"type": "click", "target": "button1"}]
        settings = {"idle": 5, "timeout": 30}
        yaml_str = actions_to_yaml(actions, settings)

        assert "settings:" in yaml_str
        assert "actions:" in yaml_str
        assert "click" in yaml_str

    def test_empty_actions(self):
        yaml_str = actions_to_yaml([], {})
        assert "settings:" in yaml_str
        assert "actions:" in yaml_str

    def test_multiple_actions(self):
        actions = [
            {"type": "click", "x": 100, "y": 200},
            {"type": "type", "text": "hello"},
            {"type": "wait", "seconds": 2},
        ]
        settings = {"idle": 1}
        yaml_str = actions_to_yaml(actions, settings)
        assert "click" in yaml_str
        assert "hello" in yaml_str
        assert "wait" in yaml_str


class TestYamlToActions:
    def test_basic_parse(self):
        yaml_content = """
settings:
  idle: 5
  timeout: 30
actions:
  - type: click
    target: button1
"""
        actions, settings = yaml_to_actions(yaml_content)
        assert len(actions) == 1
        assert actions[0]["type"] == "click"
        assert actions[0]["target"] == "button1"
        assert settings["idle"] == 5
        assert settings["timeout"] == 30

    def test_missing_actions_key(self):
        yaml_content = """
settings:
  idle: 1
"""
        actions, settings = yaml_to_actions(yaml_content)
        assert actions == []
        assert settings["idle"] == 1

    def test_missing_settings_key(self):
        yaml_content = """
actions:
  - type: wait
    seconds: 3
"""
        actions, settings = yaml_to_actions(yaml_content)
        assert len(actions) == 1
        assert settings == {}

    def test_empty_document(self):
        yaml_content = "{}"
        actions, settings = yaml_to_actions(yaml_content)
        assert actions == []
        assert settings == {}


class TestYamlRoundTrip:
    def test_round_trip_preserves_data(self):
        original_actions = [
            {"type": "click", "x": 100, "y": 200},
            {"type": "type", "text": "user@example.com"},
        ]
        original_settings = {"idle": 3, "timeout": 60, "retries": 2}

        yaml_str = actions_to_yaml(original_actions, original_settings)
        recovered_actions, recovered_settings = yaml_to_actions(yaml_str)

        assert recovered_actions == original_actions
        assert recovered_settings == original_settings

    def test_round_trip_empty(self):
        yaml_str = actions_to_yaml([], {})
        actions, settings = yaml_to_actions(yaml_str)
        assert actions == []
        assert settings == {}

    def test_round_trip_nested_action_data(self):
        actions = [
            {
                "type": "fill_form",
                "fields": {
                    "name": "John",
                    "address": {"street": "123 Main St", "city": "Anytown"},
                },
            }
        ]
        settings = {"mode": "fast"}
        yaml_str = actions_to_yaml(actions, settings)
        recovered_actions, recovered_settings = yaml_to_actions(yaml_str)
        assert recovered_actions == actions
        assert recovered_settings == settings
