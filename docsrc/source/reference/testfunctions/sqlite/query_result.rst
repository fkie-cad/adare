query_result
============

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Category: Database
:Function Name: ``query_result``

**Executes SQL query against SQLite database and validates result.**

This test function executes a SQL query against a SQLite database and validates the results based on expected row counts or specific result content. It supports complex result validation using placeholders and direct result comparison.

The query never runs on the database file itself. The database and its ``-wal`` / ``-journal`` sidecars are copied to a temporary directory and the copy is queried, so the evidence is not modified and changes that only live in the write-ahead log are included. The SHA-256 of every queried file is reported in the result details.

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
   * - ``expected_rows``
     - integer
     - **Optional.** Expected number of result rows. If specified, validates the row count.
   * - ``expected_result``
     - list
     - **Optional.** Expected query result as list of dictionaries. Supports placeholder matching.

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
         expected_rows: 1
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
         expected_rows: 3
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
         expected_rows: 0
       description: "Test sqlite_query_result with query returning no results"

     - name: test_sqlite_query_invalid_table
       function: sqlite.query_result
       expect_to_fail: true
       parameter:
         dst: '/home/adare/test_sqlite/test.db'
         query: 'SELECT * FROM nonexistent_table'
         expected_rows: 0
       description: "Test sqlite_query_result with invalid table"

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
  - Row count validation with ``expected_rows`` parameter
  - Exact result matching with ``expected_result`` parameter
  - Placeholder-based comparison for dynamic content

**Database Access**
  - The database file, ``<dst>-wal`` and ``<dst>-journal`` (when present) are copied to a
    temporary directory; SQLite only ever opens the copy, so the original files are never
    checkpointed, rolled back or otherwise modified
  - Committed transactions that are still in the write-ahead log (WAL mode, e.g. browser
    databases of a running application) are visible to the query; an interrupted transaction
    in a hot ``-journal`` is rolled back on the copy. ``-shm`` is not copied, SQLite rebuilds it
  - The SHA-256 of each copied file is reported as ``queried snapshot: <name> sha256=<hash>``
    in every result after the query ran, so the result is tied to the exact bytes queried
  - If any of the files changes while it is being copied, a warning detail is added because
    the snapshot may be inconsistent (e.g. the application was still writing)
  - In host test mode the sidecars are pulled from the guest together with ``dst`` (never from
    the pull cache); if a sidecar exists but cannot be pulled, the test ends with an error

Return Values
-------------

**Success**
  Returns success when query executes successfully and results match expectations

**Failure**
  Returns failure when:

  - Query result row count doesn't match expected count
  - Query result content doesn't match expected result
  - Query returns no results when results were expected
  - SQL syntax errors in the query
  - Database file doesn't exist (no empty database is created)
  - SQLite database corruption or connection issues

**Execution Error**
  Returns execution error when:

  - Database file cannot be read or copied (e.g. permission denied)
  - Invalid placeholder comparisons

Example Results
---------------

.. code-block:: yaml

   # Success case - row count match (WAL-mode database)
   result: success
   details:
     - "query returned 3 rows"
     - "queried snapshot: places.sqlite sha256=9f2c...e41a"
     - "queried snapshot: places.sqlite-wal sha256=0b7d...93c5"

   # Success case - specific result match
   result: success
   details:
     - "query returned 1 rows"

   # Failure case - row count mismatch
   result: failed
   details:
     - "expected 5 rows, got 3"

   # Failure case - result content mismatch
   result: failed
   details:
     - "query result does not match expected result. Got: [{'count': 3}]"

   # Failure case - SQL error
   result: failed
   details:
     - "SQLite error executing query: SELECT * FROM nonexistent_table - no such table: nonexistent_table"

   # Failure case - missing database
   result: failed
   details:
     - "database file /path/to/missing.db does not exist"