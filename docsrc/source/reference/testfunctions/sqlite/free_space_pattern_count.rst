free_space_pattern_count
========================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Database
:Function Name: ``free_space_pattern_count``

**Tests how often a text, byte pattern or regex occurs in the free space of an SQLite database (deleted, recoverable data).**

Deleting a row does not erase its bytes unless ``PRAGMA secure_delete`` is on: they stay in the
database file until SQLite reuses the space. This test parses the file per the SQLite file
format, without SQLite, locates the free space and counts the occurrences of ``pattern`` in it:

* **freelist** pages: pages no longer in use, chained from the header (trunk pages listing leaf
  pages). A leaf page counts whole, a trunk page from the end of its list of leaf page numbers.
  The overflow pages of a deleted large row end up here;
* **freeblocks**: freed cells inside a b-tree page, chained from the page header;
* **unallocated** space of each b-tree page: between the end of the cell pointer array and the
  start of the cell content area.

The reserved bytes at the end of each page and fragments of fewer than 4 bytes are not
searched. Regions never overlap, and occurrences are counted per region, so a match never spans
two regions. B-tree pages are recognised by their page type byte; pointer-map pages
(auto-vacuum databases) and the lock-byte page are skipped.

.. note::

   What is recoverable depends on what SQLite did. It can leave a record in the file **twice**:
   when a b-tree page is split, the old page keeps its cells (as unallocated space) next to the
   copies on the new pages, so a deleted record can match once per copy, and a live record can
   match in the free space too. And it can **overwrite** freed data: when it rewrites or merges
   pages (for example the tree collapsing back into its root after a large row was deleted),
   the stale cells and freeblocks of the rewritten page are gone, even though an earlier delete
   in the same transaction is still on a page that became a freelist page. Use
   ``comparison_type: greater_equal`` unless the exact number of copies is the point.

Combine it with :doc:`row_count` (``expected_count: 0``) to show that a record is gone from the
live data but still recoverable from the file.

.. warning::

   **Free space is not every stale byte.** ``expected_count: 0`` here proves only that the text is
   not in the free space; it can still be in the file. What this test does *not* search:

   * **Index interior cells are not a gap.** An index is a b-tree whose interior cells are index
     entries (not copies of leaf keys). Deleting an entry on an interior page replaces it with the
     entry before it, and the old cell becomes a freeblock or unallocated space, which is searched.
   * **Table interior pages** keep the *rowids* of deleted rows as dividers until the page is
     rebalanced or the table rewritten (``secure_delete`` does not remove them). They hold numbers,
     not text, and a pattern search cannot single them out (a rowid is a short varint).
   * **``sqlite_stat4``** (after ``ANALYZE`` or ``PRAGMA optimize``) stores up to 24 sampled index
     keys per index as live rows. A deleted row whose key was sampled stays there, even with
     ``secure_delete``, until the next ANALYZE. A query reads it:
     ``SELECT 1 FROM sqlite_stat4 WHERE instr(sample, CAST('text' AS BLOB)) > 0``.
   * **Full-text indexes** (FTS5: ``<name>_data``; FTS3/4: ``<name>_segments``) keep the terms of a
     deleted document in their segments until a merge or ``optimize``, again with ``secure_delete``.
     Terms are stored prefix-compressed, so only the part after the shared prefix may match.
   * **The unused tail of an overflow page in use.** When SQLite frees a page and takes it again as
     the last overflow page of a big value within one transaction, the bytes after the value keep
     the old content of the page. The page is neither on the freelist nor a b-tree page, so no
     region covers it. ``secure_delete`` zeroes freed pages, so this needs the default (off).
   * Reserved bytes at the end of each page, fragments of fewer than 4 bytes, bytes after the last
     complete page, and the ``-wal`` file (``view: current`` folds it into the copy first).

   In a table with an index on a text column, 400 rows and 100 deleted (10 runs, 1000 deleted
   values), every deleted value was in the free space with the default settings, and none was
   anywhere in the file with ``secure_delete`` on. After ``ANALYZE`` with ``secure_delete`` on,
   55 of the 1000 were still in ``sqlite_stat4`` and none in the free space.

   To assert that a value is **gone from the whole file**, search all of it, in the encodings
   the database uses, and the write-ahead log if there is one:

   .. code-block:: yaml

      tests:
        - name: value_not_in_main_file
          function: text.occurrence_count
          parameter:
            dst: /data/app/state.db
            content: deleted-note-title
            encoding: [utf-8, utf-16-le]
            expected_count: 0
        - name: value_not_in_wal
          function: text.occurrence_count
          parameter:
            dst: /data/app/state.db-wal   # an error when there is no -wal
            content: deleted-note-title
            expected_count: 0

   :doc:`../binary/pattern_count` does the same for a pattern type of ``bytes``, ``hex`` or ``regex``.
   Live rows are counted too, and each indexed value is in the file at least twice while the row
   lives (table cell and index entry), so "deleted but still in the file" is
   :doc:`row_count` ``expected_count: 0`` together with a whole-file count of at least 1.

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
     - **Required.** Path to the SQLite database. A glob must match exactly one file. It and its ``-wal`` / ``-journal`` are copied to a temporary directory; only the copy is read.
   * - ``pattern``
     - string
     - **Required.** What to count; must not be empty. Its meaning depends on ``pattern_type``.
   * - ``pattern_type``
     - string
     - **Optional.** ``text`` (default): ``pattern`` encoded in ``encoding``. ``bytes``: ASCII characters stand for their byte, Python escapes (``\x00``) are decoded. ``hex``: hex digits, whitespace allowed. ``regex``: an ASCII regular expression over the raw bytes (empty matches do not count). As in :doc:`../binary/pattern_count`.
   * - ``encoding``
     - string
     - **Optional.** Encoding for ``text``: ``utf-8`` (default), ``utf-16-le`` or ``utf-16-be`` for databases with a UTF-16 text encoding.
   * - ``region``
     - string
     - **Optional.** Which free space is searched: ``all`` (default), ``freelist``, ``freeblocks`` or ``unallocated``.
   * - ``view``
     - string
     - **Optional.** ``main_file`` (default): the main database file as it is, ``<dst>-wal`` left out. ``current``: the copy after ``PRAGMA wal_checkpoint(TRUNCATE)``, i.e. with the write-ahead log folded in as SQLite would on a checkpoint (a hot ``-journal`` is rolled back first).
   * - ``expected_count``
     - integer
     - **Optional.** Non-negative number to compare the occurrences with. Default: ``1``. ``0`` asserts absence.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Use ``greater_equal`` with ``expected_count: 1`` for "at least once".

Usage Example
-------------

.. code-block:: yaml

   tests:
     # deleted from the table, still recoverable from the file
     - name: note_not_queryable
       function: sqlite.row_count
       parameter:
         dst: /data/app/state.db
         query: "SELECT id FROM notes WHERE title = 'deleted-note-title'"
         expected_count: 0
     - name: note_recoverable
       function: sqlite.free_space_pattern_count
       parameter:
         dst: /data/app/state.db
         pattern: deleted-note-title
         expected_count: 1
         comparison_type: greater_equal

     # a large deleted value whose overflow pages were freed
     - name: attachment_on_freelist
       function: sqlite.free_space_pattern_count
       parameter:
         dst: /data/app/state.db
         pattern: '[0-9a-f]{32}'
         pattern_type: regex
         region: freelist
         expected_count: 1
         comparison_type: greater_equal

     # the application erases deleted records (secure delete)
     - name: nothing_left_after_checkpoint
       function: sqlite.free_space_pattern_count
       parameter:
         dst: /data/app/state.db
         pattern: deleted-note-title
         view: current
         expected_count: 0

Return Values
-------------

Every result after the file was parsed reports the count (``<n> occurrence(s) of <type>
'<pattern>' in <k> free region(s) (<bytes> bytes; region <region>)``), the comparison, the
matching regions (``matches: page 5 freelist [16384, 20480): 2; ...`` with absolute file
offsets, the first 20), the size of each kind of free space, the view and one
``read snapshot: <file> sha256=<hash>`` per copied file (for ``current`` also the hash of the
checkpointed copy that was parsed).

**Success**
  The count comparison holds.

**Failure**
  The free space was located and the count comparison does not hold.

**Error**
  The database does not exist or a glob matches no file or several; the file is not an SQLite
  database or its header is impossible (page size, reserved bytes); a broken freelist (a page
  number outside the file, a page listed twice, a trunk listing more leaves than fit, a page
  count that differs from the header's) or freeblock chain (off the page, not in ascending
  order); SQLite cannot checkpoint the copy (``view: current``); an empty or invalid pattern,
  an unknown ``pattern_type``, ``encoding``, ``region`` or ``view``; a negative
  ``expected_count`` or an unknown ``comparison_type``.

See also
--------

- :doc:`row_count` shows that the record is gone from the live data.
- :doc:`../binary/pattern_count` counts a pattern in any byte range of a file, live rows included.
- :doc:`wal_frame_count` and ``view: commit:N`` in :doc:`query_result` look at older versions of
  pages in the write-ahead log.
