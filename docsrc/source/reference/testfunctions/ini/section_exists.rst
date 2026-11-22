section_exists
==============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: INI Configuration
:Function Name: ``section_exists``

**Tests if an INI file contains a section.**

Passes when the file has at least one ``[section]`` header. For an absent section use ``expect_to_fail: true``
(a missing or unreadable file stays an error).

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
     - **Required.** Section name without brackets, compared after stripping.
   * - ``case_sensitive``
     - boolean
     - **Optional.** ``false`` compares section names case-insensitively. Default: ``true``.
   * - ``encoding``
     - string
     - **Optional.** Text encoding. Default: auto (BOM, BOM-less UTF-16, else UTF-8). An unknown name is an error.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: ini_section_written
       function: ini.section_exists
       parameter:
         dst: /home/user/.config/app/settings.ini
         section: General

Common Use Cases
----------------

**A group of settings was created**
  A section for a new account, profile or recent file list.

See Also
--------

* :doc:`contains_key` — a key in the section.
* :doc:`value_count` — how often a key occurs.

Return Values
-------------

**Success**
  A header with that name exists.

**Failure**
  The file was read and has no such header (the details list the sections found).

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or
  decoded, or the encoding is unknown.
