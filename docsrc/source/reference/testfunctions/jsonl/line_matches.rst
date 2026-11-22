line_matches
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: JSON Lines Data
:Function Name: ``line_matches``

**Tests if one line (or every line) of a JSONL file meets all given conditions.**

Parses each line of ``dst`` as JSON and checks every entry of ``conditions`` (``key_path: expected value``) against it. With ``wildcard_mode: any`` the test passes when at least one line meets all conditions; with ``all`` every valid line must meet them. To count matching lines use ``jsonl.line_count``.

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
     - **Required.** Path to the JSONL file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive. A 0-byte file fails.
   * - ``conditions``
     - dict
     - **Required.** Mapping ``key_path -> expected value``; a line matches when every condition holds. If a path yields several values (wildcard or JSON array), one matching element suffices. A missing key fails the line.
   * - ``wildcard_mode``
     - string
     - **Optional.** ``any`` (one line must match) or ``all`` (every valid line must match; a file without valid lines fails). Default: ``any``.
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
     - name: alice_logged_in
       function: jsonl.line_matches
       parameter:
         dst: /home/user/data/events.jsonl
         conditions:
           event: login
           user.name: alice

     - name: every_event_in_the_session
       function: jsonl.line_matches
       parameter:
         dst: /home/user/data/events.jsonl
         wildcard_mode: all
         conditions:
           time: !timestamp {after: '{{session_start}}', before: '{{session_end}}', precision: 1}

Common Use Cases
----------------

**Event logs**
  A line with ``event: login`` and ``user.name: alice`` proves the login was recorded as one event, not as two unrelated fields in different lines.

**Uniform exports**
  ``wildcard_mode: all`` checks that every record of an export has a field or a value format.

See Also
--------

* :doc:`value_in_any_line` — one field in any line.
* :doc:`line_count` — how many lines meet the conditions (``0`` for absence).
* :doc:`/reference/testfunctions/json/value_matches` — a value in a single JSON document.

Return Values
-------------

**Success**
  One line (``any``) or every valid line (``all``) meets all conditions.

**Failure**
  The file was read and no line (``any``) or not every line (``all``) meets the conditions, the file is empty, or (``all``) it has no valid JSON line.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or decoded, the encoding is unknown, a malformed line with ``skip_malformed: false``, or an invalid ``wildcard_mode``.
