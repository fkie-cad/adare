wal_frame_count
===============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Database
:Function Name: ``wal_frame_count``

**Tests the number of frames in the write-ahead log (-wal) of an SQLite database.**

Reads ``<dst>-wal`` and passes when the number of ``frames`` of the chosen kind satisfies
``comparison_type`` against ``expected_count``. The log is parsed per the
`SQLite WAL file format <https://www.sqlite.org/fileformat2.html#walformat>`_, without SQLite:
the 32-byte header (magic and the checksum byte order it selects, format version, page size,
checkpoint sequence, salts, header checksum), then every frame of a 24-byte frame header plus
one page. A copy of the WAL is parsed, never the original, and its SHA-256 is reported.

A WAL frame is *valid* when its salts equal the header's and its cumulative checksum matches.
SQLite replays the valid frames from the start of the file up to the last commit frame (a
frame whose "database size after commit" is nonzero). Frames after that are never read: frames
left over from before a WAL reset (a checkpoint restarted the log, a new writer overwrote its
start) and the frames of a transaction whose commit frame was never written.

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
     - **Required.** Path to the SQLite database; ``<dst>-wal`` is read. A missing ``-wal``
       next to an existing database counts as 0 frames; a missing database is an error.
       ``dst`` may also name the ``-wal`` file itself, which then must exist. A glob must
       match exactly one file.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the frame count with.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.
   * - ``frames``
     - string
     - **Optional.** Which frames to count. Default: ``valid``.

       - ``valid``: the frames SQLite replays (matching salts, intact checksum chain, up to
         the last commit frame)
       - ``commits``: the commit frames among them, one per transaction
       - ``all``: every complete frame in the file, including stale ones
       - ``stale``: ``all`` minus ``valid``

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: changes_not_checkpointed
       function: sqlite.wal_frame_count
       parameter:
         dst: /home/user/app/data.db
         expected_count: 1
         comparison_type: greater_equal
         frames: commits

     - name: wal_checkpointed_away
       function: sqlite.wal_frame_count
       parameter:
         dst: /home/user/app/data.db
         expected_count: 0

     - name: old_frames_after_reset
       function: sqlite.wal_frame_count
       parameter:
         dst: /home/user/app/data.db-wal
         expected_count: 1
         comparison_type: greater_equal
         frames: stale

Return Values
-------------

Every result after the WAL was read reports ``<frames> frames: <n>``, the comparison, all four
counts as ``frames: all=<n> valid=<n> commits=<n> stale=<n>``, the header fields (checksum byte
order, page size, checkpoint sequence, salts), bytes after the last complete frame if any,
and ``read snapshot: <name>-wal sha256=<hash>``. If the WAL changes while it is being copied, a
warning detail is added.

**Success**
  The count comparison holds. A missing ``-wal`` next to the database and an empty (0-byte)
  ``-wal`` have 0 frames of every kind.

**Failure**
  The WAL was read and the count comparison does not hold.

**Error**
  The database does not exist (or ``dst`` names a ``-wal`` that does not exist), a glob
  matches no file or more than one, the WAL cannot be read, or its header is invalid: shorter
  than 32 bytes, a wrong magic, a format version other than 3007000, a page size that is not a
  power of two from 512 to 65536, or a header checksum mismatch (SQLite would ignore such a
  WAL). Also a negative or non-integer ``expected_count``, an unknown ``comparison_type`` or
  ``frames``.

In host test mode ``<dst>-wal`` is pulled from the guest together with ``dst``.

See also
--------

- :doc:`row_count` and :doc:`query_result` with ``view: wal_added`` / ``wal_removed`` show which
  rows the WAL adds or removes compared with the main database file.
- :doc:`../text/occurrence_count` finds a value anywhere in the raw bytes of a file, including
  stale WAL frames.

Common use cases
----------------

**Changes not yet checkpointed**
  ``frames: commits`` with ``comparison_type: greater_equal`` after an action, while the
  application still holds the database open.

**Checkpoint ran**
  ``expected_count: 0`` after the application closed: the WAL was checkpointed and truncated or
  deleted.

**Leftovers of earlier transactions**
  ``frames: stale`` greater than 0: frames from before a WAL reset that SQLite no longer reads
  but whose pages may still hold earlier content.
