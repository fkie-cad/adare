"""
Database initialization system for global and project databases.

This module provides functions to initialize, validate, and manage
both global and project-specific databases in the new architecture.
"""

import logging
from pathlib import Path
from typing import Any

import sqlalchemy
from sqlalchemy.exc import SQLAlchemyError

from adare.config.configdirectory import ENVIRONMENTS_DIR, VMS_DIR
from adare.config.database import get_global_database_location, get_project_database_location
from adare.database.api.base import GlobalDatabaseApi, ProjectDatabaseApi
from adare.database.exceptions import DatabaseError
from adare.database.fixtures import fixture_stages, fixture_status
from adare.database.migrations.runner import Scope, apply_pending, invalidate_cache, pending

log = logging.getLogger(__name__)


class DatabaseInitializationError(DatabaseError):
    """Raised when database initialization fails."""
    pass


def ensure_global_directories_exist() -> bool:
    """
    Ensure global storage directories exist.

    Returns:
        True if directories exist or were successfully created

    Raises:
        DatabaseInitializationError: If directory creation fails
    """
    try:
        # Create global VMs directory
        VMS_DIR.mkdir(parents=True, exist_ok=True)
        log.debug(f"Global VMs directory ensured: {VMS_DIR}")

        # Create global environments directory
        ENVIRONMENTS_DIR.mkdir(parents=True, exist_ok=True)
        log.debug(f"Global environments directory ensured: {ENVIRONMENTS_DIR}")

        return True
    except Exception as e:
        log.error(f"Failed to create global directories: {e}")
        raise DatabaseInitializationError(log, f"Cannot create global directories: {e}") from e


def ensure_global_database_exists() -> bool:
    """
    Ensure the global database exists and is properly initialized.

    Returns:
        True if database exists or was successfully created

    Raises:
        DatabaseInitializationError: If initialization fails
    """
    try:
        # Create global database API (which auto-initializes schema)
        with GlobalDatabaseApi():
            log.info("Global database initialized successfully")
            return True
    except Exception as e:
        log.error(f"Failed to initialize global database: {e}")
        raise DatabaseInitializationError(log, f"Cannot initialize global database: {e}") from e


def ensure_project_database_exists(project_path: Path) -> bool:
    """
    Ensure a project database exists and is properly initialized.

    Args:
        project_path: Path to the project directory

    Returns:
        True if database exists or was successfully created

    Raises:
        DatabaseInitializationError: If initialization fails
    """
    try:
        if not isinstance(project_path, Path):
            project_path = Path(project_path)

        # Create project database API (which auto-initializes schema)
        with ProjectDatabaseApi(project_path) as api:
            # Load essential fixtures for the project
            fixture_status(api._session)
            fixture_stages(api._session)
            log.info(f"Project database initialized successfully for {project_path}")
            return True
    except Exception as e:
        log.error(f"Failed to initialize project database for {project_path}: {e}")
        raise DatabaseInitializationError(log, f"Cannot initialize project database: {e}") from e


def initialize_database_system() -> dict[str, Any]:
    """
    Initialize the complete database system (global + ensure directory structure).

    Returns:
        Dictionary with initialization results
    """
    results = {
        'global_db_initialized': False,
        'global_db_location': None,
        'errors': []
    }

    try:
        # Ensure global directories exist first
        ensure_global_directories_exist()
        log.info("Global directories initialized successfully")

        # Initialize global database
        global_db_location = get_global_database_location()
        results['global_db_location'] = str(global_db_location)

        if ensure_global_database_exists():
            results['global_db_initialized'] = True
            log.info("Database system initialized successfully")
        else:
            results['errors'].append("Failed to initialize global database")

    except Exception as e:
        error_msg = f"Database system initialization failed: {e}"
        log.error(error_msg)
        results['errors'].append(error_msg)

    return results


def _engine_for(db_path: Path) -> sqlalchemy.Engine:
    """Create a throwaway engine for a database file (schema work only)."""
    return sqlalchemy.create_engine(f'sqlite:///{db_path.as_posix()}')


def _registered_project_paths() -> list[Path]:
    """Paths of all projects registered in the global database that still exist."""
    from adare.database.models.global_models import Project

    with GlobalDatabaseApi() as api:
        paths = [Path(project.path) for project in api._session.query(Project).all() if project.path]

    return [path for path in paths if path.exists()]


def _pending_names(db_path: Path, scope: Scope) -> list[str]:
    """Names of pending migrations for an existing database file."""
    if not db_path.exists():
        return []

    engine = _engine_for(db_path)
    try:
        return [migration.name for migration in pending(engine, scope)]
    finally:
        engine.dispose()


def get_pending_migrations() -> list[str]:
    """
    List schema migrations not yet applied, across the global and project databases.

    Project entries are suffixed with the project name, e.g.
    ``add_testfunction_pins_to_tests [my-project]``.

    Pending migrations are not an error — they are applied automatically the
    next time the affected database is opened (or explicitly by ``adare db migrate``).
    """
    names: list[str] = []

    global_db_location = get_global_database_location()
    if not global_db_location.exists():
        return names

    # Capture global pending names before any API construction auto-applies them.
    names.extend(_pending_names(global_db_location, 'global'))

    for project_path in _registered_project_paths():
        project_db = get_project_database_location(project_path)
        names.extend(
            f"{name} [{project_path.name}]"
            for name in _pending_names(project_db, 'project')
        )

    return names


def migrate_database_system(quiet: bool = False) -> dict[str, Any]:
    """
    Apply all pending schema migrations to the global and project databases.

    Schema creation via ``create_all`` never ALTERs existing tables, so model
    changes that add columns are carried by migrations. They are applied
    automatically when a database is opened; this function is the explicit
    operator entry point behind ``adare db migrate``.

    Args:
        quiet: Route migration output to the log instead of stdout.

    Returns:
        Dictionary with ``migrated`` (bool), ``applied`` (list of migration
        names) and ``errors`` (list of str).
    """
    results: dict[str, Any] = {
        'migrated': False,
        'applied': [],
        'errors': []
    }

    # --- global database -----------------------------------------------------
    try:
        from adare.database.models.global_models import GlobalBase

        engine = _engine_for(get_global_database_location())
        try:
            GlobalBase.metadata.create_all(engine)
            results['applied'].extend(apply_pending(engine, 'global', quiet=quiet))
        finally:
            engine.dispose()
    except (DatabaseError, SQLAlchemyError, OSError) as e:
        log.error(f"Global database migration failed: {e}")
        results['errors'].append(f"Global database migration failed: {e}")

    # --- project databases ---------------------------------------------------
    try:
        project_paths = _registered_project_paths()
    except (DatabaseError, SQLAlchemyError, OSError) as e:
        log.error(f"Could not list registered projects: {e}")
        results['errors'].append(f"Could not list registered projects: {e}")
        project_paths = []

    for project_path in project_paths:
        project_db = get_project_database_location(project_path)
        if not project_db.exists():
            log.debug(f"Project database does not exist yet, skipping: {project_path}")
            continue

        try:
            from adare.database.models.project_models import ProjectBase

            engine = _engine_for(project_db)
            try:
                ProjectBase.metadata.create_all(engine)
                results['applied'].extend(
                    f"{name} [{project_path.name}]"
                    for name in apply_pending(engine, 'project', quiet=quiet)
                )
            finally:
                engine.dispose()
        except (DatabaseError, SQLAlchemyError, OSError) as e:
            log.error(f"Project database migration failed for {project_path}: {e}")
            results['errors'].append(f"Project database migration failed for {project_path}: {e}")

    results['migrated'] = not results['errors']
    return results


def validate_database_integrity() -> dict[str, Any]:
    """
    Validate the integrity of the database system.

    Returns:
        Dictionary with validation results
    """
    results = {
        'valid': True,
        'global_db_exists': False,
        'global_db_location': None,
        'global_db_accessible': False,
        'schema_version_valid': True,
        'pending_migrations': [],
        'errors': []
    }

    try:
        # Check if global database exists
        global_db_location = get_global_database_location()
        results['global_db_location'] = str(global_db_location)
        results['global_db_exists'] = global_db_location.exists()

        # Pending migrations are informational: they are applied automatically
        # on the next database open, so they never make the system invalid.
        try:
            results['pending_migrations'] = get_pending_migrations()
        except (DatabaseError, SQLAlchemyError, OSError) as e:
            log.warning(f"Could not determine pending migrations: {e}")
            results['errors'].append(f"Could not determine pending migrations: {e}")

        if results['global_db_exists']:
            # Test global database accessibility
            try:
                with GlobalDatabaseApi() as api:
                    # Try a simple query to test database accessibility
                    from sqlalchemy import text
                    api._session.execute(text("SELECT 1"))
                    results['global_db_accessible'] = True
                    log.debug("Global database is accessible")
            except Exception as e:
                results['valid'] = False
                results['errors'].append(f"Global database not accessible: {e}")
        else:
            results['valid'] = False
            results['errors'].append("Global database does not exist")

    except Exception as e:
        results['valid'] = False
        results['errors'].append(f"Database validation failed: {e}")
        log.error(f"Database validation error: {e}")

    return results


def validate_project_database(project_path: Path) -> dict[str, Any]:
    """
    Validate a specific project database.

    Args:
        project_path: Path to the project directory

    Returns:
        Dictionary with validation results
    """
    results = {
        'valid': True,
        'db_exists': False,
        'db_accessible': False,
        'project_path': str(project_path),
        'errors': []
    }

    try:
        if not isinstance(project_path, Path):
            project_path = Path(project_path)

        # Check if project database exists
        project_db_location = get_project_database_location(project_path)
        results['db_exists'] = project_db_location.exists()

        if results['db_exists']:
            # Test project database accessibility
            try:
                with ProjectDatabaseApi(project_path) as api:
                    # Try a simple query to test database accessibility
                    from sqlalchemy import text
                    api._session.execute(text("SELECT 1"))
                    results['db_accessible'] = True
                    log.debug(f"Project database accessible for {project_path}")
            except Exception as e:
                results['valid'] = False
                results['errors'].append(f"Project database not accessible: {e}")
        else:
            # Project database not existing is not necessarily an error
            # It will be created when first needed
            log.debug(f"Project database does not exist for {project_path} (will be created when needed)")

    except Exception as e:
        results['valid'] = False
        results['errors'].append(f"Project database validation failed: {e}")
        log.error(f"Project database validation error for {project_path}: {e}")

    return results


def get_database_status() -> dict[str, Any]:
    """
    Get comprehensive status of the database system.

    Returns:
        Dictionary with complete database system status
    """
    status = {
        'system_initialized': False,
        'global_database': {},
        'architecture_version': '2.0',  # New architecture version
        'timestamp': None
    }

    try:
        from datetime import datetime
        status['timestamp'] = datetime.now().isoformat()

        # Validate database integrity
        integrity_results = validate_database_integrity()
        status['global_database'] = integrity_results

        # System is considered initialized if global database is accessible
        status['system_initialized'] = integrity_results.get('global_db_accessible', False)

        log.debug(f"Database system status: {'OK' if status['system_initialized'] else 'NOT INITIALIZED'}")

    except Exception as e:
        log.error(f"Error getting database status: {e}")
        status['global_database']['errors'] = [f"Status check failed: {e}"]

    return status


def repair_database_system() -> dict[str, Any]:
    """
    Attempt to repair the database system by reinitializing components.

    Returns:
        Dictionary with repair results
    """
    results = {
        'repaired': False,
        'actions_taken': [],
        'errors': []
    }

    try:
        log.info("Starting database system repair...")

        # Try to reinitialize global database
        try:
            if ensure_global_database_exists():
                results['actions_taken'].append("Reinitialized global database")
                log.info("Global database repaired successfully")
        except Exception as e:
            results['errors'].append(f"Failed to repair global database: {e}")

        # Bring every database up to the current schema shape
        migration_results = migrate_database_system(quiet=True)
        for name in migration_results['applied']:
            results['actions_taken'].append(f"Applied schema migration: {name}")
        results['errors'].extend(migration_results['errors'])

        # Validate repair success
        validation = validate_database_integrity()
        results['repaired'] = validation.get('valid', False) and not migration_results['errors']

        if results['repaired']:
            log.info("Database system repair completed successfully")
        else:
            log.error("Database system repair failed")
            results['errors'].extend(validation.get('errors', []))

    except Exception as e:
        error_msg = f"Database repair process failed: {e}"
        log.error(error_msg)
        results['errors'].append(error_msg)

    return results


def clean_install_database_system() -> dict[str, Any]:
    """
    Perform a clean installation of the database system.

    WARNING: This will remove existing global database!

    Returns:
        Dictionary with installation results
    """
    results = {
        'installed': False,
        'actions_taken': [],
        'errors': []
    }

    try:
        log.warning("Starting clean database system installation...")

        # Remove existing global database if it exists
        global_db_location = get_global_database_location()
        if global_db_location.exists():
            global_db_location.unlink()
            # The ledger went with the file — drop the cached applied-state so
            # the fresh database is stamped again.
            invalidate_cache()
            results['actions_taken'].append("Removed existing global database")
            log.info("Removed existing global database")

        # Initialize fresh database system
        init_results = initialize_database_system()
        if init_results.get('global_db_initialized', False):
            results['actions_taken'].append("Created fresh global database")
            results['installed'] = True
            log.info("Clean database installation completed successfully")
        else:
            results['errors'].extend(init_results.get('errors', []))

    except Exception as e:
        error_msg = f"Clean database installation failed: {e}"
        log.error(error_msg)
        results['errors'].append(error_msg)

    return results
