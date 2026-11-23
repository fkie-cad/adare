lines_in_order
==============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: JSON Lines Data
:Function Name: ``lines_in_order``

**Tests that JSONL records meeting each of several condition sets occur in the given order.**

Parses each line of ``dst`` as JSON and looks for the ``conditions`` one after the other: each condition set must be met by a record after the record that met the previous one. Records in between are ignored. A record meets a condition set exactly as in ``jsonl.line_matches``. Each condition set takes the earliest such record, so two condition sets never match the same record, and when this fails no other choice of records would pass either. For plain text lines use ``text.lines_in_order``.

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
     - **Required.** Path to the JSONL file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``conditions``
     - list
     - **Required.** Non-empty list, in the expected order, of mappings ``key_path -> expected value``; a record meets one when every condition holds. If a path yields several values (wildcard or JSON array), one matching element suffices. A missing key fails the record.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat string expected values as regexes searched (``re.search``) in ``str(value)``; the value ``"*"`` then means "key exists". Without it, values are compared with type-sensitive ``==``; ``!re`` and ``!timestamp`` tags always work. Default: ``false``.
   * - ``skip_malformed``
     - boolean
     - **Optional.** ``true`` ignores lines that are not valid JSON; ``false`` makes the first malformed line an error. Default: ``true``.
   * - ``encoding``
     - string
     - **Optional.** Default ``None``: a BOM (UTF-8/16/32) or BOM-less UTF-16 is detected, else UTF-8. A name (``cp1252``) reads BOM-less files with it.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: login_then_delete_then_logout
       function: jsonl.lines_in_order
       parameter:
         dst: /var/log/app/events.jsonl
         conditions:
           - {event: login, user.name: alice}
           - {event: file_deleted, path: !re '.*report\.txt$'}
           - {event: logout}

Return Values
-------------

**Success**
  Every condition set was met by a record after the previous one. Details list the matched line
  numbers (counted from 1, blank lines included).

**Failure**
  The file was read and a condition set is met by no record after the record of the one before
  it. The first such condition set is named; if it is met only earlier, its earlier line numbers
  are listed ("out of order"). The records matched so far follow.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or
  decoded, an unknown encoding, a malformed line with ``skip_malformed: false``, an empty
  ``conditions`` list or an entry that is not a non-empty mapping, or an invalid regex.
