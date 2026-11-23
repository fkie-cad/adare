query_result
============

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Category: Database
:Function Name: ``query_result``

**Executes SQL query against SQLite database and validates result.**

This test function executes a SQL query against a SQLite database and validates the results based on expected row counts or specific result content. It supports complex result validation using placeholders and direct result comparison.

The query never runs on the database file itself. The database and its ``-wal`` / ``-journal`` sidecars are copied to a temporary directory and the copy is queried, so the evidence is not modified and changes that only live in the write-ahead log are included. The SHA-256 of every queried file is reported in the result details. With ``wal: ignore`` the ``-wal`` is left out and the main database file alone is queried.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``dst``
     - string
     - **Required.** The SQLite database file path. Supports glob patterns for dynamic path resolution.
   * - ``query``
     - string
     - **Required.** The SQL query to execute against the database.
   * - ``expected_count``
     - integer
     - **Optional.** Expected number of result rows, compared with ``comparison_type``. A negative number or a non-integer is an error. To only count rows use :doc:`row_count`.
   * - ``expected_result``
     - list
     - **Optional.** Expected query result as list of dictionaries. Supports placeholder matching.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal`` for ``expected_count``. Default: ``equals``.
   * - ``wal``
     - string
     - **Optional.** ``apply`` queries the database as SQLite sees it, with the write-ahead log replayed; ``ignore`` leaves ``<dst>-wal`` out of the copy and queries the main file alone, as if the WAL did not exist. A ``-journal`` is copied either way (see *Database Access*). Default: ``apply``.

Timestamps stored as numbers (Unix seconds or milliseconds, microseconds since 1601) are
compared in ``expected_result`` with ``!timestamp`` and its ``epoch``/``unit`` options; see
"Numeric timestamps" under ``!timestamp`` in :doc:`/reference/actions`.

Usage Example
-------------

Row Count Validation
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_sqlite_query_count
       function: sqlite.query_result
       parameter:
         dst: '/home/adare/test_sqlite/test.db'
         query: 'SELECT COUNT(*) as count FROM users'
         expected_count: 1
       description: "Test sqlite_query_result with COUNT query"

Specific Result Validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_sqlite_query_specific_result
       function: sqlite.query_result
       parameter:
         dst: '/home/adare/test_sqlite/test.db'
         query: 'SELECT COUNT(*) as count FROM users WHERE role = "Admin"'
         expected_result: [{"count": 2}]
       description: "Test sqlite_query_result with specific expected result"

Multi-Row Results
~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_sqlite_query_all_users
       function: sqlite.query_result
       parameter:
         dst: '/home/adare/test_sqlite/test.db'
         query: 'SELECT id, name, role FROM users ORDER BY id'
         expected_result: [
           {"id": 1, "name": "John Doe", "role": "Admin"},
           {"id": 2, "name": "Jane Smith", "role": "User"},
           {"id": 3, "name": "Bob Johnson", "role": "Admin"}
         ]
       description: "Test sqlite_query_result returning all users"

Single Record Lookup
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_sqlite_query_single_user
       function: sqlite.query_result
       parameter:
         dst: '/home/adare/test_sqlite/test.db'
         query: 'SELECT name, email FROM users WHERE id = 1'
         expected_result: [{"name": "John Doe", "email": "john@example.com"}]
       description: "Test sqlite_query_result with single user lookup"

JOIN Queries
~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_sqlite_query_join
       function: sqlite.query_result
       parameter:
         dst: '/home/adare/test_sqlite/test.db'
         query: 'SELECT u.name, p.title FROM users u JOIN posts p ON u.id = p.user_id WHERE u.role = "Admin"'
         expected_count: 3
       description: "Test sqlite_query_result with JOIN query"

Aggregation Queries
~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_sqlite_query_aggregation
       function: sqlite.query_result
       parameter:
         dst: '/home/adare/test_sqlite/test.db'
         query: 'SELECT role, COUNT(*) as count FROM users GROUP BY role'
         expected_result: [
           {"role": "Admin", "count": 2},
           {"role": "User", "count": 1}
         ]
       description: "Test sqlite_query_result with aggregation"

Expected Failure Cases
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_sqlite_query_no_results
       function: sqlite.query_result
       parameter:
         dst: '/home/adare/test_sqlite/test.db'
         query: 'SELECT * FROM users WHERE id = 999'
         expected_count: 0
       description: "Test sqlite_query_result with query returning no results"

     - name: test_sqlite_query_wrong_count
       function: sqlite.query_result
       expect_to_fail: true
       parameter:
         dst: '/home/adare/test_sqlite/test.db'
         query: 'SELECT * FROM users'
         expected_count: 10
       description: "Test sqlite_query_result with a wrong expected count"

Rows Only in the Write-Ahead Log
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A row that is committed but not yet checkpointed into the main file is found with the default
``wal: apply`` and missing with ``wal: ignore``. Two tests express "only in the WAL":

.. code-block:: yaml

   tests:
     - name: entry_in_database
       function: sqlite.query_result
       parameter:
         dst: /home/user/app/data.db
         query: "SELECT id FROM items WHERE name = 'example'"
         expected_count: 1
     - name: entry_not_in_main_file
       function: sqlite.query_result
       parameter:
         dst: /home/user/app/data.db
         query: "SELECT id FROM items WHERE name = 'example'"
         expected_count: 0
         wal: ignore

:doc:`wal_frame_count` counts the frames and transactions the WAL holds.

``expect_to_fail`` inverts only a pass or a failure. A database that cannot be evaluated (missing
file, SQL error) ends with an error, and an error stays an error.

Common Use Cases
----------------

**Database Content Validation**
  Verify that database contains expected records with correct data

**User Data Verification**
  Check user accounts, roles, and permissions stored in SQLite databases

**Application Data Testing**
  Validate application-specific data stored in SQLite databases

**Configuration Database Testing**
  Ensure configuration data is properly stored and accessible

**Forensic Database Analysis**
  Analyze SQLite databases created by applications for forensic artifacts

Query Features
--------------

**SELECT Statements**
  - Full support for SELECT queries with WHERE, ORDER BY, GROUP BY clauses
  - JOIN operations across multiple tables
  - Aggregate functions (COUNT, SUM, AVG, etc.)

**Result Validation**
  - Row count validation with ``expected_count`` parameter
  - Exact result matching with ``expected_result`` parameter
  - Placeholder-based comparison for dynamic content

**Database Access**
  - The database file, ``<dst>-wal`` and ``<dst>-journal`` (when present) are copied to a
    temporary directory; SQLite only ever opens the copy, so the original files are never
    checkpointed, rolled back or otherwise modified
  - Committed transactions that are still in the write-ahead log (WAL mode, e.g. databases
    of a running application) are visible to the query; an interrupted transaction
    in a hot ``-journal`` is rolled back on the copy. ``-shm`` is not copied, SQLite rebuilds it
  - ``wal: ignore`` copies the database and ``-journal`` but not ``-wal``, so SQLite opens the
    copy with an empty write-ahead log, also when the database header says WAL mode. The
    detail ``wal ignore: not applied: <name>-wal sha256=<hash>`` names the log that was left
    out. A hot ``-journal`` is still rolled back: it belongs to a rollback-journal database,
    not to the WAL, and querying the main file without it would show the half-written pages
    of a transaction that never committed
  - The SHA-256 of each copied file is reported as ``queried snapshot: <name> sha256=<hash>``
    in every result after the query ran, so the result is tied to the exact bytes queried
  - If any of the files changes while it is being copied, a warning detail is added because
    the snapshot may be inconsistent (e.g. the application was still writing)
  - In host test mode the sidecars are pulled from the guest together with ``dst`` (never from
    the pull cache); if a sidecar exists but cannot be pulled, the test ends with an error

Return Values
-------------

A failure means the query ran and its result did not match; an error means the database could
not be evaluated. Every result after the query ran reports the rows read as
``query result: [...]`` (cut after 2000 characters, with the row count).

**Success**
  Returns success when query executes successfully and results match expectations

**Failure**
  Returns failure when the query ran and:

  - Query result row count doesn't match expected count
  - Query result content doesn't match expected result
  - Query returns no results when results were expected

**Execution Error**
  Returns execution error when:

  - Database file doesn't exist (no empty database is created)
  - SQL errors: syntax, unknown table or column, a corrupt or unreadable database
  - The glob in ``dst`` does not match exactly one file
  - ``wal`` is neither ``apply`` nor ``ignore``
  - Database file cannot be read or copied (e.g. permission denied)
  - Invalid placeholder comparisons

Example Results
---------------

.. code-block:: yaml

   # Success case - row count match (WAL-mode database)
   result: success
   details:
     - "query returned 1 rows"
     - "query result: [{'n': 1}]"
     - "queried snapshot: app.db sha256=9f2c...e41a"
     - "queried snapshot: app.db-wal sha256=0b7d...93c5"

   # Failure case - row count mismatch
   result: failed
   details:
     - "expected 5 rows, got 3"
     - "query result: [{'id': 1}, {'id': 2}, {'id': 3}]"

   # Failure case - result content mismatch
   result: failed
   details:
     - "query result does not match expected result. Got: [{'count': 3}]"

   # Error case - SQL error
   result: error
   details:
     - "SQLite error executing query: SELECT * FROM nonexistent_table - no such table: nonexistent_table"

   # Error case - missing database
   result: error
   details:
     - "database file /path/to/missing.db does not exist"