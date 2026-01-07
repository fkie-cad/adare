"""
Unit tests for adare.helperfunctions module.

Tests pure utility functions that do not require file system I/O or mocking.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path


class TestStringsReplace:
    """Tests for adare.helperfunctions.strings.replace module."""

    def test_replace_multiple_strings_basic(self):
        """Test replacing multiple characters with a single replacement."""
        from adare.helperfunctions.strings.replace import replace_multiple_strings

        result = replace_multiple_strings("hello-world_test", ["-", "_"], " ")
        assert result == "hello world test"

    def test_replace_multiple_strings_empty_characters(self):
        """Test with empty characters list (no replacements)."""
        from adare.helperfunctions.strings.replace import replace_multiple_strings

        result = replace_multiple_strings("hello world", [], "_")
        assert result == "hello world"

    def test_replace_multiple_strings_no_matches(self):
        """Test when no characters match."""
        from adare.helperfunctions.strings.replace import replace_multiple_strings

        result = replace_multiple_strings("hello world", ["x", "y", "z"], "_")
        assert result == "hello world"

    def test_replace_multiple_strings_all_replaced(self):
        """Test when all characters are replaced."""
        from adare.helperfunctions.strings.replace import replace_multiple_strings

        result = replace_multiple_strings("a-b-c", ["a", "b", "c", "-"], "X")
        assert result == "XXXXX"  # "a-b-c" has 5 characters

    def test_replace_multiple_strings_empty_string(self):
        """Test with empty input string."""
        from adare.helperfunctions.strings.replace import replace_multiple_strings

        result = replace_multiple_strings("", ["a", "b"], "_")
        assert result == ""


class TestString:
    """Tests for adare.helperfunctions.string module."""

    def test_make_string_path_safe_basic(self):
        """Test basic path safety conversion."""
        from adare.helperfunctions.string import make_string_path_safe

        result = make_string_path_safe("hello world")
        assert result == "hello_world"

    def test_make_string_path_safe_multiple_unsafe(self):
        """Test with multiple unsafe characters."""
        from adare.helperfunctions.string import make_string_path_safe

        result = make_string_path_safe("file:name/with\\special*chars?test")
        assert "_" in result
        assert "/" not in result
        assert "\\" not in result
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result

    def test_make_string_path_safe_already_safe(self):
        """Test with already safe string."""
        from adare.helperfunctions.string import make_string_path_safe

        result = make_string_path_safe("already_safe_string")
        assert result == "already_safe_string"

    def test_make_string_path_safe_empty(self):
        """Test with empty string."""
        from adare.helperfunctions.string import make_string_path_safe

        result = make_string_path_safe("")
        assert result == ""

    def test_make_string_path_safe_all_unsafe(self):
        """Test string with all unsafe characters."""
        from adare.helperfunctions.string import make_string_path_safe

        result = make_string_path_safe(" /\\:*?\"<>|-")
        assert all(c == "_" for c in result)


class TestDict:
    """Tests for adare.helperfunctions.dict.dict module."""

    def test_get_value_if_missing_key_existing_key(self):
        """Test with existing key."""
        from adare.helperfunctions.dict.dict import get_value_if_missing_key

        d = {"name": "test", "count": 5}
        result = get_value_if_missing_key(d, "name", str)
        assert result == "test"

    def test_get_value_if_missing_key_missing_with_default(self):
        """Test with missing key and explicit default."""
        from adare.helperfunctions.dict.dict import get_value_if_missing_key

        d = {"name": "test"}
        result = get_value_if_missing_key(d, "missing", str, default="fallback")
        assert result == "fallback"

    def test_get_value_if_missing_key_missing_with_dtype_str(self):
        """Test with missing key, no default, dtype=str."""
        from adare.helperfunctions.dict.dict import get_value_if_missing_key

        d = {"name": "test"}
        result = get_value_if_missing_key(d, "missing", str)
        assert result == ""

    def test_get_value_if_missing_key_missing_with_dtype_int(self):
        """Test with missing key, no default, dtype=int."""
        from adare.helperfunctions.dict.dict import get_value_if_missing_key

        d = {"name": "test"}
        result = get_value_if_missing_key(d, "missing", int)
        assert result == 0

    def test_get_value_if_missing_key_missing_with_dtype_list(self):
        """Test with missing key, no default, dtype=list."""
        from adare.helperfunctions.dict.dict import get_value_if_missing_key

        d = {"name": "test"}
        result = get_value_if_missing_key(d, "missing", list)
        assert result == []

    def test_get_value_if_missing_key_missing_with_dtype_dict(self):
        """Test with missing key, no default, dtype=dict."""
        from adare.helperfunctions.dict.dict import get_value_if_missing_key

        d = {"name": "test"}
        result = get_value_if_missing_key(d, "missing", dict)
        assert result == {}

    def test_get_value_if_missing_key_unknown_dtype(self):
        """Test with unknown dtype returns None."""
        from adare.helperfunctions.dict.dict import get_value_if_missing_key

        d = {"name": "test"}
        result = get_value_if_missing_key(d, "missing", float)
        assert result is None

    def test_get_value_if_missing_key_empty_dict(self):
        """Test with empty dictionary."""
        from adare.helperfunctions.dict.dict import get_value_if_missing_key

        d = {}
        result = get_value_if_missing_key(d, "key", str, default="default")
        assert result == "default"


class TestText:
    """Tests for adare.helperfunctions.text module."""

    def test_slugify_basic(self):
        """Test basic slugify functionality."""
        from adare.helperfunctions.text import slugify

        result = slugify("Hello World")
        assert result == "hello-world"

    def test_slugify_special_chars(self):
        """Test slugify removes special characters."""
        from adare.helperfunctions.text import slugify

        result = slugify("Hello, World! How are you?")
        assert "," not in result
        assert "!" not in result
        assert "?" not in result

    def test_slugify_multiple_spaces(self):
        """Test slugify converts multiple spaces to single dash."""
        from adare.helperfunctions.text import slugify

        result = slugify("hello   world")
        assert "--" not in result
        assert "hello-world" == result

    def test_slugify_multiple_dashes(self):
        """Test slugify converts multiple dashes to single dash."""
        from adare.helperfunctions.text import slugify

        result = slugify("hello---world")
        assert "--" not in result

    def test_slugify_unicode_ascii_only(self):
        """Test slugify with unicode, converting to ASCII."""
        from adare.helperfunctions.text import slugify

        result = slugify("cafe", allow_unicode=False)
        assert result == "cafe"

    def test_slugify_unicode_allowed(self):
        """Test slugify with unicode allowed."""
        from adare.helperfunctions.text import slugify

        result = slugify("cafe", allow_unicode=True)
        assert "cafe" in result

    def test_slugify_empty_string(self):
        """Test slugify with empty string."""
        from adare.helperfunctions.text import slugify

        result = slugify("")
        assert result == ""

    def test_slugify_strips_leading_trailing(self):
        """Test slugify strips leading/trailing whitespace and dashes."""
        from adare.helperfunctions.text import slugify

        result = slugify("  -hello world-  ")
        assert result == "hello-world"

    def test_clean_rich_inline_str_removes_tags(self):
        """Test cleaning Rich inline tags."""
        from adare.helperfunctions.text import clean_rich_inline_str

        result = clean_rich_inline_str("[bold]Hello[/bold] [red]World[/red]")
        assert result == "Hello World"

    def test_clean_rich_inline_str_complex_tags(self):
        """Test cleaning complex Rich tags."""
        from adare.helperfunctions.text import clean_rich_inline_str

        result = clean_rich_inline_str("[italic red]styled[/italic red] text")
        assert result == "styled text"

    def test_clean_rich_inline_str_no_tags(self):
        """Test with string that has no tags."""
        from adare.helperfunctions.text import clean_rich_inline_str

        result = clean_rich_inline_str("plain text")
        assert result == "plain text"

    def test_clean_rich_inline_str_empty(self):
        """Test with empty string."""
        from adare.helperfunctions.text import clean_rich_inline_str

        result = clean_rich_inline_str("")
        assert result == ""


class TestHash:
    """Tests for adare.helperfunctions.hash module (pure functions only)."""

    def test_hash_dict_sha256_basic(self):
        """Test basic dictionary hashing."""
        from adare.helperfunctions.hash import hash_dict_sha256

        result = hash_dict_sha256({"key": "value"})
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 produces 64 hex chars

    def test_hash_dict_sha256_deterministic(self):
        """Test that same dict produces same hash."""
        from adare.helperfunctions.hash import hash_dict_sha256

        d = {"a": 1, "b": 2}
        result1 = hash_dict_sha256(d)
        result2 = hash_dict_sha256(d)
        assert result1 == result2

    def test_hash_dict_sha256_different_dicts(self):
        """Test that different dicts produce different hashes."""
        from adare.helperfunctions.hash import hash_dict_sha256

        result1 = hash_dict_sha256({"a": 1})
        result2 = hash_dict_sha256({"a": 2})
        assert result1 != result2

    def test_hash_dict_sha256_empty_dict(self):
        """Test hashing empty dictionary."""
        from adare.helperfunctions.hash import hash_dict_sha256

        result = hash_dict_sha256({})
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hash_string_sha256_basic(self):
        """Test basic string hashing."""
        from adare.helperfunctions.hash import hash_string_sha256

        result = hash_string_sha256("hello world")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hash_string_sha256_deterministic(self):
        """Test that same string produces same hash."""
        from adare.helperfunctions.hash import hash_string_sha256

        result1 = hash_string_sha256("test")
        result2 = hash_string_sha256("test")
        assert result1 == result2

    def test_hash_string_sha256_different_strings(self):
        """Test that different strings produce different hashes."""
        from adare.helperfunctions.hash import hash_string_sha256

        result1 = hash_string_sha256("hello")
        result2 = hash_string_sha256("world")
        assert result1 != result2

    def test_hash_string_sha256_empty(self):
        """Test hashing empty string."""
        from adare.helperfunctions.hash import hash_string_sha256

        result = hash_string_sha256("")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hash_string_sha256_encoding(self):
        """Test string hashing with different encoding."""
        from adare.helperfunctions.hash import hash_string_sha256

        # UTF-8 is default
        result_utf8 = hash_string_sha256("test", encoding="utf-8")
        assert isinstance(result_utf8, str)
        assert len(result_utf8) == 64

    def test_combine_hashes_basic(self):
        """Test combining multiple hashes."""
        from adare.helperfunctions.hash import combine_hashes

        hashes = ["abc123", "def456"]
        result = combine_hashes(hashes)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_combine_hashes_deterministic(self):
        """Test that same hashes produce same combined hash."""
        from adare.helperfunctions.hash import combine_hashes

        hashes = ["hash1", "hash2", "hash3"]
        result1 = combine_hashes(hashes)
        result2 = combine_hashes(hashes)
        assert result1 == result2

    def test_combine_hashes_order_matters(self):
        """Test that hash order matters."""
        from adare.helperfunctions.hash import combine_hashes

        result1 = combine_hashes(["a", "b"])
        result2 = combine_hashes(["b", "a"])
        assert result1 != result2

    def test_combine_hashes_empty_list(self):
        """Test combining empty list of hashes."""
        from adare.helperfunctions.hash import combine_hashes

        result = combine_hashes([])
        assert isinstance(result, str)
        assert len(result) == 64

    def test_combine_hashes_single_hash(self):
        """Test combining single hash."""
        from adare.helperfunctions.hash import combine_hashes

        result = combine_hashes(["single_hash"])
        assert isinstance(result, str)
        assert len(result) == 64


class TestOutputFormatter:
    """Tests for adare.helperfunctions.output_formatter module (pure functions only)."""

    def test_structured_formatter_strip_rich_markup_basic(self):
        """Test stripping Rich markup from text."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        result = formatter._strip_rich_markup("[bold]Hello[/bold]")
        assert result == "Hello"

    def test_structured_formatter_strip_rich_markup_emoji(self):
        """Test stripping Rich emoji codes."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        result = formatter._strip_rich_markup(":white_check_mark: Success")
        assert result == "Success"

    def test_structured_formatter_strip_rich_markup_complex(self):
        """Test stripping complex Rich markup."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        result = formatter._strip_rich_markup("[bold red]Error:[/bold red] Something failed :x:")
        assert "bold" not in result.lower()
        assert "red" not in result.lower()

    def test_structured_formatter_prepare_data_primitives(self):
        """Test prepare_data with primitive types."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        assert formatter.prepare_data(42) == 42
        assert formatter.prepare_data(3.14) == 3.14
        assert formatter.prepare_data(True) is True
        assert formatter.prepare_data(None) is None

    def test_structured_formatter_prepare_data_string(self):
        """Test prepare_data with string."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        result = formatter.prepare_data("[bold]test[/bold]")
        assert result == "test"

    def test_structured_formatter_prepare_data_datetime(self):
        """Test prepare_data with datetime."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = formatter.prepare_data(dt)
        assert result == "2024-01-15T10:30:00"

    def test_structured_formatter_prepare_data_timedelta(self):
        """Test prepare_data with timedelta."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        td = timedelta(hours=2, minutes=30)
        result = formatter.prepare_data(td)
        assert result == 9000.0  # 2.5 hours in seconds

    def test_structured_formatter_prepare_data_path(self):
        """Test prepare_data with Path."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        p = Path("/home/user/test")
        result = formatter.prepare_data(p)
        assert result == "/home/user/test"

    def test_structured_formatter_prepare_data_dict(self):
        """Test prepare_data with dictionary."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        d = {"key": "[bold]value[/bold]", "num": 42}
        result = formatter.prepare_data(d)
        assert result["key"] == "value"
        assert result["num"] == 42

    def test_structured_formatter_prepare_data_list(self):
        """Test prepare_data with list."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        lst = ["[bold]a[/bold]", "b", 3]
        result = formatter.prepare_data(lst)
        assert result == ["a", "b", 3]

    def test_structured_formatter_prepare_data_nested(self):
        """Test prepare_data with nested structures."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        nested = {
            "items": [{"name": "[red]test[/red]", "value": 1}],
            "path": Path("/tmp"),
            "time": datetime(2024, 1, 1),
        }
        result = formatter.prepare_data(nested)
        assert result["items"][0]["name"] == "test"
        assert result["path"] == "/tmp"
        assert result["time"] == "2024-01-01T00:00:00"

    def test_structured_formatter_serialize_json(self):
        """Test JSON serialization."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        data = {"key": "value", "num": 42}
        result = formatter.serialize_json(data)
        assert '"key": "value"' in result
        assert '"num": 42' in result

    def test_structured_formatter_serialize_yaml(self):
        """Test YAML serialization."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        data = {"key": "value", "num": 42}
        result = formatter.serialize_yaml(data)
        assert "key: value" in result
        assert "num: 42" in result

    def test_structured_formatter_make_json_safe(self):
        """Test making data JSON-safe."""
        from adare.helperfunctions.output_formatter import StructuredOutputFormatter

        formatter = StructuredOutputFormatter()
        result = formatter._make_json_safe({"key": "value", "list": [1, 2, 3]})
        assert result == {"key": "value", "list": [1, 2, 3]}

    def test_output_format_enum(self):
        """Test OutputFormat enum values."""
        from adare.helperfunctions.output_formatter import OutputFormat

        assert OutputFormat.RICH.value == "rich"
        assert OutputFormat.JSON.value == "json"
        assert OutputFormat.YAML.value == "yaml"

    def test_get_formatter_with_enum(self):
        """Test get_formatter with enum."""
        from adare.helperfunctions.output_formatter import get_formatter, OutputFormat

        formatter = get_formatter(OutputFormat.JSON)
        assert formatter.format_type == OutputFormat.JSON

    def test_get_formatter_with_string(self):
        """Test get_formatter with string."""
        from adare.helperfunctions.output_formatter import get_formatter, OutputFormat

        formatter = get_formatter("json")
        assert formatter.format_type == OutputFormat.JSON

    def test_get_formatter_with_invalid_string(self):
        """Test get_formatter with invalid string defaults to Rich."""
        from adare.helperfunctions.output_formatter import get_formatter, OutputFormat

        formatter = get_formatter("invalid")
        assert formatter.format_type == OutputFormat.RICH

    def test_output_formatter_format_json(self):
        """Test OutputFormatter with JSON format."""
        from adare.helperfunctions.output_formatter import OutputFormatter, OutputFormat

        formatter = OutputFormatter(OutputFormat.JSON)
        result = formatter.format({"key": "value"})
        assert '"key": "value"' in result

    def test_output_formatter_format_yaml(self):
        """Test OutputFormatter with YAML format."""
        from adare.helperfunctions.output_formatter import OutputFormatter, OutputFormat

        formatter = OutputFormatter(OutputFormat.YAML)
        result = formatter.format({"key": "value"})
        assert "key: value" in result
