value_count
===========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: JSON Data
:Function Name: ``value_count``

**Tests how many JSON values exist at a key path, optionally only those matching a value (0 = absent).**

Passes when the number of values at the key path (only those matching ``expected_value``, if given) satisfies ``comparison_type`` against ``expected_count``. ``expected_count: 0`` asserts absence of a key or value; a missing or invalid file is still an error, never a pass. Without ``expected_value`` every selected value counts once, ``null`` included (``items`` counts 1, ``items[*]`` the elements); with it, a path that selects one array counts matching elements.

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
     - **Required.** Path to the JSON file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive, ``store.jsonlz4!`` reads LZ4-compressed JSON.
   * - ``key_path``
     - string
     - **Required.** Dot path from the root, e.g. ``a.b.c``. ``*`` expands all values of an object, ``name[*]`` all elements of array ``name``, ``name[0]`` / ``name[-1]`` one element; a leading ``[0]`` / ``[*]`` addresses a top-level array. ``['a.b']`` is a key that contains dots.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``expected_value``
     - string/int/float/bool
     - **Optional.** Only count values equal to this (type-sensitive, as in ``value_matches``; ``!re`` / ``!timestamp`` tags work; an invalid regex or unknown placeholder is an ERROR). Default: count every value.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat a string ``expected_value`` as a Python regex searched (``re.search``) in ``str(value)``. Default: ``false``.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.
   * - ``encoding``
     - string
     - **Optional.** ``null`` (default) detects UTF-8/16/32 with or without BOM; a name (``latin-1``) decodes BOM-less files with it. An unknown name is an ERROR.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: json_entry_removed
       function: json.value_count
       parameter:
         dst: /home/user/data/settings.json
         key_path: "groups[*].items[*].title"
         expected_value: Example Entry
         expected_count: 0

     - name: json_compressed_store_has_three_tags
       function: json.value_count
       parameter:
         dst: /home/user/data/store.jsonlz4!
         key_path: "[*].tag"
         expected_count: 3

Common Use Cases
----------------

**A key or value is absent**
  ``expected_count: 0``: the key path selects nothing, or no value matches ``expected_value``.

**How many entries a list holds**
  Exactly three bookmarks, at least one entry with a URL.

See Also
--------

* :doc:`value_matches` — the value at a key path.
* :doc:`contains_key` — only that the key exists.
* :doc:`/reference/testfunctions/jsonl/line_count` — records in a JSON Lines file.
* :doc:`/guide/absence` — checking that something is absent.

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The file was read and the count comparison does not hold.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or
  is not valid JSON, a negative or non-integer ``expected_count``, an unknown ``comparison_type``,
  or an invalid regex.
