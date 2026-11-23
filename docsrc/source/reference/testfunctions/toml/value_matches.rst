value_matches
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: TOML Data
:Function Name: ``value_matches``

**Tests if the TOML value at a key path matches the expected value.**

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
     - **Required.** Path to the TOML file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
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
   * - ``comparison_type``
     - string
     - **Optional.** ``equals`` (default), ``not_equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Anything but ``equals``, or any of the parameters below, compares the value with ``expected_value`` as a number or timestamp (see :ref:`ordered-comparison`); a ``!re`` tag, ``{{placeholder}}`` or ``regex_match`` is then an ERROR.
   * - ``value_type``
     - string
     - **Optional.** ``auto`` (default: numbers if both sides are numbers, else timestamps), ``number`` or ``timestamp``.
   * - ``tolerance``
     - number
     - **Optional.** Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
   * - ``time_format``
     - string
     - **Optional.** ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822.
   * - ``timestamp_epoch``
     - int
     - **Optional.** Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
   * - ``timestamp_unit``
     - string
     - **Optional.** Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
   * - ``utc_offset``
     - string
     - **Optional.** Zone of timestamps without one (``+02:00``); default UTC.

Numbers and Timestamps
----------------------

With ``comparison_type``, ``value_type``, ``tolerance`` or a time parameter the value is compared as a number or a point in time instead of by equality: greater/less (earlier/later), or equal within a tolerance. To compare two values of one file use :doc:`values_compare`. A value that is no number or timestamp is an ERROR (the test looked at the wrong field), as is a regex or placeholder ``expected_value``. See :ref:`ordered-comparison`.

.. code-block:: yaml

   tests:
     - name: ordered_value
       function: toml.value_matches
       parameter:
         dst: /home/user/.config/app/settings.toml
         key_path: cache.size
         expected_value: 1024
         comparison_type: less

Key Paths and Values
--------------------

Tables are dictionaries: ``[server]`` with ``port = 8080`` is ``server.port``. An array of tables (``[[items]]``) is an array: ``items[*].name`` selects every entry, ``items[0].name`` the first. A quoted table or key name with dots (``["app.window"]``) uses quotes in brackets: ``['app.window'].width``. Files are read as UTF-8.

Values keep their TOML types (integers, floats, booleans, strings). Dates and times become ISO 8601 strings: ``1979-05-27`` (local date), ``07:32:00`` (local time), ``1979-05-27T07:32:00`` (local date-time), ``1979-05-27T07:32:00-08:00`` (offset date-time; ``Z`` becomes ``+00:00``).

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: toml_value
       function: toml.value_matches
       parameter:
         dst: /home/user/.config/app/settings.toml
         key_path: "items[*].name"
         expected_value: 'Example Entry'

     - name: toml_value_exact
       function: toml.value_matches
       parameter:
         dst: /home/user/.config/app/settings.toml
         key_path: "updated"
         expected_value: '1979-05-27T07:32:00-08:00'

Common Use Cases
----------------

**A setting has a value**
  A setting changed in the GUI is stored in a TOML configuration.

See Also
--------

* :doc:`value_count` — how many values match (``0`` for absence).
* :doc:`contains_key` — only that the key exists.
* :doc:`/reference/testfunctions/json/value_matches` — the same for JSON files.

Return Values
-------------

**Success**
  The value (``any``: one of the values, ``all``: every value) matches.

**Failure**
  The file was read and the key path selects nothing, or the value(s) do not match.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read,
  the content is not valid TOML (syntax error, duplicate key, impossible date or time, bytes that are not UTF-8), an invalid ``wildcard_mode``, or an invalid regex.
