value_count
===========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: INI Configuration
:Function Name: ``value_count``

**Tests the number of occurrences of an INI key, optionally only those with a matching value (0 = absent).**

Counts the ``key`` lines in every occurrence of ``section`` (only those whose value matches ``expected_value``,
if given) and compares the count with ``expected_count``. ``expected_count: 0`` asserts the key, or the key with
that value, is absent; a missing or unreadable file is still an error, never a pass.

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
     - **Required.** Path to the INI file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``section``
     - string
     - **Required.** Section name without brackets; ``''`` = keys before the first header.
   * - ``key``
     - string
     - **Required.** Key name.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``expected_value``
     - string/int/float/bool
     - **Optional.** Only count occurrences whose value matches (same rules as ``value_matches``). Default: count every occurrence.
   * - ``regex_match``
     - boolean
     - **Optional.** Search ``expected_value`` as a regex. Default: ``false``.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.
   * - ``case_sensitive``
     - boolean
     - **Optional.** ``false`` compares section and key names case-insensitively. Default: ``true``.
   * - ``encoding``
     - string
     - **Optional.** Text encoding. Default: auto (BOM, BOM-less UTF-16, else UTF-8).

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: ini_entry_removed
       function: ini.value_count
       parameter:
         dst: /home/user/.config/app/settings.ini
         section: RecentFiles
         key: file
         expected_value: /home/user/Documents/report.txt
         expected_count: 0

     - name: ini_list_has_entries
       function: ini.value_count
       parameter:
         dst: /home/user/.config/app/settings.ini
         section: RecentFiles
         key: file
         expected_count: 2
         comparison_type: greater_equal

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The file was read and the count comparison does not hold.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or
  decoded, the encoding is unknown, a negative or non-integer ``expected_count``, an unknown
  ``comparison_type``, or an invalid regex.
