"""Tests for adarelib.common.variables module."""

import pytest

from adarelib.common.variables import (
    TimestampMetadata,
    ValidationError,
    Variable,
    VariableRegistry,
    VariableType,
)


# ---------------------------------------------------------------------------
# TimestampMetadata
# ---------------------------------------------------------------------------

class TestTimestampMetadata:

    def test_to_dict_all_fields(self):
        meta = TimestampMetadata(
            timezone="UTC",
            format_str="%Y-%m-%d",
            tolerance_upper=5,
            tolerance_lower=3,
            localtime=True,
        )
        result = meta.to_dict()
        assert result == {
            "timezone": "UTC",
            "format": "%Y-%m-%d",
            "tolerance": [5, 3],
            "localtime": True,
        }

    def test_from_dict_roundtrip(self):
        original = TimestampMetadata(
            timezone="US/Eastern",
            format_str="%H:%M",
            tolerance_upper=10,
            tolerance_lower=20,
            localtime=True,
        )
        restored = TimestampMetadata.from_dict(original.to_dict())
        assert restored.timezone == original.timezone
        assert restored.format_str == original.format_str
        assert restored.tolerance_upper == original.tolerance_upper
        assert restored.tolerance_lower == original.tolerance_lower
        assert restored.localtime == original.localtime

    def test_from_dict_single_tolerance_creates_symmetric(self):
        data = {"tolerance": 7}
        meta = TimestampMetadata.from_dict(data)
        assert meta.tolerance_upper == 7
        assert meta.tolerance_lower == 7


# ---------------------------------------------------------------------------
# Variable.auto_infer -- type inference
# ---------------------------------------------------------------------------

class TestVariableAutoInfer:

    def test_boolean(self):
        var = Variable.auto_infer(True)
        assert var.type == VariableType.BOOLEAN
        assert var.value is True

    def test_integer(self):
        var = Variable.auto_infer(42)
        assert var.type == VariableType.INTEGER
        assert var.value == 42

    def test_float(self):
        var = Variable.auto_infer(3.14)
        assert var.type == VariableType.FLOAT
        assert var.value == 3.14

    def test_list(self):
        var = Variable.auto_infer([1, 2])
        assert var.type == VariableType.LIST
        assert var.value == [1, 2]

    def test_dict(self):
        var = Variable.auto_infer({"a": 1})
        assert var.type == VariableType.DICT
        assert var.value == {"a": 1}

    def test_string(self):
        var = Variable.auto_infer("hello")
        assert var.type == VariableType.STRING
        assert var.value == "hello"

    def test_path(self):
        var = Variable.auto_infer("/usr/bin/file")
        assert var.type == VariableType.PATH
        assert var.value == "/usr/bin/file"


# ---------------------------------------------------------------------------
# Variable validation / coercion
# ---------------------------------------------------------------------------

class TestVariableValidation:

    def test_string_coerces_int(self):
        var = Variable(value=42, type=VariableType.STRING)
        assert var.value == "42"
        assert isinstance(var.value, str)

    def test_boolean_coerces_true_string(self):
        var = Variable(value="true", type=VariableType.BOOLEAN)
        assert var.value is True

    def test_boolean_coerces_false_string(self):
        var = Variable(value="false", type=VariableType.BOOLEAN)
        assert var.value is False

    def test_regex_valid_pattern(self):
        var = Variable(value=r"^foo\d+$", type=VariableType.REGEX)
        assert var.value == r"^foo\d+$"

    def test_regex_invalid_pattern_raises(self):
        with pytest.raises(ValidationError, match="Invalid regex"):
            Variable(value="[unclosed", type=VariableType.REGEX)


# ---------------------------------------------------------------------------
# VariableRegistry
# ---------------------------------------------------------------------------

class TestVariableRegistry:

    def test_add_and_get(self):
        registry = VariableRegistry()
        var = Variable(value="world", type=VariableType.STRING)
        registry.add("greeting", var)

        retrieved = registry.get("greeting")
        assert retrieved is var
        assert retrieved.value == "world"

    def test_resolve_in_string_replaces_variable(self):
        registry = VariableRegistry()
        registry.add("name", Variable(value="Alice", type=VariableType.STRING))
        result = registry.resolve_in_string("Hello {{name}}!")
        assert result == "Hello Alice!"

    def test_resolve_in_string_unknown_var_unchanged(self):
        registry = VariableRegistry()
        text = "Hello {{unknown}}!"
        result = registry.resolve_in_string(text)
        assert result == "Hello {{unknown}}!"

    def test_to_dict_returns_string_values(self):
        registry = VariableRegistry()
        registry.add("count", Variable(value=5, type=VariableType.INTEGER))
        registry.add("flag", Variable(value=True, type=VariableType.BOOLEAN))
        result = registry.to_dict()
        assert result == {"count": "5", "flag": "true"}

    def test_from_dict_explicit_type_dicts(self):
        data = {
            "host": {"type": "string", "value": "localhost"},
            "port": {"type": "integer", "value": 8080},
        }
        registry = VariableRegistry.from_dict(data)
        assert registry.get("host").type == VariableType.STRING
        assert registry.get("host").value == "localhost"
        assert registry.get("port").type == VariableType.INTEGER
        assert registry.get("port").value == 8080

    def test_from_dict_auto_inferred(self):
        data = {
            "name": "hello",
            "count": 42,
            "enabled": True,
        }
        registry = VariableRegistry.from_dict(data)
        assert registry.get("name").type == VariableType.STRING
        assert registry.get("count").type == VariableType.INTEGER
        assert registry.get("enabled").type == VariableType.BOOLEAN
