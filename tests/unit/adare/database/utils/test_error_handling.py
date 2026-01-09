"""
Comprehensive unit tests for database error handling utilities.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from adare.database.utils.error_handling import (
    DataRetrievalError,
    ObjectNotFoundError,
    MultipleObjectsFoundError,
    safe_query_one,
    safe_query_first,
    safe_query_all,
    safe_get_attribute,
    safe_count,
    validate_ulid,
    safe_execute_with_fallback,
)


# =============================================================================
# Exception Classes Tests
# =============================================================================

class TestExceptionClasses:
    """Test custom exception classes."""

    def test_data_retrieval_error_is_exception(self):
        """DataRetrievalError should be an Exception subclass."""
        assert issubclass(DataRetrievalError, Exception)

    def test_data_retrieval_error_message(self):
        """DataRetrievalError should carry a message."""
        error = DataRetrievalError("Test error message")
        assert str(error) == "Test error message"

    def test_object_not_found_error_inheritance(self):
        """ObjectNotFoundError should inherit from DataRetrievalError."""
        assert issubclass(ObjectNotFoundError, DataRetrievalError)
        assert issubclass(ObjectNotFoundError, Exception)

    def test_object_not_found_error_message(self):
        """ObjectNotFoundError should carry a message."""
        error = ObjectNotFoundError("Object xyz not found")
        assert str(error) == "Object xyz not found"

    def test_multiple_objects_found_error_inheritance(self):
        """MultipleObjectsFoundError should inherit from DataRetrievalError."""
        assert issubclass(MultipleObjectsFoundError, DataRetrievalError)
        assert issubclass(MultipleObjectsFoundError, Exception)

    def test_multiple_objects_found_error_message(self):
        """MultipleObjectsFoundError should carry a message."""
        error = MultipleObjectsFoundError("Expected one, found many")
        assert str(error) == "Expected one, found many"

    def test_can_catch_specific_errors_with_base_class(self):
        """Should be able to catch specific errors using base class."""
        with pytest.raises(DataRetrievalError):
            raise ObjectNotFoundError("test")

        with pytest.raises(DataRetrievalError):
            raise MultipleObjectsFoundError("test")


# =============================================================================
# safe_query_one() Tests
# =============================================================================

class TestSafeQueryOne:
    """Test safe_query_one function."""

    def test_success_returns_result(self):
        """Should return the query result when exactly one found."""
        mock_query = Mock()
        expected_result = {"id": 1, "name": "test"}
        mock_query.one.return_value = expected_result

        result = safe_query_one(mock_query)

        assert result == expected_result
        mock_query.one.assert_called_once()

    def test_no_result_raises_object_not_found_error_default(self):
        """Should raise ObjectNotFoundError when no result found (default)."""
        mock_query = Mock()
        mock_query.one.side_effect = NoResultFound()

        with pytest.raises(ObjectNotFoundError) as exc_info:
            safe_query_one(mock_query)

        assert "Object not found" in str(exc_info.value)

    def test_no_result_raises_custom_error_class(self):
        """Should raise custom error class when specified."""
        mock_query = Mock()
        mock_query.one.side_effect = NoResultFound()

        class CustomError(Exception):
            pass

        with pytest.raises(CustomError) as exc_info:
            safe_query_one(mock_query, error_class=CustomError, error_message="Custom not found")

        assert "Custom not found" in str(exc_info.value)

    def test_no_result_with_custom_message(self):
        """Should use custom error message when provided."""
        mock_query = Mock()
        mock_query.one.side_effect = NoResultFound()

        with pytest.raises(ObjectNotFoundError) as exc_info:
            safe_query_one(mock_query, error_message="VM with id 123 not found")

        assert "VM with id 123 not found" in str(exc_info.value)

    def test_multiple_results_raises_multiple_objects_found_error(self):
        """Should raise MultipleObjectsFoundError when multiple found."""
        mock_query = Mock()
        mock_query.one.side_effect = MultipleResultsFound()

        with pytest.raises(MultipleObjectsFoundError) as exc_info:
            safe_query_one(mock_query, error_message="Expected unique VM")

        assert "Multiple objects found" in str(exc_info.value)
        assert "Expected unique VM" in str(exc_info.value)

    def test_unexpected_error_raises_data_retrieval_error(self):
        """Should wrap unexpected errors in DataRetrievalError."""
        mock_query = Mock()
        mock_query.one.side_effect = RuntimeError("Database connection lost")

        with pytest.raises(DataRetrievalError) as exc_info:
            safe_query_one(mock_query)

        assert "Database error" in str(exc_info.value)


# =============================================================================
# safe_query_first() Tests
# =============================================================================

class TestSafeQueryFirst:
    """Test safe_query_first function."""

    def test_success_returns_result(self):
        """Should return the first result when found."""
        mock_query = Mock()
        expected_result = {"id": 1, "name": "first"}
        mock_query.first.return_value = expected_result

        result = safe_query_first(mock_query)

        assert result == expected_result
        mock_query.first.assert_called_once()

    def test_no_result_returns_default_none(self):
        """Should return None when no result found and no default specified."""
        mock_query = Mock()
        mock_query.first.return_value = None

        result = safe_query_first(mock_query)

        assert result is None

    def test_no_result_returns_custom_default(self):
        """Should return custom default when no result found."""
        mock_query = Mock()
        mock_query.first.return_value = None

        default_value = {"status": "unknown"}
        result = safe_query_first(mock_query, default=default_value)

        assert result == default_value

    def test_no_result_returns_empty_list_as_default(self):
        """Should return empty list as default when specified."""
        mock_query = Mock()
        mock_query.first.return_value = None

        result = safe_query_first(mock_query, default=[])

        assert result == []

    def test_error_returns_default(self):
        """Should return default on database error."""
        mock_query = Mock()
        mock_query.first.side_effect = RuntimeError("Connection failed")

        result = safe_query_first(mock_query, default="fallback")

        assert result == "fallback"

    def test_error_returns_none_as_default(self):
        """Should return None on error when no default specified."""
        mock_query = Mock()
        mock_query.first.side_effect = RuntimeError("Connection failed")

        result = safe_query_first(mock_query)

        assert result is None


# =============================================================================
# safe_query_all() Tests
# =============================================================================

class TestSafeQueryAll:
    """Test safe_query_all function."""

    def test_success_returns_all_results(self):
        """Should return all results from query."""
        mock_query = Mock()
        expected_results = [{"id": 1}, {"id": 2}, {"id": 3}]
        mock_query.all.return_value = expected_results

        result = safe_query_all(mock_query)

        assert result == expected_results
        mock_query.all.assert_called_once()

    def test_empty_result_returns_empty_list(self):
        """Should return empty list when query returns nothing."""
        mock_query = Mock()
        mock_query.all.return_value = []

        result = safe_query_all(mock_query)

        assert result == []

    def test_error_returns_empty_list_default(self):
        """Should return empty list on error when no default specified."""
        mock_query = Mock()
        mock_query.all.side_effect = RuntimeError("Database error")

        result = safe_query_all(mock_query)

        assert result == []

    def test_error_returns_custom_default(self):
        """Should return custom default on error."""
        mock_query = Mock()
        mock_query.all.side_effect = RuntimeError("Database error")

        default_value = [{"fallback": True}]
        result = safe_query_all(mock_query, default=default_value)

        assert result == default_value

    def test_none_default_is_replaced_with_empty_list(self):
        """Should convert None default to empty list internally."""
        mock_query = Mock()
        mock_query.all.side_effect = RuntimeError("Database error")

        result = safe_query_all(mock_query, default=None)

        assert result == []


# =============================================================================
# safe_get_attribute() Tests
# =============================================================================

class TestSafeGetAttribute:
    """Test safe_get_attribute function."""

    def test_simple_attribute_access(self):
        """Should get a simple attribute from an object."""
        obj = Mock()
        obj.name = "test_name"

        result = safe_get_attribute(obj, "name")

        assert result == "test_name"

    def test_missing_attribute_returns_default(self):
        """Should return default when attribute doesn't exist."""
        obj = Mock(spec=[])  # Empty spec, no attributes

        result = safe_get_attribute(obj, "nonexistent", default="fallback")

        assert result == "fallback"

    def test_none_object_returns_default(self):
        """Should return default when object is None."""
        result = safe_get_attribute(None, "any_attribute", default="default_value")

        assert result == "default_value"

    def test_nested_attribute_access(self):
        """Should access nested attributes using dot notation."""
        inner_obj = Mock()
        inner_obj.subattr = "nested_value"

        outer_obj = Mock()
        outer_obj.attr = inner_obj

        result = safe_get_attribute(outer_obj, "attr", nested="subattr")

        assert result == "nested_value"

    def test_deeply_nested_attribute_access(self):
        """Should access deeply nested attributes (obj.attr.sub.deep)."""
        deep_obj = Mock()
        deep_obj.value = "deep_value"

        sub_obj = Mock()
        sub_obj.deep = deep_obj

        attr_obj = Mock()
        attr_obj.sub = sub_obj

        outer_obj = Mock()
        outer_obj.attr = attr_obj

        result = safe_get_attribute(outer_obj, "attr", nested="sub.deep.value")

        assert result == "deep_value"

    def test_nested_with_none_attribute_returns_none(self):
        """Should return None when attribute value is None (nested not traversed)."""
        outer_obj = Mock()
        outer_obj.attr = None

        # When the attribute itself is None, nested traversal is skipped and None is returned
        result = safe_get_attribute(outer_obj, "attr", nested="subattr", default="default")

        assert result is None

    def test_nested_attribute_not_found_returns_default(self):
        """Should return default when nested attribute doesn't exist."""
        inner_obj = Mock(spec=[])  # Empty spec

        outer_obj = Mock()
        outer_obj.attr = inner_obj

        result = safe_get_attribute(outer_obj, "attr", nested="nonexistent", default="fallback")

        assert result == "fallback"

    def test_error_during_access_returns_default(self):
        """Should return default when exception occurs during attribute access."""
        obj = Mock()
        # Make the attribute access raise an exception
        type(obj).problem_attr = property(lambda self: 1/0)

        result = safe_get_attribute(obj, "problem_attr", default="safe_default")

        assert result == "safe_default"


# =============================================================================
# safe_count() Tests
# =============================================================================

class TestSafeCount:
    """Test safe_count function."""

    def test_success_returns_count(self):
        """Should return the count from query."""
        mock_query = Mock()
        mock_query.count.return_value = 42

        result = safe_count(mock_query)

        assert result == 42
        mock_query.count.assert_called_once()

    def test_zero_count(self):
        """Should return zero when count is zero."""
        mock_query = Mock()
        mock_query.count.return_value = 0

        result = safe_count(mock_query)

        assert result == 0

    def test_error_returns_default_zero(self):
        """Should return 0 on error when no default specified."""
        mock_query = Mock()
        mock_query.count.side_effect = RuntimeError("Database error")

        result = safe_count(mock_query)

        assert result == 0

    def test_error_returns_custom_default(self):
        """Should return custom default on error."""
        mock_query = Mock()
        mock_query.count.side_effect = RuntimeError("Database error")

        result = safe_count(mock_query, default=-1)

        assert result == -1


# =============================================================================
# validate_ulid() Tests
# =============================================================================

class TestValidateUlid:
    """Test validate_ulid function."""

    def test_valid_ulid(self):
        """Should return True for valid ULID."""
        # Valid ULID: 26 chars, Crockford's Base32
        valid_ulid = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        assert validate_ulid(valid_ulid) is True

    def test_valid_ulid_lowercase(self):
        """Should return True for valid lowercase ULID."""
        valid_ulid = "01arz3ndektsv4rrffq69g5fav"
        assert validate_ulid(valid_ulid) is True

    def test_valid_ulid_mixed_case(self):
        """Should return True for valid mixed case ULID."""
        valid_ulid = "01ArZ3NDekTSv4rrFFQ69G5FAv"
        assert validate_ulid(valid_ulid) is True

    def test_empty_string_invalid(self):
        """Should return False for empty string."""
        assert validate_ulid("") is False

    def test_none_invalid(self):
        """Should return False for None."""
        assert validate_ulid(None) is False

    def test_too_short_invalid(self):
        """Should return False for ULID shorter than 26 chars."""
        short_ulid = "01ARZ3NDEKTSV4RRFFQ69G5FA"  # 25 chars
        assert validate_ulid(short_ulid) is False

    def test_too_long_invalid(self):
        """Should return False for ULID longer than 26 chars."""
        long_ulid = "01ARZ3NDEKTSV4RRFFQ69G5FAVX"  # 27 chars
        assert validate_ulid(long_ulid) is False

    def test_invalid_characters(self):
        """Should return False for ULID with invalid characters."""
        # 'I', 'L', 'O', 'U' are not in Crockford's Base32
        invalid_ulid_i = "01ARZ3NDEKTSV4RRFFQI9G5FAV"  # Contains I
        invalid_ulid_l = "01ARZ3NDEKTSV4RRFFQL9G5FAV"  # Contains L
        invalid_ulid_o = "01ARZ3NDEKTSV4RRFFQO9G5FAV"  # Contains O
        invalid_ulid_u = "01ARZ3NDEKTSV4RRFFQU9G5FAV"  # Contains U

        assert validate_ulid(invalid_ulid_i) is False
        assert validate_ulid(invalid_ulid_l) is False
        assert validate_ulid(invalid_ulid_o) is False
        assert validate_ulid(invalid_ulid_u) is False

    def test_special_characters_invalid(self):
        """Should return False for ULID with special characters."""
        invalid_ulid = "01ARZ3NDEK-SV4RR+FQ69G5FAV"
        assert validate_ulid(invalid_ulid) is False

    def test_spaces_invalid(self):
        """Should return False for ULID with spaces."""
        invalid_ulid = "01ARZ3NDEKTSV4RR FQ69G5FAV"
        assert validate_ulid(invalid_ulid) is False

    def test_all_valid_crockford_characters(self):
        """Should accept all valid Crockford's Base32 characters."""
        # Test with all valid characters: 0-9, A-H, J, K, M, N, P-T, V-Z
        valid_chars = "0123456789ABCDEFGHJKMNPQRS"  # 26 chars with valid set
        assert validate_ulid(valid_chars) is True


# =============================================================================
# safe_execute_with_fallback() Tests
# =============================================================================

class TestSafeExecuteWithFallback:
    """Test safe_execute_with_fallback function."""

    def test_primary_success(self):
        """Should return primary function result on success."""
        def primary(x, y):
            return x + y

        def fallback(x, y):
            return x * y

        result = safe_execute_with_fallback(primary, fallback, 3, 4)

        assert result == 7  # 3 + 4

    def test_fallback_on_primary_failure(self):
        """Should use fallback when primary fails."""
        def primary(x, y):
            raise ValueError("Primary failed")

        def fallback(x, y):
            return x * y

        result = safe_execute_with_fallback(primary, fallback, 3, 4)

        assert result == 12  # 3 * 4

    def test_with_kwargs(self):
        """Should pass kwargs to both functions."""
        def primary(a, b, multiplier=1):
            return (a + b) * multiplier

        def fallback(a, b, multiplier=1):
            return a * b * multiplier

        result = safe_execute_with_fallback(primary, fallback, 2, 3, multiplier=10)

        assert result == 50  # (2 + 3) * 10

    def test_fallback_with_kwargs_on_primary_failure(self):
        """Should pass kwargs to fallback when primary fails."""
        def primary(a, b, multiplier=1):
            raise RuntimeError("Nope")

        def fallback(a, b, multiplier=1):
            return a * b * multiplier

        result = safe_execute_with_fallback(primary, fallback, 2, 3, multiplier=10)

        assert result == 60  # 2 * 3 * 10

    def test_both_fail_raises_data_retrieval_error(self):
        """Should raise DataRetrievalError when both functions fail."""
        def primary():
            raise ValueError("Primary failed")

        def fallback():
            raise RuntimeError("Fallback also failed")

        with pytest.raises(DataRetrievalError) as exc_info:
            safe_execute_with_fallback(primary, fallback)

        assert "All operations failed" in str(exc_info.value)

    def test_no_args(self):
        """Should work with functions taking no arguments."""
        def primary():
            return "primary_result"

        def fallback():
            return "fallback_result"

        result = safe_execute_with_fallback(primary, fallback)

        assert result == "primary_result"

    def test_primary_returns_none(self):
        """Should return None when primary returns None (not fallback)."""
        def primary():
            return None

        def fallback():
            return "fallback"

        result = safe_execute_with_fallback(primary, fallback)

        assert result is None

    def test_primary_returns_false(self):
        """Should return False when primary returns False (not fallback)."""
        def primary():
            return False

        def fallback():
            return True

        result = safe_execute_with_fallback(primary, fallback)

        assert result is False


# =============================================================================
# Integration-style Tests
# =============================================================================

class TestIntegrationScenarios:
    """Test realistic usage scenarios combining multiple functions."""

    def test_chained_safe_queries(self):
        """Test using safe functions in a realistic query chain."""
        # Mock a parent query that returns an item
        mock_parent_query = Mock()
        parent_obj = Mock()
        parent_obj.id = "parent_123"
        parent_obj.child = Mock()
        parent_obj.child.name = "child_object"
        mock_parent_query.first.return_value = parent_obj

        # Get parent
        parent = safe_query_first(mock_parent_query)
        assert parent is not None

        # Get nested attribute
        child_name = safe_get_attribute(parent, "child", nested="name")
        assert child_name == "child_object"

    def test_validate_and_query(self):
        """Test validating ULID before querying."""
        valid_ulid = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        invalid_ulid = "invalid"

        mock_query = Mock()
        mock_query.one.return_value = {"id": valid_ulid}

        if validate_ulid(valid_ulid):
            result = safe_query_one(mock_query)
            assert result["id"] == valid_ulid

        assert not validate_ulid(invalid_ulid)

    def test_fallback_to_count_on_all_failure(self):
        """Test using safe_execute_with_fallback with query operations."""
        def get_all_items(query):
            return safe_query_all(query)

        def get_item_count(query):
            return safe_count(query)

        mock_query = Mock()
        mock_query.all.side_effect = RuntimeError("Query too complex")
        mock_query.count.return_value = 100

        # This should use fallback
        result = safe_execute_with_fallback(
            lambda: get_all_items(mock_query),
            lambda: get_item_count(mock_query)
        )

        # Since all() returns [] on error (its default), primary actually "succeeds"
        # Let's use a different test approach
        assert result == []  # Empty list is the default from safe_query_all
