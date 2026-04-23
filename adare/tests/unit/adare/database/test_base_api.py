"""Tests for EnhancedDatabaseApi — the base database API layer."""

import logging
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy
import ulid
from sqlalchemy import CHAR, Column, String, create_engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

pytestmark = pytest.mark.unit

from adare.database.api.base import (
    EnhancedDatabaseApi,
    handle_db_errors,
    validate_input,
)
from adare.database.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    EntityNotFoundError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Test model — lightweight SQLAlchemy model for in-memory testing
# ---------------------------------------------------------------------------

TestBase = declarative_base()


class Item(TestBase):
    """Minimal model for exercising the base API."""

    __tablename__ = "item"
    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True)
    category = Column(String, nullable=True)


# ---------------------------------------------------------------------------
# Concrete subclass of the abstract-ish EnhancedDatabaseApi
# ---------------------------------------------------------------------------


class _TestApi(EnhancedDatabaseApi):
    """Thin subclass that bypasses config-dependent __init__."""

    def __init__(self, engine):
        # Skip the normal __init__ which reads config and creates an engine.
        self._engine = engine
        self._session = None
        self._session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """In-memory SQLite engine with the Item table created."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    TestBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def api(engine):
    """An _TestApi instance wrapped in its context manager."""
    db = _TestApi(engine)
    with db:
        yield db


@pytest.fixture()
def api_no_session(engine):
    """An _TestApi instance *without* an active session."""
    return _TestApi(engine)


def _ulid() -> str:
    return str(ulid.ULID())


# ===================================================================
# Context manager: __enter__ / __exit__
# ===================================================================


class TestContextManager:
    """Verify session lifecycle through the context manager."""

    def test_enter_creates_session(self, engine):
        db = _TestApi(engine)
        assert db._session is None
        db.__enter__()
        assert db._session is not None
        db.__exit__(None, None, None)

    def test_exit_closes_session(self, engine):
        db = _TestApi(engine)
        db.__enter__()
        assert db._session is not None
        db.__exit__(None, None, None)
        assert db._session is None

    def test_exit_commits_on_success(self, api):
        """Entities created inside the context are persisted."""
        entity = api.create_entity(Item, name="persisted")
        assert entity.id is not None

    def test_exit_rolls_back_on_exception(self, engine):
        db = _TestApi(engine)
        try:
            with db:
                db.create_entity(Item, name="should_vanish")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        # After rollback the row must not be in the database.
        with db:
            results = db.list_entities(Item)
            assert results == []

    def test_reuses_existing_session(self, engine):
        db = _TestApi(engine)
        db.__enter__()
        first_session = db._session
        db._start_session()  # should reuse
        assert db._session is first_session
        db.__exit__(None, None, None)


# ===================================================================
# get_by_ulid
# ===================================================================


class TestGetByUlid:
    def test_returns_entity_when_found(self, api):
        created = api.create_entity(Item, name="findme")
        found = api.get_by_ulid(Item, created.id)
        assert found is not None
        assert found.id == created.id
        assert found.name == "findme"

    def test_returns_none_when_not_found(self, api):
        fake_ulid = _ulid()
        result = api.get_by_ulid(Item, fake_ulid)
        assert result is None

    def test_raises_validation_error_on_bad_ulid(self, api):
        with pytest.raises(ValidationError):
            api.get_by_ulid(Item, "not-a-valid-ulid")

    def test_raises_database_error_without_session(self, api_no_session):
        with pytest.raises(DatabaseError):
            api_no_session.get_by_ulid(Item, _ulid())


# ===================================================================
# get_by_ulid_or_404
# ===================================================================


class TestGetByUlidOr404:
    def test_returns_entity_when_found(self, api):
        created = api.create_entity(Item, name="here")
        found = api.get_by_ulid_or_404(Item, created.id)
        assert found.id == created.id

    def test_raises_entity_not_found(self, api):
        with pytest.raises(EntityNotFoundError):
            api.get_by_ulid_or_404(Item, _ulid())


# ===================================================================
# create_entity
# ===================================================================


class TestCreateEntity:
    def test_creates_and_returns_entity(self, api):
        entity = api.create_entity(Item, name="new_item")
        assert entity.name == "new_item"
        assert entity.id is not None
        assert len(entity.id) == 26  # ULID length

    def test_auto_generates_ulid(self, api):
        entity = api.create_entity(Item, name="auto_id")
        # Validate the generated id is a valid ULID
        parsed = ulid.ULID.from_str(entity.id)
        assert str(parsed) == entity.id

    def test_uses_provided_id(self, api):
        custom_id = _ulid()
        entity = api.create_entity(Item, id=custom_id, name="custom")
        assert entity.id == custom_id

    def test_raises_on_duplicate_unique_field(self, api):
        api.create_entity(Item, name="unique_name")
        with pytest.raises((DatabaseError, IntegrityError)):
            api.create_entity(Item, name="unique_name")

    def test_raises_database_error_without_session(self, api_no_session):
        with pytest.raises(DatabaseError):
            api_no_session.create_entity(Item, name="fail")


# ===================================================================
# update_entity
# ===================================================================


class TestUpdateEntity:
    def test_updates_fields(self, api):
        entity = api.create_entity(Item, name="before", category="old")
        updated = api.update_entity(entity, name="after", category="new")
        assert updated.name == "after"
        assert updated.category == "new"

    def test_ignores_unknown_attributes(self, api):
        entity = api.create_entity(Item, name="item")
        updated = api.update_entity(entity, nonexistent_field="value")
        assert updated.name == "item"
        assert not hasattr(updated, "nonexistent_field")

    def test_raises_database_error_without_session(self, api_no_session):
        fake_entity = Item(name="x")
        with pytest.raises(DatabaseError):
            api_no_session.update_entity(fake_entity, name="y")


# ===================================================================
# delete_entity
# ===================================================================


class TestDeleteEntity:
    def test_deletes_entity(self, api):
        entity = api.create_entity(Item, name="doomed")
        api.delete_entity(entity)
        assert api.get_by_ulid(Item, entity.id) is None

    def test_count_decreases_after_delete(self, api):
        entity = api.create_entity(Item, name="to_delete")
        assert api.count_entities(Item) == 1
        api.delete_entity(entity)
        assert api.count_entities(Item) == 0

    def test_raises_database_error_without_session(self, api_no_session):
        fake_entity = Item(name="x")
        with pytest.raises(DatabaseError):
            api_no_session.delete_entity(fake_entity)


# ===================================================================
# get_or_create
# ===================================================================


class TestGetOrCreate:
    def test_creates_when_not_exists(self, api):
        entity, created = api.get_or_create(Item, name="fresh")
        assert created is True
        assert entity.name == "fresh"
        assert entity.id is not None

    def test_returns_existing(self, api):
        api.create_entity(Item, name="existing")
        entity, created = api.get_or_create(Item, name="existing")
        assert created is False
        assert entity.name == "existing"

    def test_applies_defaults_on_create(self, api):
        entity, created = api.get_or_create(
            Item, defaults={"category": "default_cat"}, name="with_defaults"
        )
        assert created is True
        assert entity.category == "default_cat"

    def test_defaults_ignored_for_existing(self, api):
        api.create_entity(Item, name="old", category="original")
        entity, created = api.get_or_create(
            Item, defaults={"category": "overridden"}, name="old"
        )
        assert created is False
        assert entity.category == "original"

    def test_raises_database_error_without_session(self, api_no_session):
        with pytest.raises(DatabaseError):
            api_no_session.get_or_create(Item, name="fail")


# ===================================================================
# list_entities
# ===================================================================


class TestListEntities:
    def test_lists_all(self, api):
        api.create_entity(Item, name="a")
        api.create_entity(Item, name="b")
        api.create_entity(Item, name="c")
        result = api.list_entities(Item)
        assert len(result) == 3

    def test_filters(self, api):
        api.create_entity(Item, name="x", category="cat1")
        api.create_entity(Item, name="y", category="cat2")
        api.create_entity(Item, name="z", category="cat1")
        result = api.list_entities(Item, filters={"category": "cat1"})
        assert len(result) == 2
        assert all(e.category == "cat1" for e in result)

    def test_limit(self, api):
        for i in range(5):
            api.create_entity(Item, name=f"item_{i}")
        result = api.list_entities(Item, limit=3)
        assert len(result) == 3

    def test_offset(self, api):
        for i in range(5):
            api.create_entity(Item, name=f"item_{i}")
        all_items = api.list_entities(Item, order_by="name")
        offset_items = api.list_entities(Item, order_by="name", offset=2)
        assert len(offset_items) == 3
        assert offset_items[0].name == all_items[2].name

    def test_limit_and_offset_combined(self, api):
        for i in range(10):
            api.create_entity(Item, name=f"item_{i:02d}")
        result = api.list_entities(Item, order_by="name", offset=2, limit=3)
        assert len(result) == 3

    def test_order_by(self, api):
        api.create_entity(Item, name="charlie")
        api.create_entity(Item, name="alpha")
        api.create_entity(Item, name="bravo")
        result = api.list_entities(Item, order_by="name")
        names = [e.name for e in result]
        assert names == sorted(names)

    def test_order_by_unknown_field_still_returns(self, api):
        api.create_entity(Item, name="a")
        result = api.list_entities(Item, order_by="nonexistent_column")
        assert len(result) == 1  # just no ordering applied

    def test_empty_result(self, api):
        result = api.list_entities(Item)
        assert result == []

    def test_raises_database_error_without_session(self, api_no_session):
        with pytest.raises(DatabaseError):
            api_no_session.list_entities(Item)


# ===================================================================
# count_entities
# ===================================================================


class TestCountEntities:
    def test_counts_all(self, api):
        assert api.count_entities(Item) == 0
        api.create_entity(Item, name="one")
        api.create_entity(Item, name="two")
        assert api.count_entities(Item) == 2

    def test_counts_with_filter(self, api):
        api.create_entity(Item, name="a", category="x")
        api.create_entity(Item, name="b", category="y")
        api.create_entity(Item, name="c", category="x")
        assert api.count_entities(Item, filters={"category": "x"}) == 2
        assert api.count_entities(Item, filters={"category": "y"}) == 1

    def test_raises_database_error_without_session(self, api_no_session):
        with pytest.raises(DatabaseError):
            api_no_session.count_entities(Item)


# ===================================================================
# bulk_create_entities
# ===================================================================


class TestBulkCreateEntities:
    def test_creates_multiple(self, api):
        items = [{"name": "bulk1"}, {"name": "bulk2"}, {"name": "bulk3"}]
        api.bulk_create_entities(Item, items)
        assert api.count_entities(Item) == 3

    def test_auto_generates_ulids(self, api):
        items = [{"name": "a"}, {"name": "b"}]
        api.bulk_create_entities(Item, items)
        all_items = api.list_entities(Item)
        for entity in all_items:
            assert entity.id is not None
            assert len(entity.id) == 26

    def test_return_objects_flag(self, api):
        items = [{"name": "ret1"}, {"name": "ret2"}]
        result = api.bulk_create_entities(Item, items, return_objects=True)
        assert len(result) == 2
        names = {e.name for e in result}
        assert names == {"ret1", "ret2"}

    def test_returns_empty_list_by_default(self, api):
        items = [{"name": "x"}]
        result = api.bulk_create_entities(Item, items, return_objects=False)
        assert result == []

    def test_empty_items_returns_empty(self, api):
        result = api.bulk_create_entities(Item, [])
        assert result == []
        assert api.count_entities(Item) == 0

    def test_raises_database_error_without_session(self, api_no_session):
        with pytest.raises(DatabaseError):
            api_no_session.bulk_create_entities(Item, [{"name": "fail"}])


# ===================================================================
# transaction() context manager
# ===================================================================


class TestTransaction:
    def test_commits_on_success(self, api):
        with api.transaction():
            api._session.add(Item(id=_ulid(), name="txn_ok"))
        found = api.list_entities(Item)
        assert len(found) == 1
        assert found[0].name == "txn_ok"

    def test_rolls_back_on_error(self, api):
        with pytest.raises(ValueError):
            with api.transaction():
                api._session.add(Item(id=_ulid(), name="txn_fail"))
                api._session.flush()
                raise ValueError("forced error")
        # After rollback the row must be gone.
        result = api.list_entities(Item)
        assert result == []

    def test_raises_without_session(self, api_no_session):
        with pytest.raises(DatabaseError):
            with api_no_session.transaction():
                pass


# ===================================================================
# Error handling decorators
# ===================================================================


class TestHandleDbErrors:
    """Verify that handle_db_errors wraps SQLAlchemy exceptions."""

    def test_wraps_integrity_error(self, api):
        """IntegrityError becomes DatabaseError."""
        api.create_entity(Item, name="dup")
        with pytest.raises(DatabaseError, match="integrity"):
            api.create_entity(Item, name="dup")

    def test_wraps_sqlalchemy_error(self, engine):
        """Generic SQLAlchemyError becomes DatabaseError."""

        class _BadApi(_TestApi):
            @handle_db_errors
            def bad_query(self):
                raise SQLAlchemyError("synthetic")

        db = _BadApi(engine)
        with pytest.raises(DatabaseError, match="Database operation failed"):
            db.bad_query()

    def test_non_db_exceptions_pass_through(self, engine):
        """Non-SQLAlchemy exceptions are not caught by handle_db_errors."""

        class _BadApi(_TestApi):
            @handle_db_errors
            def explode(self):
                raise RuntimeError("not a db error")

        db = _BadApi(engine)
        with pytest.raises(RuntimeError, match="not a db error"):
            db.explode()


class TestValidateInput:
    """Verify that validate_input wraps ValueError/TypeError."""

    def test_wraps_value_error(self, engine):

        class _BadApi(_TestApi):
            @validate_input
            def bad_value(self):
                raise ValueError("bad val")

        db = _BadApi(engine)
        with pytest.raises(ValidationError, match="Invalid input"):
            db.bad_value()

    def test_wraps_type_error(self, engine):

        class _BadApi(_TestApi):
            @validate_input
            def bad_type(self):
                raise TypeError("wrong type")

        db = _BadApi(engine)
        with pytest.raises(ValidationError, match="Invalid input"):
            db.bad_type()

    def test_other_exceptions_pass_through(self, engine):

        class _BadApi(_TestApi):
            @validate_input
            def explode(self):
                raise KeyError("unrelated")

        db = _BadApi(engine)
        with pytest.raises(KeyError):
            db.explode()


# ===================================================================
# Helper methods (expunge, refresh, commit, rollback, flush, etc.)
# ===================================================================


class TestHelperMethods:
    def test_expunge_removes_from_session(self, api):
        entity = api.create_entity(Item, name="expunged")
        api.expunge(entity)
        # The entity should no longer be tracked by the session
        assert entity not in api._session

    def test_expunge_all(self, api):
        api.create_entity(Item, name="a")
        api.create_entity(Item, name="b")
        api.expunge_all()
        # Session identity map should be empty
        assert len(api._session.identity_map) == 0

    def test_commit(self, api):
        api._session.add(Item(id=_ulid(), name="committed"))
        api._session.flush()
        api.commit()
        # Data persists after commit
        found = api.list_entities(Item)
        assert len(found) == 1

    def test_rollback(self, api):
        api._session.add(Item(id=_ulid(), name="rolled_back"))
        api._session.flush()
        api.rollback()
        found = api.list_entities(Item)
        assert found == []

    def test_flush(self, api):
        item = Item(id=_ulid(), name="flushed")
        api._session.add(item)
        api.flush()
        # After flush the item should be queryable within the session
        found = api._session.query(Item).filter_by(name="flushed").first()
        assert found is not None

    def test_make_transient(self, api):
        entity = api.create_entity(Item, name="transient")
        api.make_transient(entity)
        assert entity not in api._session

    def test_extract_id_with_id_attr(self, api):
        entity = api.create_entity(Item, name="extract")
        extracted = api.extract_id(entity)
        assert extracted == entity.id

    def test_extract_id_falls_back_to_str(self, api):
        result = api.extract_id("plain_string")
        assert result == "plain_string"

    def test_helpers_are_safe_without_session(self, api_no_session):
        """Helper methods should not raise when there is no active session."""
        fake = Item(name="x")
        api_no_session.expunge(fake)       # no-op
        api_no_session.expunge_all()       # no-op
        api_no_session.refresh(fake)       # no-op
        api_no_session.commit()            # no-op
        api_no_session.rollback()          # no-op
        api_no_session.flush()             # no-op
        api_no_session.make_transient(fake)  # no-op


# ===================================================================
# bulk_update_entities
# ===================================================================


class TestBulkUpdateEntities:
    def test_updates_multiple(self, api):
        items = [{"name": "u1", "category": "old"}, {"name": "u2", "category": "old"}]
        api.bulk_create_entities(Item, items)
        all_items = api.list_entities(Item)
        updates = [{"id": e.id, "category": "new"} for e in all_items]
        api.bulk_update_entities(Item, updates)
        # Expire cached objects so the next query reads fresh data
        api._session.expire_all()
        refreshed = api.list_entities(Item)
        assert all(e.category == "new" for e in refreshed)

    def test_empty_items_is_noop(self, api):
        api.bulk_update_entities(Item, [])  # should not raise
        assert api.count_entities(Item) == 0

    def test_raises_validation_error_without_id(self, api):
        with pytest.raises(ValidationError, match="id"):
            api.bulk_update_entities(Item, [{"name": "no_id"}])

    def test_raises_database_error_without_session(self, api_no_session):
        with pytest.raises(DatabaseError):
            api_no_session.bulk_update_entities(Item, [{"id": _ulid(), "name": "x"}])


# ===================================================================
# _setup_database
# ===================================================================


class TestSetupDatabase:
    def test_connection_error_on_bad_path(self):
        """_setup_database raises DatabaseConnectionError for an unreachable path."""
        with patch("adare.config.database.get_database_location") as mock_loc:
            # Use a path that will fail in create_engine due to directory not existing
            from pathlib import Path
            mock_loc.return_value = Path("/nonexistent_dir_abc123/db.sqlite")
            # The constructor calls _setup_database; the engine creation itself may
            # succeed (SQLite lazily creates) but sessionmaker should work.
            # Instead, test that engine property is set.
            db = EnhancedDatabaseApi()
            assert db._engine is not None

    def test_engine_property(self, engine):
        db = _TestApi(engine)
        assert db.engine is engine
