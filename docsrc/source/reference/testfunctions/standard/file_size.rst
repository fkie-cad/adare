file_size
=========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``file_size``

**Tests the size of a file in bytes.**

Passes when the file size (``os.stat``) satisfies ``comparison_type`` against ``expected_size``: ``expected_size: 0`` asserts an empty file, ``comparison_type: greater`` with ``0`` a non-empty one. A missing file is an error, never a pass; for existence alone use ``standard.file_exists``.

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
     - **Required.** Path to the file. A glob must match exactly one file; ``archive.zip!/member`` gives the extracted member's size.
   * - ``expected_size``
     - integer
     - **Required.** Non-negative number of bytes.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: log_was_written
       function: standard.file_size
       parameter:
         dst: /home/user/data/app.log
         expected_size: 0
         comparison_type: greater

     - name: cache_was_emptied
       function: standard.file_size
       parameter:
         dst: /home/user/data/cache.bin
         expected_size: 0

Return Values
-------------

**Success**
  The size comparison holds.

**Failure**
  The file was examined and the size comparison does not hold.

**Error**
  The file does not exist or is a directory, a glob matches no file or more than one, the file
  cannot be examined, a negative or non-integer ``expected_size``, or an unknown ``comparison_type``.
