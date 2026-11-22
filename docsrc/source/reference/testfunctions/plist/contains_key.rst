contains_key
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Property List Data
:Function Name: ``contains_key``

**Tests if a plist file contains the specified key path.**

Passes when the key path selects at least one value. To check the value use :doc:`value_matches`; to check that a key is absent use :doc:`value_count` with ``expected_count: 0`` (or ``expect_to_fail: true`` here — a missing file stays an error).

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

Key Paths and Values
--------------------

Property lists are dictionaries, arrays and scalar values. Keys in preference files often contain dots (``com.example.lastVersion``); address them with quotes in brackets: ``['com.example.lastVersion']``, also mid-path (``recent['com.example.doc'].name``).

``<date>`` values become ISO 8601 strings without zone (plist dates are UTC): ``2024-01-15T10:30:00``. ``<data>`` values become lowercase hex strings (``0a1bff``). ``<integer>``, ``<real>`` and ``<true/>``/``<false/>`` stay numbers and booleans.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: plist_has_key
       function: plist.contains_key
       parameter:
         dst: /home/user/Library/Preferences/com.example.app.plist
         key_path: "['com.example.lastVersion']"

Return Values
-------------

**Success**
  The key path selects at least one value.

**Failure**
  The file was read and the key path selects nothing.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read,
  the content is not a valid plist (malformed XML, corrupt binary plist, unknown element, unparsable value).
