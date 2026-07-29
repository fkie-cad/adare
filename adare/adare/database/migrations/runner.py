"""
Ordered schema-migration runner for the ADARE SQLite databases.

Schema *creation* goes through ``Base.metadata.create_all()``, which builds
missing tables but never ALTERs an existing one. Any model change that adds a
column to a table that already exists therefore needs a migration, or an
existing installation ends up with a database the ORM cannot query
(``sqlite3.OperationalError: no such column: ...``).

This module turns the previously manual migration scripts into an ordered
registry with a per-database applied-ledger (``schema_migration`` table), so
schema drift heals itself:

* :data:`MIGRATIONS` lists every migration, oldest first. **The order is the
  contract — append only, never reorder or remove entries.**
* :func:`apply_pending` is called right after ``create_all`` when a database is
  opened, so an existing database is brought up to the current shape
  automatically (quietly — output only goes to the log).
* ``adare db migrate`` runs the same code path verbosely for operators.

Each migration module exposes ``upgrade(conn)`` operating on a
caller-supplied connection (a migration must never open a database API itself —
that would recurse through ``GlobalDatabaseApi.__init__``). Every ``upgrade()``
is idempotent, so a freshly created database — where ``create_all`` already
produced the current schema — simply runs a cheap no-op and gets stamped.
"""

import logging
from contextlib import redirect_stdout
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Literal

import sqlalchemy
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from adare.database.exceptions import DatabaseError

log = logging.getLogger(__name__)

Scope = Literal['global', 'project']

_PACKAGE = 'adare.database.migrations'

#: Name of the per-database ledger table recording applied migrations.
LEDGER_TABLE = 'schema_migration'


@dataclass(frozen=True)
class Migration:
    """A single schema migration: its ledger name, target database and module."""

    name: str
    scope: Scope
    module: str


#: Ordered migration registry — oldest first. APPEND ONLY.
MIGRATIONS: list[Migration] = [
    Migration(
        name='add_overlay_disk_path_to_dev_sessions',
        scope='global',
        module=f'{_PACKAGE}.add_overlay_disk_path_to_dev_sessions',
    ),
    Migration(
        name='add_run_directory_path_to_dev_sessions',
        scope='global',
        module=f'{_PACKAGE}.add_run_directory_path_to_dev_sessions',
    ),
    Migration(
        name='add_recipe_provenance_to_vm',
        scope='global',
        module=f'{_PACKAGE}.add_recipe_provenance_to_vm',
    ),
    Migration(
        name='add_name_to_dev_sessions',
        scope='global',
        module=f'{_PACKAGE}.add_name_to_dev_sessions',
    ),
    Migration(
        name='add_testfunction_versioning',
        scope='global',
        module=f'{_PACKAGE}.add_testfunction_versioning',
    ),
    Migration(
        name='add_testfunction_pins_to_tests',
        scope='project',
        module=f'{_PACKAGE}.add_testfunction_pins_to_tests',
    ),
    Migration(
        name='add_remote_identity_to_project_db',
        scope='project',
        module=f'{_PACKAGE}.add_remote_identity_to_project_db',
    ),
    Migration(
        name='add_unique_active_websocket_port_to_vm_instance',
        scope='global',
        module=f'{_PACKAGE}.add_unique_active_websocket_port_to_vm_instance',
    ),
]

# Applied-migration names per database URL. Keeps auto-apply at one SELECT per
# process per database instead of one per API construction.
_applied_cache: dict[str, set[str]] = {}


class _LogWriter:
    """File-like sink forwarding a migration's ``print`` output to the log."""

    def __init__(self, logger: logging.Logger, prefix: str = ''):
        self._log = logger
        self._prefix = prefix
        self._buffer = ''

    def write(self, chunk: str) -> int:
        self._buffer += chunk
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            if line.strip():
                self._log.info('%s%s', self._prefix, line.rstrip())
        return len(chunk)

    def flush(self) -> None:
        if self._buffer.strip():
            self._log.info('%s%s', self._prefix, self._buffer.strip())
        self._buffer = ''


def _adare_version() -> str | None:
    """Installed adare version, or None when running from an unmanaged tree."""
    try:
        return package_version('adare')
    except PackageNotFoundError:
        return None


def _cache_key(engine: sqlalchemy.Engine) -> str:
    return str(engine.url)


def _ensure_ledger(conn) -> None:
    """Create the applied-migration ledger table if it does not exist yet."""
    conn.execute(text(
        f"""
        CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
            name TEXT PRIMARY KEY,
            applied_at DATETIME,
            adare_version TEXT NULL
        )
        """
    ))


def _stamp(conn, name: str) -> None:
    """Record ``name`` as applied (same transaction as the migration itself)."""
    conn.execute(
        text(
            f"INSERT OR REPLACE INTO {LEDGER_TABLE} (name, applied_at, adare_version) "
            f"VALUES (:name, datetime('now'), :version)"
        ),
        {'name': name, 'version': _adare_version()},
    )


def _applied(engine: sqlalchemy.Engine) -> set[str]:
    """Names already applied to ``engine``'s database (cached per database URL)."""
    key = _cache_key(engine)
    if key in _applied_cache:
        return _applied_cache[key]

    with engine.begin() as conn:
        _ensure_ledger(conn)
        names = {row[0] for row in conn.execute(text(f"SELECT name FROM {LEDGER_TABLE}"))}

    _applied_cache[key] = names
    return names


def invalidate_cache(engine: sqlalchemy.Engine | None = None) -> None:
    """
    Forget cached ledger state for ``engine`` (or all databases when None).

    Must be called whenever a database file is deleted or replaced behind the
    ORM's back (``db reset``, ``db clean-install``) — otherwise the cache would
    claim migrations are applied to a database that no longer holds them.
    """
    if engine is None:
        _applied_cache.clear()
    else:
        _applied_cache.pop(_cache_key(engine), None)


def pending(engine: sqlalchemy.Engine, scope: Scope) -> list[Migration]:
    """Migrations of ``scope`` not yet applied to ``engine``'s database, in order."""
    applied = _applied(engine)
    return [m for m in MIGRATIONS if m.scope == scope and m.name not in applied]


def apply_pending(engine: sqlalchemy.Engine, scope: Scope, *, quiet: bool = True) -> list[str]:
    """
    Apply every pending migration of ``scope`` to ``engine``'s database.

    Each migration runs in its own transaction together with its ledger row, so
    a failure leaves the database at the last fully applied migration.

    Args:
        engine: Engine bound to the database to migrate.
        scope: ``'global'`` or ``'project'`` — selects the applicable migrations.
        quiet: Route migration output to the log instead of stdout (the default,
            used by auto-apply). ``adare db migrate`` passes ``quiet=False``.

    Returns:
        Names of the migrations applied by this call (empty if nothing pending).

    Raises:
        DatabaseError: If a migration fails; the database keeps every migration
            applied before the failing one.
    """
    todo = pending(engine, scope)
    if not todo:
        return []

    applied_now: list[str] = []
    for migration in todo:
        try:
            module = import_module(migration.module)
            with engine.begin() as conn:
                _ensure_ledger(conn)
                if quiet:
                    with redirect_stdout(_LogWriter(log, f'[{migration.name}] ')):
                        module.upgrade(conn)
                else:
                    print(f"Applying migration: {migration.name}")
                    module.upgrade(conn)
                _stamp(conn, migration.name)
        except (SQLAlchemyError, ImportError, OSError) as e:
            log.error("Schema migration '%s' failed: %s", migration.name, e, exc_info=True)
            _applied_cache.pop(_cache_key(engine), None)
            raise DatabaseError(
                log,
                f"Schema migration '{migration.name}' failed on {engine.url.database}: {e}",
                ['Run: adare --verbose db migrate'],
            ) from e

        _applied_cache.setdefault(_cache_key(engine), set()).add(migration.name)
        applied_now.append(migration.name)
        log.info("Applied schema migration '%s' to %s", migration.name, engine.url.database)

    return applied_now
