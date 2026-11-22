value_count
===========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Property List Data
:Function Name: ``value_count``

**Tests how many plist values exist at a key path, optionally only those matching a value (0 = absent).**

Passes when the number of values at the key path (only those matching ``expected_value``, if given) satisfies ``comparison_type`` against ``expected_count``. ``expected_count: 0`` asserts absence of a key or value; a missing or invalid file is still an error, never a pass. Without ``expected_value`` every selected value counts once (``items`` counts 1, ``items[*]`` the elements); with it, a path that selects one array counts matching elements.

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
     - **Required.** Path to the property list. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``key_path``
     - string
     - **Required.** Dot path from the root, e.g. ``a.b.c``. ``*`` expands all values of a dictionary, ``name[*]`` all elements of array ``name``, ``name[0]`` / ``name[-1]`` one element; a leading ``[0]`` / ``[*]`` addresses a top-level array. ``['a.b']`` is a key that contains dots.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``expected_value``
     - string/int/float/bool/null
     - **Optional.** Only count values equal to this (normalised as in ``value_matches``). Default: count every value.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat a string ``expected_value`` as a regex searched in ``str(value)``. Default: ``false``.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.

Key Paths and Values
--------------------

Property lists are dictionaries, arrays and scalar values. Keys in preference files often contain dots (``com.example.lastVersion``); address them with quotes in brackets: ``['com.example.lastVersion']``, also mid-path (``recent['com.example.doc'].name``).

``<date>`` values become ISO 8601 strings without zone (plist dates are UTC): ``2024-01-15T10:30:00``. ``<data>`` values become lowercase hex strings (``0a1bff``). ``<integer>``, ``<real>`` and ``<true/>``/``<false/>`` stay numbers and booleans.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: plist_entry_removed
       function: plist.value_count
       parameter:
         dst: /home/user/Library/Preferences/com.example.app.plist
         key_path: "['com.example.recentDocuments'][*]"
         expected_count: 0

     - name: plist_at_least_two
       function: plist.value_count
       parameter:
         dst: /home/user/Library/Preferences/com.example.app.plist
         key_path: "['com.example.recentDocuments'][*]"
         expected_count: 2
         comparison_type: greater_equal

Common Use Cases
----------------

**A key or value is absent**
  ``expected_count: 0``.

**How many entries a list holds**
  Recent items, accounts or bookmarks.

See Also
--------

* :doc:`value_matches` — the value at a key path.
* :doc:`contains_key` — only that the key exists.
* :doc:`/reference/testfunctions/json/value_count` — the same for JSON files.

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The file was read and the count comparison does not hold.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read,
  the content is not a valid plist (malformed XML, corrupt binary plist, unknown element, unparsable value), a negative or non-integer ``expected_count``, an unknown ``comparison_type``, or an invalid regex.
