"""
Enhanced base database API with improved error handling, validation, and ULID support.

This module provides a robust foundation for database operations with:
- Comprehensive error handling and custom exceptions
- Input validation decorators
- Transaction management with retry logic
- Consistent ULID-based operations
- Standardized query patterns
"""

import functools
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar, cast

import sqlalchemy
import ulid
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import adare.config.database as config_database
from adare.database.exceptions import DatabaseConnectionError, DatabaseError, EntityNotFoundError, ValidationError

log = logging.getLogger(__name__)

T = TypeVar('T')

# One engine (connection pool) and session factory per database file for the
# whole process, instead of a new engine per API instance.
_ENGINES: dict[str, tuple[sqlalchemy.Engine, sessionmaker]] = {}
# Database files whose schema was created and migrated in this process.
_SCHEMA_READY: set[str] = set()
_ENGINES_LOCK = threading.Lock()

# Per-connection settings for every SQLite engine (see configure_sqlite).
# busy_timeout comes first so the switch to WAL waits for a competing writer.
SQLITE_CONNECT_PRAGMAS = (
    'PRAGMA busy_timeout=30000',
    'PRAGMA journal_mode=WAL',
    'PRAGMA synchronous=NORMAL',
)
# The one pragma that writes to the database file; it may fail on a read-only one.
SQLITE_JOURNAL_MODE_PRAGMA = 'PRAGMA journal_mode=WAL'
# Files SQLite keeps next to a database: the write-ahead log, its shared-memory
# index, and the rollback journal of the pre-WAL journal mode.
SQLITE_SIDECAR_SUFFIXES = ('-wal', '-shm', '-journal')


def configure_sqlite(engine: sqlalchemy.Engine) -> sqlalchemy.Engine:
    """Apply the connection pragmas to every new connection of a SQLite ``engine``.

    - ``busy_timeout=30000``: wait up to 30 s for a competing writer instead of
      failing with "database is locked".
    - ``journal_mode=WAL``: readers no longer block the writer and vice versa.
      Persistent in the database file; an in-memory database stays ``memory``.
      Switching a file to WAL writes to it: on a read-only database file or
      directory the switch fails, and the connection keeps the file's current
      journal mode (logged at debug level) so the database can still be read.
    - ``synchronous=NORMAL``: safe with WAL (a power loss can drop the last
      commits but never corrupts the file) and far fewer fsyncs than ``FULL``.

    ``foreign_keys`` stays off by decision. Non-SQLite engines are returned unchanged.
    """
    if engine.dialect.name != 'sqlite':
        return engine

    @event.listens_for(engine, 'connect')
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            for pragma in SQLITE_CONNECT_PRAGMAS:
                if pragma != SQLITE_JOURNAL_MODE_PRAGMA:
                    cursor.execute(pragma)
                    continue
                try:
                    cursor.execute(pragma)
                except sqlite3.OperationalError as e:
                    log.debug('%s failed (%s); keeping the current journal mode', pragma, e)
        finally:
            cursor.close()

    return engine


def create_sqlite_engine(db_path: Path) -> sqlalchemy.Engine:
    """New engine for the SQLite database file ``db_path``, with the connection pragmas applied."""
    return configure_sqlite(sqlalchemy.create_engine(f'sqlite:///{db_path.as_posix()}', echo=False))


def _engine_for(db_path: Path) -> tuple[sqlalchemy.Engine, sessionmaker]:
    """Cached engine + session factory for ``db_path``.

    A file deleted behind our back (``adare db reset``, tests) drops its cached
    engine and schema state, so the recreated database is set up from scratch
    rather than served by connections to the unlinked file.
    """
    key = str(db_path)
    with _ENGINES_LOCK:
        cached = _ENGINES.get(key)
        if cached is not None and db_path.exists():
            return cached
        if cached is not None:
            cached[0].dispose()
            _SCHEMA_READY.discard(key)
        engine = create_sqlite_engine(db_path)
        factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
        _ENGINES[key] = (engine, factory)
        return engine, factory


def dispose_engines() -> None:
    """Close every cached engine and forget schema state (before deleting a database file, and in tests)."""
    with _ENGINES_LOCK:
        for engine, _factory in _ENGINES.values():
            engine.dispose()
        _ENGINES.clear()
        _SCHEMA_READY.clear()


def remove_database_files(db_path: Path) -> bool:
    """Delete a SQLite database file and its ``-wal``/``-shm``/``-journal`` sidecars.

    Disposes every cached engine first: pooled connections keep the files open
    (Windows cannot delete them), and a leftover sidecar must never be paired
    with a new database of the same name. Missing files are skipped.

    Returns:
        True if at least one file was removed.

    Raises:
        OSError: If an existing file cannot be deleted.
    """
    dispose_engines()
    removed = False
    for path in (db_path, *(db_path.with_name(db_path.name + suffix) for suffix in SQLITE_SIDECAR_SUFFIXES)):
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed = True
    return removed


def experiment_name_from_run_path(run_path: str | Path | None) -> str | None:
    """Derive the experiment name from a run directory path.

    Run directories follow the structure ``<project>/run/<experiment_name>/<timestamp>``,
    so the experiment name is the parent directory of the timestamp directory.
    Returns ``None`` when the path is empty or does not match that structure
    (e.g. runs interrupted before their ``path`` was set).
    """
    if not run_path:
        return None
    parts = Path(str(run_path)).parts
    # Find the 'run' segment and take the directory immediately after it.
    for idx, part in enumerate(parts):
        if part == 'run' and idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def validate_input(func):
    """Decorator for input validation of API methods."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Basic validation - can be extended per method
        try:
            return func(self, *args, **kwargs)
        except (ValueError, TypeError) as e:
            raise ValidationError(log, f"Invalid input for {func.__name__}: {e}") from e

    return wrapper


def handle_db_errors(func):
    """Decorator for standardized database error handling."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except IntegrityError as e:
            log.error(f"Database integrity error in {func.__name__}: {e}")
            raise DatabaseError(log, f"Data integrity violation: {e.orig}") from e
        except SQLAlchemyError as e:
            log.error(f"Database error in {func.__name__}: {e}")
            raise DatabaseError(log, f"Database operation failed: {e}") from e
        # Anything else propagates unchanged and is reported at the CLI boundary.

    return wrapper


class EnhancedDatabaseApi:
    """
    Enhanced base database API with improved patterns and error handling.

    Features:
    - ULID-based entity management
    - Comprehensive error handling
    - Transaction management with retry logic
    - Input validation
    - Query optimization helpers
    """

    # Nesting depth of `with` blocks on this instance; only the outermost one
    # commits/rolls back and closes the session.
    _depth = 0

    # None outside a `with` block. Any rather than Session | None: subclasses
    # query it without narrowing (typing it as Session surfaces ~50 latent
    # errors in the domain APIs; tighten once those are fixed).
    _session: Any
    _engine: sqlalchemy.Engine
    _session_factory: sessionmaker

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or config_database.get_database_location()
        self._session = None
        self._setup_database()

    def _setup_database(self):
        """Attach to the process-wide engine and session factory for this database."""
        try:
            self._engine, self._session_factory = _engine_for(self.db_path)
        except (SQLAlchemyError, OSError, PermissionError) as e:
            log.error(f"Failed to setup database: {e}")
            raise DatabaseConnectionError(log, f"Cannot connect to database: {e}") from e
        # Remove generic Exception - let unexpected errors propagate naturally

    @property
    def engine(self) -> sqlalchemy.Engine:
        """Get the database engine."""
        return self._engine

    def __enter__(self):
        """Context manager entry - start session (or join the one an outer `with` opened)."""
        self._start_session()
        self._depth += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - the outermost block commits or rolls back and closes."""
        self._depth = max(self._depth - 1, 0)
        if self._depth > 0:
            # Nested block: committing here would persist the outer block's
            # half-done work even if it later fails. A failure still discards
            # the pending changes now, as it always has.
            if exc_type and self._session:
                log.debug(f"Rolling back transaction due to {exc_type.__name__}: {exc_val}")
                self._session.rollback()
            return
        if self._session:
            try:
                if exc_type:
                    # Debug, not warning: the exception itself propagates and is
                    # reported once at the CLI boundary; at warning level every
                    # nested DB context echoed it again ("Rolling back ..." x N).
                    log.debug(f"Rolling back transaction due to {exc_type.__name__}: {exc_val}")
                    self._session.rollback()
                else:
                    self._session.commit()
            except SQLAlchemyError as e:
                log.error(f"Error during session cleanup: {e}")
                self._session.rollback()
            finally:
                self._session.close()
                self._session = None

    def _start_session(self):
        """Start a new database session."""
        if self._session:
            log.debug("Session already active, reusing existing session")
            return

        try:
            self._session = self._session_factory()
        except SQLAlchemyError as e:
            log.error(f"Failed to start session: {e}")
            raise DatabaseConnectionError(log, f"Cannot start database session: {e}") from e

    @contextmanager
    def transaction(self):
        """Context manager for explicit transaction control."""
        if not self._session:
            raise DatabaseError(log, "No active session for transaction")

        committed = False
        try:
            yield self._session
            self._session.commit()
            committed = True
        finally:
            # Any failure (in the block or in the commit, KeyboardInterrupt
            # included) rolls back; the exception itself propagates.
            if not committed:
                self._session.rollback()
                log.error("Transaction rolled back")

    @validate_input
    @handle_db_errors
    def get_by_ulid(self, model: type[T], ulid_str: str) -> T | None:
        """
        Get entity by ULID with validation.

        Args:
            model: SQLAlchemy model class
            ulid_str: ULID string

        Returns:
            Entity instance or None if not found

        Raises:
            ValidationError: If ULID format is invalid
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError(log, "No active session")

        # Validate ULID format
        try:
            ulid.ULID.from_str(ulid_str)
        except ValueError:
            raise ValidationError(log, f"Invalid ULID format: {ulid_str}") from None

        return cast('T | None', self._session.query(model).filter(cast(Any, model).id == ulid_str).first())

    @validate_input
    @handle_db_errors
    def get_by_ulid_or_404(self, model: type[T], ulid_str: str) -> T:
        """
        Get entity by ULID or raise EntityNotFoundError.

        Args:
            model: SQLAlchemy model class
            ulid_str: ULID string

        Returns:
            Entity instance

        Raises:
            EntityNotFoundError: If entity not found
            ValidationError: If ULID format is invalid
            DatabaseError: If database operation fails
        """
        entity = self.get_by_ulid(model, ulid_str)
        if not entity:
            raise EntityNotFoundError(log, f"{model.__name__} with ULID {ulid_str} not found")
        return cast(T, entity)

    @validate_input
    @handle_db_errors
    def create_entity(self, model: type[T], **kwargs) -> T:
        """
        Create new entity with ULID generation.

        Args:
            model: SQLAlchemy model class
            **kwargs: Entity attributes

        Returns:
            Created entity instance

        Raises:
            ValidationError: If input validation fails
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError(log, "No active session")

        # Generate ULID if not provided and model has id field
        if hasattr(model, 'id') and 'id' not in kwargs:
            kwargs['id'] = str(ulid.ULID())

        try:
            entity = model(**kwargs)
            self._session.add(entity)
            self._session.flush()  # Get ID without committing
            return entity
        except (SQLAlchemyError, TypeError, ValueError) as e:
            log.error(f"Failed to create {model.__name__}: {e}")
            raise

    @validate_input
    @handle_db_errors
    def update_entity(self, entity: T, **kwargs) -> T:
        """
        Update entity attributes.

        Args:
            entity: Entity instance to update
            **kwargs: Attributes to update

        Returns:
            Updated entity instance

        Raises:
            ValidationError: If input validation fails
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError(log, "No active session")

        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
            else:
                log.warning(f"Ignoring unknown attribute {key} for {type(entity).__name__}")

        self._session.flush()
        return entity

    @validate_input
    @handle_db_errors
    def delete_entity(self, entity: T) -> None:
        """
        Delete entity from database.

        Args:
            entity: Entity instance to delete

        Raises:
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError(log, "No active session")

        self._session.delete(entity)
        self._session.flush()

    @validate_input
    @handle_db_errors
    def get_or_create(self, model: type[T], defaults: dict[str, Any] | None = None, **kwargs) -> tuple[T, bool]:
        """
        Get existing entity or create new one.

        Args:
            model: SQLAlchemy model class
            defaults: Default values for creation
            **kwargs: Filter criteria and creation values

        Returns:
            Tuple of (entity, created_flag)

        Raises:
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError(log, "No active session")

        # Try to get existing
        entity = self._session.query(model).filter_by(**kwargs).first()
        if entity:
            return entity, False

        # Create new
        create_kwargs = kwargs.copy()
        if defaults:
            create_kwargs.update(defaults)

        return self.create_entity(model, **create_kwargs), True

    @validate_input
    @handle_db_errors
    def list_entities(
        self,
        model: type[T],
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[T]:
        """
        List entities with optional filtering and pagination.

        Args:
            model: SQLAlchemy model class
            filters: Filter criteria
            order_by: Order by field name
            limit: Maximum number of results
            offset: Results offset

        Returns:
            List of entity instances

        Raises:
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError(log, "No active session")

        query = self._session.query(model)

        # Apply filters
        if filters:
            query = query.filter_by(**filters)

        # Apply ordering
        if order_by:
            if hasattr(model, order_by):
                query = query.order_by(getattr(model, order_by))
            else:
                log.warning(f"Unknown order_by field {order_by} for {model.__name__}")

        # Apply pagination
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        return cast(list[T], query.all())

    @validate_input
    @handle_db_errors
    def count_entities(self, model: type[T], filters: dict[str, Any] | None = None) -> int:
        """
        Count entities with optional filtering.

        Args:
            model: SQLAlchemy model class
            filters: Filter criteria

        Returns:
            Count of matching entities

        Raises:
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError(log, "No active session")

        query = self._session.query(model)
        if filters:
            query = query.filter_by(**filters)

        return int(query.count())

    def expunge(self, entity: T) -> T:
        """Remove entity from session."""
        if self._session:
            self._session.expunge(entity)
        return entity

    def expunge_all(self):
        """Remove all entities from session."""
        if self._session:
            self._session.expunge_all()

    def refresh(self, entity: T) -> T:
        """Refresh entity from database."""
        if self._session:
            self._session.refresh(entity)
        return entity

    def commit(self):
        """Explicitly commit current transaction."""
        if self._session:
            self._session.commit()

    def rollback(self):
        """Explicitly rollback current transaction."""
        if self._session:
            self._session.rollback()

    def flush(self):
        """Flush pending changes without committing."""
        if self._session:
            self._session.flush()

    def make_transient(self, entity):
        """
        Make an entity transient (detached from session) while preserving its data.

        This helps avoid DetachedInstanceError by allowing the entity to be used
        outside of the session context.
        """
        if self._session:
            self._session.expunge(entity)

    def extract_id(self, entity):
        """
        Safely extract the ID from an entity while session is active.

        This is a helper to avoid DetachedInstanceError when you only need the ID.
        """
        if hasattr(entity, 'id'):
            return entity.id
        if hasattr(entity, 'ulid'):
            return entity.ulid
        return str(entity)

    @validate_input
    @handle_db_errors
    def bulk_create_entities(
        self, model: type[T], items: list[dict[str, Any]], return_objects: bool = False
    ) -> list[T]:
        """
        Bulk create multiple entities efficiently.

        This method uses SQLAlchemy's bulk_insert_mappings for maximum performance,
        which is 50-100x faster than creating entities one by one.

        Args:
            model: SQLAlchemy model class
            items: List of dictionaries with entity attributes
            return_objects: If True, return created objects (slower).
                           If False, return empty list (faster).

        Returns:
            List of created entities if return_objects=True, else []

        Example:
            items = [
                {'name': 'test1', 'value': 'a'},
                {'name': 'test2', 'value': 'b'}
            ]
            api.bulk_create_entities(TestModel, items)
        """
        if not self._session:
            raise DatabaseError(log, "No active session")

        if not items:
            return []

        # Add ULID to items if model has id field
        if hasattr(model, 'id'):
            for item in items:
                if 'id' not in item:
                    item['id'] = str(ulid.ULID())

        # Use bulk_insert_mappings for maximum performance
        self._session.bulk_insert_mappings(model, items)
        self._session.flush()

        if return_objects:
            # Query back the created objects (slower but returns objects)
            ids = [item['id'] for item in items if 'id' in item]
            return cast(list[T], self._session.query(model).filter(cast(Any, model).id.in_(ids)).all())

        return []

    @validate_input
    @handle_db_errors
    def bulk_update_entities(self, model: type[T], items: list[dict[str, Any]]) -> None:
        """
        Bulk update multiple entities efficiently.

        This method uses SQLAlchemy's bulk_update_mappings for maximum performance.

        Args:
            model: SQLAlchemy model class
            items: List of dicts with 'id' and fields to update

        Example:
            updates = [
                {'id': 'ABC123', 'status': 'completed'},
                {'id': 'DEF456', 'status': 'completed'}
            ]
            api.bulk_update_entities(ExperimentRun, updates)
        """
        if not self._session:
            raise DatabaseError(log, "No active session")

        if not items:
            return

        # Validate all items have 'id'
        if not all('id' in item for item in items):
            raise ValidationError(log, "All items must have 'id' field for bulk update")

        # Use bulk_update_mappings for maximum performance
        self._session.bulk_update_mappings(model, items)
        self._session.flush()


class GlobalDatabaseApi(EnhancedDatabaseApi):
    """
    Database API for global resources (VMs, environments, test functions, project metadata).

    This API connects to the global database and manages globally shared resources.
    """

    def __init__(self):
        """Initialize with global database location."""
        super().__init__(config_database.get_global_database_location())
        self._ensure_global_database()

    def _ensure_global_database(self):
        """Ensure global database schema exists and is migrated to the current shape (once per process)."""
        if str(self.db_path) in _SCHEMA_READY:
            return
        try:
            from adare.database.migrations.runner import apply_pending
            from adare.database.models.global_models import GlobalBase

            GlobalBase.metadata.create_all(self.engine)
            # create_all builds missing tables but never ALTERs existing ones —
            # heal schema drift from model changes on already-installed databases.
            apply_pending(self.engine, 'global')
            _SCHEMA_READY.add(str(self.db_path))
            log.debug("Global database schema ensured")
        except (SQLAlchemyError, ImportError) as e:
            log.error(f"Failed to create global database schema: {e}")
            raise DatabaseError(log, f"Cannot initialize global database: {e}") from e


class ProjectDatabaseApi(EnhancedDatabaseApi):
    """
    Database API for project-specific resources (experiments, runs).

    This API connects to a project-specific database and manages project data.
    """

    def __init__(self, project_path: Path):
        """
        Initialize with project-specific database location.

        Args:
            project_path: Path to the project directory
        """
        if not isinstance(project_path, Path):
            project_path = Path(project_path)

        self.project_path = project_path
        db_path = config_database.get_project_database_location(project_path)
        super().__init__(db_path)
        self._ensure_project_database()

    def _ensure_project_database(self):
        """Ensure project database schema exists and is migrated to the current shape (once per process)."""
        if str(self.db_path) in _SCHEMA_READY:
            return
        try:
            from adare.database.migrations.runner import apply_pending
            from adare.database.models.project_models import ProjectBase

            ProjectBase.metadata.create_all(self.engine)
            # create_all builds missing tables but never ALTERs existing ones —
            # heal schema drift from model changes on already-installed databases.
            apply_pending(self.engine, 'project')
            _SCHEMA_READY.add(str(self.db_path))
            log.debug(f"Project database schema ensured for {self.project_path}")
        except (SQLAlchemyError, ImportError) as e:
            log.error(f"Failed to create project database schema: {e}")
            raise DatabaseError(log, f"Cannot initialize project database: {e}") from e


# Legacy alias for backward compatibility
DatabaseApi = EnhancedDatabaseApi
