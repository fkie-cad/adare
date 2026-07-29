"""
Database migrations for ADARE.

Each module in this package exposes ``upgrade(conn)`` — an idempotent schema
change applied to a caller-supplied SQLAlchemy connection — plus a
``run_migration()`` wrapper for ``python -m adare.database.migrations.<name>``.

:mod:`adare.database.migrations.runner` holds the ordered registry and applies
pending migrations automatically when a database is opened. ``adare db migrate``
runs them verbosely.
"""
