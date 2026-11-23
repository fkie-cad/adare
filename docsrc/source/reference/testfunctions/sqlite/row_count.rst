row_count
=========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Database
:Function Name: ``row_count``

**Tests the number of rows an SQL query returns on an SQLite database.**

Runs ``query`` and passes when the number of returned rows satisfies ``comparison_type`` against ``expected_count``. ``expected_count: 0`` asserts that no such record exists; a missing database or an SQL error is still an error, never a pass.

The database is queried exactly like ``sqlite.query_result``: the file and its ``-wal`` / ``-journal`` sidecars are copied to a temporary directory and only the copy is opened, so the evidence is not modified and changes that only live in the write-ahead log are counted (``view`` counts in the main database file alone, or only the rows the write-ahead log adds or removes). The SHA-256 of every queried file and the rows read are reported in the result details.

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
   * - ``view``
     - string
     - **Optional.** Which state of the database is counted (for a difference: its rows). All views come from one snapshot (the files are copied once). ``current``: the database as SQLite sees it, the write-ahead log replayed. ``main_file``: the main database file alone, ``<dst>-wal`` left out. ``wal_added``: result rows of ``current`` that are not in ``main_file``. ``wal_removed``: result rows of ``main_file`` that are not in ``current`` (deleted or changed in the WAL, still in the file). Differences compare whole rows as multisets, so select identifying columns: a changed row appears in both. A ``-journal`` is used in every view (see *Database Access* in :doc:`query_result`). Default: ``current``.

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

     # a row only in the write-ahead log, not yet checkpointed into the main file
     - name: entry_not_checkpointed
       function: sqlite.row_count
       parameter:
         dst: /home/user/app/data.db
         query: "SELECT id FROM items WHERE name = 'example'"
         expected_count: 1
         view: wal_added

     # deleted in the WAL, still in the main file
     - name: deleted_entry_still_in_file
       function: sqlite.row_count
       parameter:
         dst: /home/user/app/data.db
         query: "SELECT id FROM items WHERE name = 'secret-project'"
         expected_count: 1
         view: wal_removed

Return Values
-------------

Every result after the query ran reports ``query returned <n> rows``, the comparison, the rows
read as ``query result: [...]`` (cut after 2000 characters) and one
``queried snapshot: <file> sha256=<hash>`` per copied file; every view other than
``current`` also reports ``view: <name>``, the ``-wal`` sha256 and, for a difference, the row
counts of both sides.

**Success**
  The count comparison holds.

**Failure**
  The query ran and the count comparison does not hold.

**Error**
  The database does not exist, a glob matches no file or more than one, an SQL error (syntax,
  unknown table or column, a corrupt or unreadable database), an empty ``query``, a negative or
  non-integer ``expected_count``, an unknown ``comparison_type`` or ``view``.

See also
--------

- :doc:`query_result` checks the returned rows themselves (``expected_result``).
- :doc:`wal_frame_count` counts the frames and transactions in the write-ahead log.
- :doc:`../text/occurrence_count` finds a value anywhere in the raw database bytes, including
  freed pages that a query no longer returns.

Common use cases
----------------

**Record created exactly once**
  An action must add one row (one history entry, one bookmark), not zero and not two.

**Record removed**
  ``expected_count: 0`` after a delete or "clear history" action.

**Row not yet checkpointed**
  ``view: wal_added`` holds the rows that live only in the write-ahead log; ``view: wal_removed``
  the rows deleted there that the main file still holds.

**Growth of a table**
  ``comparison_type: greater_equal`` when an action may add a varying number of rows.
