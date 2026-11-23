value_matches
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: YAML Data
:Function Name: ``value_matches``

**Tests if the YAML value at a key path matches the expected value.**

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
     - **Required.** Path to the YAML file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
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
     - **Optional.** ``equals`` (default), ``not_equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Anything but ``equals``, or any of the parameters below, compares the value with ``expected_value`` as a number or timestamp (see :ref:`ordered-comparison`); a ``!re`` tag or ``regex_match`` is then an ERROR, a lone ``{{ name }}`` is the saved variable's value.
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
   * - ``value_decode``
     - list / string
     - **Optional.** Decode the value read from the file before comparing: one step or a list applied in order: ``url``, ``base64``, ``hex``, ``utf16``, ``json`` (see "Decoding a stored value" under :ref:`ordered-comparison`). A value a step cannot decode, or an unknown step, is an ERROR.
   * - ``decoded_key_path``
     - string
     - **Optional.** With ``json`` in ``value_decode``: key path into the decoded value; it must select one value. Required with ``json``, an ERROR without it.

Numbers and Timestamps
----------------------

With ``comparison_type``, ``value_type``, ``tolerance`` or a time parameter the value is compared as a number or a point in time instead of by equality: greater/less (earlier/later), or equal within a tolerance. To compare two values of one file use :doc:`values_compare`. A value that is no number or timestamp is an ERROR (the test looked at the wrong field), as is a regex ``expected_value``; a lone ``{{ name }}`` placeholder compares with the saved variable. See :ref:`ordered-comparison`.

.. code-block:: yaml

   tests:
     - name: ordered_value
       function: yaml.value_matches
       parameter:
         dst: /home/user/.config/app/state.yaml
         key_path: session.closed
         expected_value: "2026-03-01T10:00:00Z"
         comparison_type: greater

Key Paths and Values
--------------------

A file with one document is addressed from its root. A file with several documents (separated by ``---``) is a top-level list with one entry per document: ``[0].kind`` is ``kind`` in the first document, ``[*].kind`` in all of them. An empty file has no keys. Files are read as UTF-8, or UTF-16 with a byte order mark.

Values keep their YAML 1.1 types: ``5`` is an integer, ``true``/``yes``/``on`` and ``false``/``no``/``off`` are booleans, ``null`` is ``None``. Dates and timestamps become ISO 8601 strings: ``2024-01-15``, ``2024-01-15T10:30:00``, and a ``Z`` zone becomes ``+00:00``. ``!!binary`` values become lowercase hex strings.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: yaml_value
       function: yaml.value_matches
       parameter:
         dst: /home/user/.config/app/config.yaml
         key_path: "servers[*].port"
         expected_value: 8080

     - name: yaml_value_exact
       function: yaml.value_matches
       parameter:
         dst: /home/user/.config/app/config.yaml
         key_path: "[1].name"
         expected_value: second

Common Use Cases
----------------

**A setting has a value**
  A setting changed in the GUI is stored in a YAML configuration.

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
  the content is not valid YAML (syntax error, unknown or unsafe tag, impossible date, undecodable bytes), an invalid ``wildcard_mode``, or an invalid regex.
