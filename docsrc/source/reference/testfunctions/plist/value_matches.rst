value_matches
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Property List Data
:Function Name: ``value_matches``

**Tests if the plist value at a key path matches the expected value.**

Passes when the value at the key path equals (or matches) ``expected_value``. If the path selects several values (a wildcard, or an array value, whose elements are then compared one by one) ``wildcard_mode`` decides.

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
   * - ``expected_value``
     - string/int/float/bool/null
     - **Required.** Compared with ``==`` (type-sensitive: ``5`` is not ``"5"``). A ``!re`` tag (``re.match``) or a ``{{placeholder}}`` compares ``str(value)``.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat a string ``expected_value`` as a regex searched (``re.search``) in ``str(value)``. Default: ``false``.
   * - ``wildcard_mode``
     - string
     - **Optional.** ``any``: one selected value must match; ``all``: every value must match. Default: ``any``.

Key Paths and Values
--------------------

Property lists are dictionaries, arrays and scalar values. Keys in preference files often contain dots (``com.example.lastVersion``); address them with quotes in brackets: ``['com.example.lastVersion']``, also mid-path (``recent['com.example.doc'].name``).

``<date>`` values become ISO 8601 strings without zone (plist dates are UTC): ``2024-01-15T10:30:00``. ``<data>`` values become lowercase hex strings (``0a1bff``). ``<integer>``, ``<real>`` and ``<true/>``/``<false/>`` stay numbers and booleans.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: plist_value
       function: plist.value_matches
       parameter:
         dst: /home/user/Library/Preferences/com.example.app.plist
         key_path: "['com.example.lastLaunch']"
         expected_value: !re '^2024-01-15T'

     - name: plist_value_exact
       function: plist.value_matches
       parameter:
         dst: /home/user/Library/Preferences/com.example.app.plist
         key_path: "window.width"
         expected_value: 1280

Return Values
-------------

**Success**
  The value (``any``: one of the values, ``all``: every value) matches.

**Failure**
  The file was read and the key path selects nothing, or the value(s) do not match.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read,
  the content is not a valid plist (malformed XML, corrupt binary plist, unknown element, unparsable value), an invalid ``wildcard_mode``, or an invalid regex.
