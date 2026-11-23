values_compare
==============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Database
:Function Name: ``values_compare``

**Compares the values two SQL queries return on SQLite databases or on two views of one (earlier/later, within a tolerance, A = B + offset).**

Passes when ``value(query on view) <comparison_type> value(other_query on other_view) + offset``
holds. Each value is the first column of the single row its query returns. Both values are
compared as numbers or as points in time; the time parameters say how to read timestamps
(ISO 8601 and RFC 2822 by default, ``time_format`` for others, ``timestamp_epoch`` for numeric
counts).

With one database both sides come from one snapshot: the database and its ``-wal`` /
``-journal`` are copied once and every view is derived from that copy, so the two values show
the same moment (see *Database Access* in :doc:`query_result`). This turns "the write-ahead log
adds exactly one row" into a single check: ``SELECT count(*)`` on ``current`` equal to the same
count on ``main_file`` plus one.

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
     - **Required.** SQL returning the first value. It must return exactly one row; its first column is compared. No row fails, more than one row is an error.
   * - ``other_query``
     - string
     - **Optional.** SQL returning the second value; same rules. Default: ``query`` again (on ``other_dst`` / ``other_view``).
   * - ``other_dst``
     - string
     - **Optional.** Database of the second value, with its own snapshot. Default: ``dst``. In host test mode it is pulled from the guest with its sidecars.
   * - ``view``
     - string
     - **Optional.** State of ``dst`` the first query sees: ``current`` (default, the write-ahead log replayed), ``main_file`` (``<dst>-wal`` left out) or ``commit:N`` (the write-ahead log replayed through its N-th transaction; ``commit:-1`` the last, ``commit:0`` = ``main_file``), as in :doc:`query_result`. The differences ``wal_added`` / ``wal_removed`` are not values and are an error here.
   * - ``other_view``
     - string
     - **Optional.** State the second query sees; same values. Default: ``view``.
   * - ``comparison_type``
     - string
     - **Optional.** How the first value relates to the second: ``equals`` (default), ``not_equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal`` (``less`` = earlier for timestamps).
   * - ``value_type``
     - string
     - **Optional.** ``auto`` (default: numbers if both values are numbers, else timestamps), ``number`` or ``timestamp``.
   * - ``tolerance``
     - number
     - **Optional.** Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
   * - ``offset``
     - number
     - **Optional.** Added to the second value before comparing (seconds for timestamps, may be negative): ``first <comparison_type> second + offset``.
   * - ``time_format``
     - string
     - **Optional.** ``strptime`` format of text timestamps; default ISO 8601 or RFC 2822.
   * - ``timestamp_epoch``
     - int
     - **Optional.** Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
   * - ``timestamp_unit``
     - string
     - **Optional.** Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
   * - ``utc_offset``
     - string
     - **Optional.** Zone of timestamps without one (``+02:00``); default UTC.

Usage Example
-------------

.. code-block:: yaml

   tests:
     # the write-ahead log adds exactly one row, in one check
     - name: one_row_only_in_wal
       function: sqlite.values_compare
       parameter:
         dst: /data/app/state.db
         query: SELECT count(*) FROM items
         view: current
         other_view: main_file
         offset: 1

     # a value raised by the second transaction in the WAL
     - name: counter_raised_by_second_transaction
       function: sqlite.values_compare
       parameter:
         dst: /data/app/state.db
         query: SELECT value FROM counters WHERE name = 'opened'
         view: commit:2
         other_view: commit:1
         comparison_type: greater

     # two timestamps of one record in order
     - name: modified_after_created
       function: sqlite.values_compare
       parameter:
         dst: /data/app/state.db
         query: SELECT modified FROM items WHERE id = 7
         other_query: SELECT created FROM items WHERE id = 7
         comparison_type: greater_equal
         timestamp_epoch: 1970
         timestamp_unit: us

     # the same count in a second database
     - name: copy_has_the_same_rows
       function: sqlite.values_compare
       parameter:
         dst: /data/app/state.db
         other_dst: /data/app/backup/state.db
         query: SELECT count(*) FROM items

Return Values
-------------

Every result after both queries ran reports the two values
(``query '<sql>' (<view>) = '<value>', other_query '<sql>' (<view>) = '<value>'``), the
comparison, the view of each side (``query: view: ...``, ``other_query: view: ...``, with the
``-wal`` sha256 and, for ``commit:N``, the WAL frame it stops at) and one
``queried snapshot: <file> sha256=<hash>`` per copied file (``queried snapshot (other_dst): ...``
for the second database).

**Success**
  The comparison holds.

**Failure**
  Both queries ran, and a query returned no row or the comparison does not hold.

**Error**
  A database does not exist or a glob matches no file or several; an SQL error; a query that
  returns more than one row; a value that is no number or timestamp (``NULL``, a BLOB); an
  invalid ``view`` / ``other_view`` or ``commit:N`` out of range; an empty ``query``; invalid
  comparison or timestamp parameters.

See also
--------

- :doc:`query_result` and :doc:`row_count` check the rows of one view.
- :doc:`../json/values_compare` compares two values of one JSON file the same way.
