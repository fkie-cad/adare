"""
Generic Repository[T] base for type-safe database operations.

Provides a cleaner interface over EnhancedDatabaseApi by binding
operations to a specific model type, eliminating the need to pass
the model class to every method call.

Usage:
    class ProjectRepository(Repository[Project]):
        model = Project

    with ProjectRepository() as repo:
        project = repo.find_by_id("01ABC")
        all_projects = repo.find_all()
        new_project = repo.save(name="test", path="/tmp/test")
        repo.delete_by_id("01ABC")
"""

import logging
from typing import Generic, TypeVar

from adare.database.api.base import EnhancedDatabaseApi
from adare.database.exceptions import EntityNotFoundError

log = logging.getLogger(__name__)

T = TypeVar('T')


class Repository(EnhancedDatabaseApi, Generic[T]):
    """
    Generic repository providing type-safe CRUD operations for a specific model.

    Subclasses must set the `model` class attribute to their SQLAlchemy model class.
    """

    model: type[T]

    def find_by_id(self, ulid_str: str) -> T | None:
        """Find entity by ULID, returns None if not found."""
        return self.get_by_ulid(self.model, ulid_str)

    def find_by_id_or_raise(self, ulid_str: str) -> T:
        """Find entity by ULID, raises EntityNotFoundError if not found."""
        return self.get_by_ulid_or_404(self.model, ulid_str)

    def find_all(self, filters: dict | None = None, limit: int | None = None,
                 offset: int | None = None, order_by: str | None = None) -> list[T]:
        """Find all entities matching optional filters."""
        return self.list_entities(self.model, filters=filters, limit=limit,
                                  offset=offset, order_by=order_by)

    def count(self, filters: dict | None = None) -> int:
        """Count entities matching optional filters."""
        return self.count_entities(self.model, filters=filters)

    def save(self, **kwargs) -> T:
        """Create a new entity with the given attributes."""
        return self.create_entity(self.model, **kwargs)

    def save_many(self, entities_data: list[dict], return_objects: bool = False) -> list[T]:
        """Create multiple entities at once."""
        return self.bulk_create_entities(self.model, entities_data, return_objects=return_objects)

    def delete_by_id(self, ulid_str: str) -> None:
        """Delete entity by ULID."""
        entity = self.find_by_id_or_raise(ulid_str)
        self.delete_entity(entity)

    def find_or_create(self, filters: dict, defaults: dict | None = None) -> tuple[T, bool]:
        """Find existing entity or create new one. Returns (entity, created)."""
        return self.get_or_create(self.model, defaults=defaults, **filters)
