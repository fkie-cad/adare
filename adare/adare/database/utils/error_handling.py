"""
Consistent error handling utilities for database operations.

Provides standardized error handling patterns to improve code consistency.
"""
# configure logging
import logging
from typing import Any, TypeVar

from sqlalchemy.orm import Query
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound

log = logging.getLogger(__name__)

T = TypeVar('T')


class DataRetrievalError(Exception):
    """Base exception for data retrieval errors."""
    pass


class ObjectNotFoundError(DataRetrievalError):
    """Raised when a required object is not found."""
    pass


class MultipleObjectsFoundError(DataRetrievalError):
    """Raised when multiple objects found where one was expected."""
    pass


def safe_query_one(query: Query, error_class: type[Exception] = ObjectNotFoundError,
                   error_message: str = "Object not found") -> Any:
    """
    Safely execute a query that should return exactly one result.

    Args:
        query: SQLAlchemy query
        error_class: Exception class to raise on error
        error_message: Error message for the exception

    Returns:
        Single query result

    Raises:
        error_class: When no result or multiple results found
    """
    try:
        return query.one()
    except NoResultFound:
        log.warning(f"No result found: {error_message}")
        raise error_class(error_message) from None
    except MultipleResultsFound:
        log.warning(f"Multiple results found: {error_message}")
        raise MultipleObjectsFoundError(f"Multiple objects found: {error_message}") from None
    except Exception as e:
        log.error(f"Unexpected database error: {e}")
        raise DataRetrievalError(f"Database error: {e}") from e


def safe_query_first(query: Query, default: Any = None) -> Any:
    """
    Safely execute a query that may return zero or one result.

    Args:
        query: SQLAlchemy query
        default: Default value to return if no result found

    Returns:
        First query result or default value
    """
    try:
        result = query.first()
        return result if result is not None else default
    except Exception as e:
        log.error(f"Database query error: {e}")
        return default


def safe_query_all(query: Query, default: list | None = None) -> list:
    """
    Safely execute a query that returns multiple results.

    Args:
        query: SQLAlchemy query
        default: Default value to return on error

    Returns:
        List of query results or default value
    """
    if default is None:
        default = []

    try:
        return query.all()
    except Exception as e:
        log.error(f"Database query error: {e}")
        return default


def safe_get_attribute(obj: Any, attribute: str, default: Any = None,
                      nested: str | None = None) -> Any:
    """
    Safely get an attribute from an object with optional nested access.

    Args:
        obj: Object to get attribute from
        attribute: Attribute name
        default: Default value if attribute not found
        nested: Optional nested attribute (e.g., 'vm.osinfo')

    Returns:
        Attribute value or default
    """
    try:
        if obj is None:
            return default

        value = getattr(obj, attribute, default)

        if nested and value is not None:
            for nested_attr in nested.split('.'):
                value = getattr(value, nested_attr, default)
                if value is None:
                    return default

        return value
    except Exception as e:
        log.debug(f"Error getting attribute {attribute}: {e}")
        return default


def safe_count(query: Query, default: int = 0) -> int:
    """
    Safely get count from a query.

    Args:
        query: SQLAlchemy query
        default: Default count value on error

    Returns:
        Count result or default value
    """
    try:
        return query.count()
    except Exception as e:
        log.error(f"Database count error: {e}")
        return default


def validate_ulid(ulid: str) -> bool:
    """
    Validate ULID format.

    Args:
        ulid: ULID string to validate

    Returns:
        True if valid ULID format, False otherwise
    """
    if not ulid or len(ulid) != 26:
        return False

    # ULID uses Crockford's Base32 encoding
    valid_chars = set('0123456789ABCDEFGHJKMNPQRSTVWXYZ')
    return all(c in valid_chars for c in ulid.upper())


def safe_execute_with_fallback(primary_func, fallback_func, *args, **kwargs):
    """
    Execute a function with a fallback if the primary fails.

    Args:
        primary_func: Primary function to try
        fallback_func: Fallback function if primary fails
        *args: Arguments for both functions
        **kwargs: Keyword arguments for both functions

    Returns:
        Result from primary function or fallback function
    """
    try:
        return primary_func(*args, **kwargs)
    except Exception as e:
        log.warning(f"Primary function failed, using fallback: {e}")
        try:
            return fallback_func(*args, **kwargs)
        except Exception as fallback_e:
            log.error(f"Both primary and fallback functions failed: {e}, {fallback_e}")
            raise DataRetrievalError(f"All operations failed: {e}") from fallback_e
