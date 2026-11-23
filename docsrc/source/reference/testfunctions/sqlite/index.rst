SQLite
==============

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Functions: 5
:Category: Database Validation

.. adare-testfunction-collection:: sqlite

Snapshots and the Write-Ahead Log
---------------------------------

SQLite only ever opens a copy. ``dst``, ``<dst>-wal`` and ``<dst>-journal`` (when present) are
copied once to a temporary directory and the copy is queried, so the original files are never
checkpointed, rolled back or otherwise modified. ``-shm`` is not copied; SQLite rebuilds it. Every
result after the query ran reports ``queried snapshot: <name> sha256=<hash>`` per copied file, and
a warning when a file changed while it was copied (the application was still writing).

``view`` chooses the state a query sees, all from that one snapshot:

- ``current`` (default): the database as SQLite sees it, the committed WAL frames replayed.
- ``main_file``: a second copy made from the snapshot with the database and ``-journal`` but not
  ``-wal``, so SQLite opens it with an empty write-ahead log, also when the header says WAL mode.
- ``wal_added`` / ``wal_removed``: the query runs on both copies and the multiset difference of
  the rows is reported, so both sides show the same moment. A row whose value changed in the WAL
  is in ``wal_added`` with its new value and in ``wal_removed`` with its old one.

A hot ``-journal`` is rolled back in every view: it belongs to a rollback-journal database, not to
the WAL, and querying without it would show the half-written pages of a transaction that never
committed. Views other than ``current`` report ``view: <name>``, the ``-wal`` sha256 (or that
there is none) and, for the differences, the row counts of both sides.

``wal_frame_count`` parses the ``-wal`` per the
`SQLite WAL file format <https://www.sqlite.org/fileformat2.html#walformat>`_, without SQLite: the
32-byte header (magic, format version, page size, checkpoint sequence, salts, header checksum),
then frames of a 24-byte frame header plus one page. A frame is *valid* when its salts equal the
header's and its cumulative checksum matches; SQLite replays the valid frames up to the last
commit frame. Frames after that are *stale*: left over from before a WAL reset, or from a
transaction whose commit frame was never written.

In host test mode the sidecars are pulled from the guest together with ``dst`` (never from the
pull cache); a sidecar that exists but cannot be pulled ends the test with an error.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_sqlite.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: sqlite-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   query_result
   row_count
   wal_frame_count
   values_compare
   free_space_pattern_count
