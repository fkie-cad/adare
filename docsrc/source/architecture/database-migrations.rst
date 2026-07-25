*******************
Database Migrations
*******************

ADARE stores its state in SQLite: one **global** database
(``~/.adare/state/global.db.sqlite3`` -- VMs, environments, test functions,
project registry, dev sessions) and one **project** database per project
(``<project>/.adare/project.db.sqlite3`` -- experiments, runs, test events).

Both are created from the SQLAlchemy models via
``Base.metadata.create_all()``. ``create_all`` creates *missing tables*, but it
never ``ALTER``\ s a table that already exists. A model change that adds a
column therefore has no effect on an installation that already has that table,
and the ORM then queries a column the database does not have::

   sqlite3.OperationalError: no such column: test_function_file.version

Migrations close that gap.

.. contents:: On this page
   :local:
   :depth: 2


How migrations are applied
==========================

Each migration is a module in ``adare/database/migrations/`` exposing an
idempotent ``upgrade(conn)``. :mod:`adare.database.migrations.runner` holds an
ordered registry (``MIGRATIONS``) and a per-database ledger table
(``schema_migration``: ``name``, ``applied_at``, ``adare_version``) recording
what has already run.

``apply_pending(engine, scope)`` is called right after ``create_all`` whenever a
database is opened:

* ``GlobalDatabaseApi._ensure_global_database()`` -- scope ``global``
* ``ProjectDatabaseApi._ensure_project_database()`` -- scope ``project``
* ``DevModeApi.__init__()`` -- scope ``global`` (it runs its own ``create_all``)

So schema drift heals itself: an installation that pulls a model change is
migrated the next time it runs *any* ADARE command. Auto-apply is quiet --
migration output goes to the logfile, visible with ``adare --verbose <command>``.

Fresh installations need no special handling: ``create_all`` has already
produced the current schema, so every ``upgrade()`` is a cheap no-op that is
then stamped in the ledger.

Each migration runs in its own transaction together with its ledger row, so a
failure leaves the database at the last fully applied migration. A failure is
raised as a ``DatabaseError`` suggesting ``adare --verbose db migrate``.


Applying migrations explicitly
==============================

``adare db migrate``
   Apply all pending migrations to the global database and to every registered
   project database, printing each one. Re-running reports
   ``Nothing pending``. Both ``make install`` and ``make update`` run it before
   ``adare testfunction sync``.

``adare db status``
   Reports pending migrations (informational -- pending migrations do not make
   the system invalid, they are applied on next use). Project entries are
   suffixed with the project name, e.g.
   ``add_testfunction_pins_to_tests [my-project]``.

``adare db repair``
   Reinitializes the global database and applies pending migrations, listing
   them under the actions taken.

A single migration can still be run on its own::

   python -m adare.database.migrations.add_testfunction_versioning

Inspect what has been applied with::

   sqlite3 ~/.adare/state/global.db.sqlite3 "SELECT * FROM schema_migration"


Adding a migration
==================

Whenever you add or change a column on an existing model, add a matching
migration:

#. **Write the module** in ``adare/database/migrations/``, exposing
   ``upgrade(conn)`` that operates on the *caller-supplied* connection::

      def upgrade(conn) -> None:
          """Add the fancy_flag column to vm (idempotent)."""
          existing = {row[1] for row in conn.execute(text("PRAGMA table_info(vm)"))}
          if not existing:
              print("· Table 'vm' not present, skipping.")
              return
          if 'fancy_flag' in existing:
              print("✓ Column 'fancy_flag' already exists, skipping.")
              return
          conn.execute(text("ALTER TABLE vm ADD COLUMN fancy_flag BOOLEAN NULL"))

   Rules for ``upgrade()``:

   * **Idempotent** -- it also runs against freshly created databases, where the
     column already exists. Check ``PRAGMA table_info`` first and use
     ``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT EXISTS``.
   * **Never open a database API** (``GlobalDatabaseApi``, ``VmApi``,
     ``DevModeApi``, ...). Opening one would recurse back into the migration
     runner. Use the connection you were given.
   * **Raise on failure** -- do not return a bool or catch errors; the runner
     owns the transaction, logging and reporting.
   * ``print()`` is fine; auto-apply redirects it into the log.

#. **Add a ``run_migration()`` wrapper** so
   ``python -m adare.database.migrations.<name>`` keeps working: open the right
   API, then ``with api.engine.begin() as conn: upgrade(conn)``.

#. **Append an entry to** ``MIGRATIONS`` in
   :mod:`adare.database.migrations.runner`, with the correct scope
   (``'global'`` for anything in ``GlobalBase`` -- including ``dev_sessions`` --
   and ``'project'`` for ``ProjectBase`` models):

   .. code-block:: python

      Migration(
          name='add_fancy_flag_to_vm',
          scope='global',
          module=f'{_PACKAGE}.add_fancy_flag_to_vm',
      ),

   The registry order is the contract: **append only**. Never reorder or remove
   entries -- existing installations identify applied migrations by name and
   apply the rest in list order.

#. **Verify** against a real installation: ``adare db status`` lists the new
   migration as pending, ``adare db migrate`` applies it, a second run reports
   nothing pending, and ``PRAGMA table_info(<table>)`` shows the column.
