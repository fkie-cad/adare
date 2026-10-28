"""The ``safe_*`` database helpers swallow only the errors a database read is expected to raise.

They used to catch ``Exception``, so a programming bug inside a query or a property looked like
an empty result. Expected database errors still turn into the default; anything else propagates.
"""

import logging
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import DetachedInstanceError

from adare.database.exceptions import DatabaseConnectionError
from adare.database.utils import display_helpers
from adare.database.utils.error_handling import (
    DataRetrievalError,
    ObjectNotFoundError,
    safe_count,
    safe_execute_with_fallback,
    safe_get_attribute,
    safe_query_all,
    safe_query_first,
    safe_query_one,
)

pytestmark = pytest.mark.unit

EXPECTED = [
    pytest.param(OperationalError('SELECT 1', {}, Exception('database is locked')), id='sqlalchemy'),
    pytest.param(sqlite3.DatabaseError('file is not a database'), id='sqlite3'),
]
UNEXPECTED = [
    pytest.param(ZeroDivisionError('bug'), id='ZeroDivisionError'),
    pytest.param(RuntimeError('bug'), id='RuntimeError'),
]


def _query(method: str, error: BaseException) -> MagicMock:
    query = MagicMock()
    getattr(query, method).side_effect = error
    return query


class TestQueryHelpers:
    @pytest.mark.parametrize('error', EXPECTED)
    def test_expected_errors_return_the_default(self, error):
        assert safe_query_first(_query('first', error), default='d') == 'd'
        assert safe_query_all(_query('all', error)) == []
        assert safe_query_all(_query('all', error), default=['d']) == ['d']
        assert safe_count(_query('count', error), default=7) == 7

    @pytest.mark.parametrize('error', UNEXPECTED)
    def test_unexpected_errors_propagate(self, error):
        with pytest.raises(type(error)):
            safe_query_first(_query('first', error))
        with pytest.raises(type(error)):
            safe_query_all(_query('all', error))
        with pytest.raises(type(error)):
            safe_count(_query('count', error))

    def test_results_pass_through(self):
        query = MagicMock()
        query.first.return_value = None
        query.all.return_value = [1, 2]
        query.count.return_value = 2
        assert safe_query_first(query, default='d') == 'd'
        assert safe_query_all(query) == [1, 2]
        assert safe_count(query) == 2


class TestSafeQueryOne:
    @pytest.mark.parametrize('error', EXPECTED)
    def test_expected_errors_become_data_retrieval_errors(self, error):
        with pytest.raises(DataRetrievalError):
            safe_query_one(_query('one', error))

    def test_no_result_raises_the_requested_error(self):
        from sqlalchemy.orm.exc import NoResultFound

        with pytest.raises(ObjectNotFoundError):
            safe_query_one(_query('one', NoResultFound()))

    @pytest.mark.parametrize('error', UNEXPECTED)
    def test_unexpected_errors_propagate_unwrapped(self, error):
        with pytest.raises(type(error)):
            safe_query_one(_query('one', error))


class _Row:
    def __init__(self, error: BaseException):
        self._error = error

    @property
    def broken(self):
        raise self._error


class TestSafeGetAttribute:
    def test_missing_attribute_is_the_default(self):
        assert safe_get_attribute(SimpleNamespace(), 'nope', default='d') == 'd'

    def test_nested_access(self):
        obj = SimpleNamespace(vm=SimpleNamespace(osinfo=SimpleNamespace(os='linux')))
        assert safe_get_attribute(obj, 'vm', nested='osinfo.os') == 'linux'

    def test_detached_lazy_load_is_the_default(self):
        assert safe_get_attribute(_Row(DetachedInstanceError('detached')), 'broken', default='d') == 'd'

    @pytest.mark.parametrize('error', UNEXPECTED)
    def test_unexpected_errors_propagate(self, error):
        with pytest.raises(type(error)):
            safe_get_attribute(_Row(error), 'broken')


class TestSafeExecuteWithFallback:
    def test_expected_error_uses_the_fallback(self):
        def primary():
            raise DatabaseConnectionError(logging.getLogger(__name__), 'gone')

        assert safe_execute_with_fallback(primary, lambda: 'fallback') == 'fallback'

    def test_both_failing_raise_data_retrieval_error(self):
        def failing():
            raise sqlite3.DatabaseError('broken')

        with pytest.raises(DataRetrievalError):
            safe_execute_with_fallback(failing, failing)

    def test_unexpected_error_skips_the_fallback(self):
        fallback = MagicMock()

        def primary():
            raise RuntimeError('bug')

        with pytest.raises(RuntimeError):
            safe_execute_with_fallback(primary, fallback)
        fallback.assert_not_called()


class _Obj:
    """A row whose relationships raise on access, like a detached or broken row."""

    def __init__(self, error: BaseException):
        self._error = error

    @property
    def sync_metadata(self):
        raise self._error

    @property
    def osinfo(self):
        raise self._error

    @property
    def vm(self):
        raise self._error

    @property
    def tags(self):
        raise self._error


class TestDisplayHelpers:
    @pytest.mark.parametrize('error', [*EXPECTED, pytest.param(DetachedInstanceError('x'), id='detached')])
    def test_expected_errors_return_the_default(self, error):
        obj = _Obj(error)
        assert display_helpers.safe_get_sync_status(obj) == (False, False)
        assert display_helpers.safe_get_os_info(obj) == ('Unknown', '', '', '', '')
        assert display_helpers.safe_get_vm_info(obj) == ('No VM', '')
        assert display_helpers.safe_get_tags(obj) == []

    @pytest.mark.parametrize('error', UNEXPECTED)
    def test_unexpected_errors_propagate(self, error):
        obj = _Obj(error)
        for helper in (
            display_helpers.safe_get_sync_status,
            display_helpers.safe_get_os_info,
            display_helpers.safe_get_vm_info,
            display_helpers.safe_get_tags,
        ):
            with pytest.raises(type(error)):
                helper(obj)


class _FailingApi:
    def __init__(self, error: BaseException):
        self._error = error

    def __enter__(self):
        raise self._error

    def __exit__(self, *exc):
        return False


ULID = '01J0000000000000000000000A'


class TestReferenceManager:
    def _manager(self, monkeypatch, error):
        from adare.database.reference_manager import ReferenceManager

        manager = ReferenceManager()
        monkeypatch.setattr(manager, '_get_global_api', lambda: _FailingApi(error))
        return manager

    @pytest.mark.parametrize(
        'error',
        [*EXPECTED, pytest.param(DatabaseConnectionError(logging.getLogger(__name__), 'gone'), id='adare-db')],
    )
    def test_expected_errors_mean_not_found(self, monkeypatch, error):
        manager = self._manager(monkeypatch, error)
        assert manager.validate_environment_exists(ULID) is False
        assert manager.get_vm_object(ULID) is None
        assert manager.get_projects_using_vm(ULID) == []

    @pytest.mark.parametrize('error', UNEXPECTED)
    def test_unexpected_errors_propagate(self, monkeypatch, error):
        manager = self._manager(monkeypatch, error)
        with pytest.raises(type(error)):
            manager.validate_environment_exists(ULID)
        with pytest.raises(type(error)):
            manager.get_vm_object(ULID)
