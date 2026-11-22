row_count
=========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Database
:Function Name: ``row_count``

**Tests the number of rows an SQL query returns on an SQLite database.**

Runs ``query`` and passes when the number of returned rows satisfies ``comparison_type`` against ``expected_count``. ``expected_count: 0`` asserts that no such record exists; a missing database or an SQL error is still an error, never a pass.

The database is queried exactly like ``sqlite.query_result``: the file and its ``-wal`` / ``-journal`` sidecars are copied to a temporary directory and only the copy is opened, so the evidence is not modified and changes that only live in the write-ahead log are counted. The SHA-256 of every queried file and the rows read are reported in the result details.

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
     - **Required.** Path to the SQLite database. A glob must match exactly one file.
   * - ``query``
     - string
     - **Required.** SQL to execute. Every returned row counts, so ``SELECT COUNT(*) ...`` returns one row; select the rows themselves instead.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the row count with. ``0`` asserts absence.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: one_history_entry
       function: sqlite.row_count
       parameter:
         dst: /home/user/data/app.db
         query: "SELECT id FROM items WHERE name LIKE '%example%'"
         expected_count: 1

     - name: entry_deleted
       function: sqlite.row_count
       parameter:
         dst: /home/user/data/app.db
         query: "SELECT id FROM items WHERE name = 'secret-project'"
         expected_count: 0

     - name: several_downloads
       function: sqlite.row_count
       parameter:
         dst: /home/user/data/app.db
         query: SELECT id FROM downloads
         expected_count: 3
         comparison_type: greater_equal

Return Values
-------------

Every result after the query ran reports ``query returned <n> rows``, the comparison, the rows
read as ``query result: [...]`` (cut after 2000 characters) and one
``queried snapshot: <file> sha256=<hash>`` per copied file.

**Success**
  The count comparison holds.

**Failure**
  The query ran and the count comparison does not hold.

**Error**
  The database does not exist, a glob matches no file or more than one, an SQL error (syntax,
  unknown table or column, a corrupt or unreadable database), an empty ``query``, a negative or
  non-integer ``expected_count``, or an unknown ``comparison_type``.

See also
--------

- :doc:`query_result` checks the returned rows themselves (``expected_result``).
- :doc:`../text/occurrence_count` finds a value anywhere in the raw database bytes, including
  freed pages that a query no longer returns.

Common use cases
----------------

**Record created exactly once**
  An action must add one row (one history entry, one bookmark), not zero and not two.

**Record removed**
  ``expected_count: 0`` after a delete or "clear history" action.

**Growth of a table**
  ``comparison_type: greater_equal`` when an action may add a varying number of rows.
