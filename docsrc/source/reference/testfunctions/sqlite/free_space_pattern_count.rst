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
  start of the cell content area;
* the **overflow tail**: a value too large for its b-tree cell continues on a chain of overflow
  pages (the number of the next page, then the value); the last page of the chain is rarely full,
  and the bytes after the value keep whatever the page held before. When SQLite frees a page and
  takes it again as an overflow page within one transaction, those bytes are the old rows, and
  ``secure_delete`` does not wipe them. Every in-use chain of a table leaf, index leaf or index
  interior cell is walked, and the region is ``[4 + bytes of the value on the page, usable size)``
  of its last page.

The reserved bytes at the end of each page and fragments of fewer than 4 bytes are not
searched. Regions never overlap, and occurrences are counted per region, so a match never spans
two regions. B-tree pages are recognised by their page type byte; pointer-map pages
(auto-vacuum databases) and the lock-byte page are skipped. A page that an overflow chain claims
is an overflow page whatever its first byte says.

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

   **Free space is not every byte of the file.** ``expected_count: 0`` on a free-space region
   proves only that the text is not in that free space. What the free-space regions do *not*
   cover, and ``region: whole_file`` does:

   * **``sqlite_stat4``** (after ``ANALYZE`` or ``PRAGMA optimize``) stores up to 24 sampled index
     keys per index as live rows. A deleted row whose key was sampled stays there, even with
     ``secure_delete``, until the next ANALYZE. A query reads it too:
     ``SELECT 1 FROM sqlite_stat4 WHERE instr(sample, CAST('text' AS BLOB)) > 0``.
   * **Full-text indexes** (FTS5: ``<name>_data``; FTS3/4: ``<name>_segments``) keep the terms of a
     deleted document in their segments until a merge or ``optimize``, again with ``secure_delete``.
     Terms are stored prefix-compressed, so only the part after the shared prefix may match.
   * **The write-ahead log and the rollback journal.** ``view: current`` folds the ``-wal`` into a
     copy, which can overwrite the very pages that hold old data; ``whole_file`` searches the
     ``-wal`` and the ``-journal`` as seized.
   * Reserved bytes at the end of each page, fragments of fewer than 4 bytes and bytes after the
     last complete page (only ``whole_file`` sees them).

   Two things that look like gaps are not: an **index** interior cell is a real index entry that
   deleting replaces, so the old cell is free space (a freeblock or unallocated space); and the
   **table interior pages** keep only the *rowids* of deleted rows as dividers (numbers, not text;
   ``secure_delete`` does not remove them).

   To assert that a value is **gone from the evidence**, use ``region: whole_file``: it counts
   the pattern in every byte of the database file and of its ``-wal`` and ``-journal`` (those that
   exist), each file on its own, so a match never spans two files. Live rows are counted too, and an
   indexed value is in the file at least twice while the row lives (table cell and index entry),
   so "deleted but still in the file" is :doc:`row_count` ``expected_count: 0`` together with a
   ``whole_file`` count of at least 1. Search each encoding the database uses (a second test with
   ``encoding: utf-16-le``). ``view`` has no meaning there and ``current`` is an error: the files
   are searched as seized, nothing is checkpointed or parsed (so even a damaged database can be
   searched).

   .. code-block:: yaml

      tests:
        - name: value_not_anywhere
          function: sqlite.free_space_pattern_count
          parameter:
            dst: /data/app/state.db
            pattern: deleted-note-title
            region: whole_file
            expected_count: 0
        - name: value_not_anywhere_utf16
          function: sqlite.free_space_pattern_count
          parameter:
            dst: /data/app/state.db
            pattern: deleted-note-title
            encoding: utf-16-le
            region: whole_file
            expected_count: 0

   In a table with an index on a text column, 400 rows and 100 deleted (10 runs, 1000 deleted
   values), every deleted value was in the free space with the default settings, and none was
   anywhere in the file with ``secure_delete`` on. After ``ANALYZE`` with ``secure_delete`` on,
   55 of the 1000 were still in ``sqlite_stat4`` and none in the free space; ``whole_file`` finds
   them.

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
     - **Optional.** Which free space is searched: ``all`` (default: ``freelist``, ``freeblocks``, ``unallocated`` and ``overflow_tail``), ``freelist``, ``freeblocks``, ``unallocated`` or ``overflow_tail``. Or ``whole_file``, which is not free space: every byte of the database file and of its ``-wal`` and ``-journal`` that exist (they are not required), each file counted on its own.
   * - ``view``
     - string
     - **Optional.** ``main_file`` (default): the main database file as it is, ``<dst>-wal`` left out. ``current``: the copy after ``PRAGMA wal_checkpoint(TRUNCATE)``, i.e. with the write-ahead log folded in as SQLite would on a checkpoint (a hot ``-journal`` is rolled back first). ``current`` is an error with ``region: whole_file``.
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

     # the delete left nothing, anywhere in the database file or its -wal / -journal
     - name: nothing_left_anywhere
       function: sqlite.free_space_pattern_count
       parameter:
         dst: /data/app/state.db
         pattern: deleted-note-title
         region: whole_file
         expected_count: 0

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

With ``region: whole_file`` the result reports the count over the whole evidence
(``<n> occurrence(s) of <type> '<pattern>' in the whole evidence (<k> file(s); region whole_file)``),
the comparison, one line per file that exists (``state.db-wal: 1 occurrence(s) in 4152 bytes,
sha256=<hash>``) and the ``read snapshot`` lines.

Every other result after the file was parsed reports the count (``<n> occurrence(s) of <type>
'<pattern>' in <k> free region(s) (<bytes> bytes; region <region>)``), the comparison, the
matching regions (``matches: page 5 freelist [16384, 20480): 2; ...`` with absolute file
offsets, the first 20), the size of each kind of free space (the overflow tail with its number of
overflow pages), the view and one
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
  count that differs from the header's), freeblock chain (off the page, not in ascending
  order) or overflow chain (a page out of range, on the freelist or claimed twice, a cycle, a
  chain that ends before or goes on after the size of the value; not for ``whole_file``); SQLite cannot checkpoint the copy (``view: current``); an empty or invalid pattern,
  an unknown ``pattern_type``, ``encoding``, ``region`` or ``view``, ``view: current`` with
  ``region: whole_file``; a negative
  ``expected_count`` or an unknown ``comparison_type``.

See also
--------

- :doc:`row_count` shows that the record is gone from the live data.
- :doc:`../binary/pattern_count` counts a pattern in any byte range of a file, live rows included
  (``region: whole_file`` does it for the database and its sidecars at once).
- :doc:`wal_frame_count` and ``view: commit:N`` in :doc:`query_result` look at older versions of
  pages in the write-ahead log.
