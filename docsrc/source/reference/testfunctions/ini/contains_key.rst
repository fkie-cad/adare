contains_key
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: INI Configuration
:Function Name: ``contains_key``

**Tests if an INI file contains a key in a section.**

Passes when the section has a ``key = ...`` line; an empty value counts. Lines without ``=`` are not keys.
For an absent key use ``value_count`` with ``expected_count: 0``.

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
     - **Required.** Section name without brackets; ``''`` = keys before the first header. Duplicate sections are searched together.
   * - ``key``
     - string
     - **Required.** Key name, compared after stripping.
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
     - name: ini_key_written
       function: ini.contains_key
       parameter:
         dst: /home/user/.config/app/settings.ini
         section: General
         key: last_opened

Common Use Cases
----------------

**A setting was written**
  The key exists after the action, whatever its value.

See Also
--------

* :doc:`value_matches` — the value of the key.
* :doc:`value_count` — how often the key occurs (``0`` for absence).
* :doc:`section_exists` — only the section.

Return Values
-------------

**Success**
  The key exists in the section (the details show its first value).

**Failure**
  The file was read and the section has no such key.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or
  decoded, or the encoding is unknown.
