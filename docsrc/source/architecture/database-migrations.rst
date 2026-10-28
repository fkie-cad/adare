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

A migration can also repair *data*. ``delete_orphan_run_rows`` (project scope)
deletes the rows that run deletions left behind while they relied on the ORM
cascade alone (foreign keys are off in SQLite): ``action_execution`` rows whose
non-NULL ``experiment_run_id`` names no run, ``experiment_run_files`` rows no
run references, and the ``log_file`` rows only they referenced. Only runs write
execution rows with a run id (dev sessions write none), so such a row is always
a deleted run's leftover; rows without a run id are kept. A data-repair
migration must only delete what is provably unreferenced, and it must stay
set-based (no per-row Python, no reading blob columns) because it runs on every
project database when it is first opened. Run deletion itself goes through
:func:`adare.database.api.run_cleanup.delete_runs`, which removes a run's rows
along with the run.

``move_parent_event_keys`` (project scope) repairs a column that held the wrong
kind of value. ``event.parent_event_id`` is declared as a foreign key to
``event.id``, but the event writers stored the enclosing action's *key* there
(its ``event_group_id``), never an event id, so every nested event was a
foreign-key violation (``PRAGMA foreign_key_check``; 44k of them in one project).
The migration adds ``event.parent_group_id`` with the index
``ix_event_parent_group_id`` -- the name SQLAlchemy gives ``index=True``, so fresh
and migrated databases agree -- and moves every ``parent_event_id`` that names no
event into it, clearing ``parent_event_id``. A value that does name an event is a
real parent and is kept. Writers now set ``parent_group_id`` only; the old column
stays because SQLite cannot drop a foreign-key column without rebuilding the
table.

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


Connection settings
===================

Every SQLite engine ADARE creates -- the process-wide engines of the database
APIs (``database/api/base.py``) and the throwaway schema engines of
``adare db migrate`` / ``db status`` (``database/init.py``) -- goes through
``create_sqlite_engine()`` / ``configure_sqlite()``. A ``connect`` event
listener sets these pragmas on every new connection:

``PRAGMA busy_timeout=30000``
   Wait up to 30 seconds for a competing writer instead of failing at once with
   ``database is locked`` (SQLAlchemy's default was 5 seconds). Set first, so
   the switch to WAL below also waits.

``PRAGMA journal_mode=WAL``
   Write-ahead logging: readers keep reading the last committed state while a
   writer is active, and a writer is not blocked by readers. The CLI, the web
   API and a running experiment can then use the same database at once. WAL is
   *persistent* -- it is recorded in the database file -- so it sticks even for
   tools that open the file without ADARE. An in-memory database reports
   ``memory`` instead (WAL does not apply to it). WAL needs shared memory and
   does not work on network file systems; keep ``~/.adare`` and project
   directories on a local disk. Switching to WAL writes to the file, which
   fails on a read-only database file or directory; the hook then logs the
   failure at debug level and keeps the file's current journal mode, so a
   read-only database stays readable (the other pragmas still apply).

``PRAGMA synchronous=NORMAL``
   The recommended level for WAL: commits no longer fsync, only checkpoints
   do. A power loss can lose the most recent commits but never corrupts the
   database.

``foreign_keys`` stays **off** by decision: existing databases were written
without enforcement, and turning it on could make previously accepted writes and
deletes fail.

A WAL database keeps two sidecar files next to it, ``<name>-wal`` and
``<name>-shm`` (rollback mode used ``<name>-journal``). They belong to the
database: deleting only the main file and keeping a stale sidecar can corrupt a
new database of the same name. ``adare db reset`` and ``adare db clean-install``
therefore call ``remove_database_files()``, which disposes the cached engines
(``dispose_engines()``) and then removes the main file together with all
sidecars. Removing a project closes the pooled connections before its directory
-- and the project database in it -- is deleted.

Why this is not a migration
---------------------------

Migrations run inside a transaction (one per migration, together with its
ledger row), and these settings cannot be made there:

* Changing ``journal_mode`` to or from WAL, and ``VACUUM``, cannot run inside a
  transaction -- SQLite rejects them (``cannot change into wal mode from within
  a transaction`` / ``cannot VACUUM from within a transaction``).
* ``PRAGMA foreign_keys`` is a silent no-op inside a transaction, and it is
  per-connection state rather than a property of the file: setting it once in a
  migration would not affect any later connection. The same is true of
  ``busy_timeout`` and ``synchronous``.

Per-connection settings therefore belong in the connect hook, where every
pooled connection receives them before its first statement. Never put a
``PRAGMA journal_mode``, ``PRAGMA foreign_keys`` or ``VACUUM`` into an
``upgrade(conn)``.

Maintenance outside migrations
==============================

Work that rewrites a lot of data or needs ``VACUUM`` is an operator command, not a
migration: ``adare db compact`` (:mod:`adare.database.maintenance`) strips the
screenshot copies old ``action_execution`` rows kept in ``result_data`` -- only
images that are byte-for-byte identical to the screenshot file on disk, nothing
else -- and then vacuums, on a raw autocommit connection. It first makes sure
nothing may write meanwhile: no other process holds the write lock, no
unfinished run of the project showed activity in the last 30 minutes, and no
dev session is live. ``adare db check`` reports ``quick_check``,
``foreign_key_check`` and orphan counts read-only; its run-files counts reuse
the SQL of ``delete_orphan_run_rows``, so the two cannot drift apart. The pages
a data-repair migration frees stay in the file until ``adare db compact`` (or any
``VACUUM``) runs. See :doc:`../reference/cli` for both commands.
