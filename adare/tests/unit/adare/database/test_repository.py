"""Tests for the generic Repository[T] base class."""

import pytest
import sqlalchemy
import ulid as ulid_lib
from sqlalchemy import Column, String
from sqlalchemy.orm import DeclarativeBase, sessionmaker

pytestmark = pytest.mark.unit


def _ulid() -> str:
    return str(ulid_lib.ULID())


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, default="default")


@pytest.fixture
def repo():
    """Create an in-memory repository for testing."""
    from adare.database.api.repository import Repository

    class ItemRepository(Repository[Item]):
        model = Item

    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    repo = ItemRepository.__new__(ItemRepository)
    repo.db_path = None
    repo._engine = engine
    repo._session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    repo._session = None
    repo.__enter__()
    yield repo
    repo.__exit__(None, None, None)
    engine.dispose()


class TestRepositoryFindById:

    def test_find_by_id_returns_entity(self, repo):
        uid = _ulid()
        repo.save(id=uid, name="test")
        repo._session.commit()
        entity = repo.find_by_id(uid)
        assert entity is not None
        assert entity.name == "test"

    def test_find_by_id_returns_none_when_missing(self, repo):
        assert repo.find_by_id(_ulid()) is None


class TestRepositorySave:

    def test_save_creates_entity(self, repo):
        entity = repo.save(name="created")
        assert entity.id is not None
        assert entity.name == "created"

    def test_save_with_custom_id(self, repo):
        uid = _ulid()
        entity = repo.save(id=uid, name="custom")
        assert entity.id == uid


class TestRepositoryFindAll:

    def test_find_all_returns_entities(self, repo):
        repo.save(name="a", category="cat1")
        repo.save(name="b", category="cat2")
        repo._session.flush()
        entities = repo.find_all()
        assert len(entities) == 2

    def test_find_all_with_filters(self, repo):
        repo.save(name="a", category="cat1")
        repo.save(name="b", category="cat2")
        repo._session.flush()
        entities = repo.find_all(filters={"category": "cat1"})
        assert len(entities) == 1
        assert entities[0].name == "a"

    def test_find_all_with_limit(self, repo):
        for i in range(5):
            repo.save(name=f"item{i}")
        repo._session.flush()
        entities = repo.find_all(limit=3)
        assert len(entities) == 3


class TestRepositoryCount:

    def test_count_all(self, repo):
        repo.save(name="a")
        repo.save(name="b")
        repo._session.flush()
        assert repo.count() == 2

    def test_count_with_filter(self, repo):
        repo.save(name="a", category="x")
        repo.save(name="b", category="y")
        repo._session.flush()
        assert repo.count(filters={"category": "x"}) == 1


class TestRepositoryDeleteById:

    def test_delete_by_id(self, repo):
        entity = repo.save(name="to-delete")
        repo._session.flush()
        entity_id = entity.id
        repo.delete_by_id(entity_id)
        repo._session.flush()
        assert repo.find_by_id(entity_id) is None


class TestRepositoryFindOrCreate:

    def test_find_or_create_creates(self, repo):
        entity, created = repo.find_or_create(
            filters={"name": "new-item"},
            defaults={"category": "new"}
        )
        assert created is True
        assert entity.name == "new-item"

    def test_find_or_create_finds_existing(self, repo):
        repo.save(id=_ulid(), name="existing", category="old")
        repo._session.flush()
        entity, created = repo.find_or_create(
            filters={"name": "existing"},
            defaults={"category": "new"}
        )
        assert created is False
        assert entity.category == "old"
