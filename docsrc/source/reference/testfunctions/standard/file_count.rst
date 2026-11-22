file_count
==========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``file_count``

**Tests the number of files (or directories) matching a path or glob.**

Counts the paths matching ``dst`` that are of ``kind`` and passes when the count satisfies
``comparison_type`` against ``expected_count``. It is an existence test: a glob without a match,
or a missing plain path, counts 0 and is not an error, so ``expected_count: 0`` asserts that a
whole group of files is absent. For one file use ``standard.file_exists``.

In host test mode the guest lists the matching paths and their kinds; no file is pulled, so a
copy pulled by an earlier test is never counted.

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
     - **Required.** Path or glob (Python ``glob``, not recursive: ``**`` acts like ``*``; ``*`` skips dotfiles). ``archive.zip!/logs/*.log`` counts the matching file members of an archive; the archive itself must exist and be readable.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number of paths.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.
   * - ``kind``
     - string
     - **Optional.** ``file``: regular files (also through a symlink); ``dir``: directories; ``any``: every existing path, broken symlinks included. Archives have file members only, so ``dir`` with an archive path is an error. Default: ``file``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: three_exports_written
       function: standard.file_count
       parameter:
         dst: /home/user/Documents/export-*.csv
         expected_count: 3

     - name: temp_files_removed
       function: standard.file_count
       parameter:
         dst: /home/user/.cache/app/*.tmp
         expected_count: 0

     - name: logs_in_backup
       function: standard.file_count
       parameter:
         dst: /home/user/backup.zip!/logs/*.log
         expected_count: 1
         comparison_type: greater_equal

Common Use Cases
----------------

**How many files were written**
  Exactly three exports, at least one rotated log, one file inside an archive.

**A group of files is gone**
  ``expected_count: 0`` on a glob: cleared cache or temp files, a deleted folder content.

See Also
--------

* :doc:`file_exists` — one file (or a glob) exists.
* :doc:`file_does_not_exist` — one file (or a glob) is absent.
* :doc:`dir_content` — the exact names in a directory.
* :doc:`file_size` — the size of one file.
* :doc:`/guide/absence` — checking that something is absent.

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The paths were examined and the count comparison does not hold (also when nothing matches and
  ``expected_count`` is above 0).

**Error**
  An empty ``dst`` or one with an unresolved ``{{ placeholder }}``, a negative or non-integer
  ``expected_count``, an unknown ``comparison_type`` or ``kind``,
  ``kind: dir`` with an archive path, an archive that is missing or cannot be read (also an
  archive glob that matches a link member), or, in host mode, a failed guest listing.
