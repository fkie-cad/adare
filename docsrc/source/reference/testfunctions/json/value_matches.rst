value_matches
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: JSON Data
:Function Name: ``value_matches``

**Tests if JSON value at key path matches expected value using placeholders (supports wildcards [*] and * with any/all modes).**

This test function validates that a JSON value at a specified key path matches an expected value. It supports advanced features including wildcard matching, regular expressions, and placeholder comparison for flexible value validation.

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
     - **Required.** The JSON file path to check. Supports glob patterns for dynamic path resolution.
   * - ``key_path``
     - string
     - **Required.** The key path using dot notation. Supports wildcards: ``[*]`` for arrays, ``*`` for all object keys.
   * - ``expected_value``
     - string/int/float/bool/null
     - **Required.** The expected value, compared with type-sensitive ``==`` (``5`` is not ``"5"``; a JSON ``null`` needs ``expected_value: null``). A ``!re``/``!timestamp`` placeholder compares the value's string form; an invalid regex or unknown placeholder is an ERROR.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat a string ``expected_value`` as a Python regex searched (``re.search``, unanchored) in the value's string form. Default: ``false``.
   * - ``wildcard_mode``
     - string
     - **Optional.** Mode for wildcard matching: ``any`` (at least one match) or ``all`` (all must match). Default: ``any``.
   * - ``encoding``
     - string
     - **Optional.** ``null`` (default) detects UTF-8/16/32 with or without BOM; a name (``latin-1``) decodes BOM-less files with it. An unknown name is an ERROR.
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
     - **Optional.** With ``json`` in ``value_decode``: key path into the decoded value; it must select one value: none is FAILED (the value decoded, the key is not in it), several are an ERROR. Required with ``json``, an ERROR without it.

Numbers and Timestamps
----------------------

With ``comparison_type``, ``value_type``, ``tolerance`` or a time parameter the value is compared as a number or a point in time instead of by equality: greater/less (earlier/later), or equal within a tolerance. To compare two values of one file use :doc:`values_compare`. A value that is no number or timestamp is an ERROR (the test looked at the wrong field), as is a regex ``expected_value``; a lone ``{{ name }}`` placeholder compares with the saved variable. See :ref:`ordered-comparison`.

.. code-block:: yaml

   tests:
     - name: ordered_value
       function: json.value_matches
       parameter:
         dst: /home/user/data/settings.json
         key_path: window.width
         expected_value: 800
         comparison_type: greater_equal

Usage Example
-------------

Basic Value Matching
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_string
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'app_name'
         expected_value: 'TestApplication'
       description: "Test json_value_matches with string value"

Integer and Boolean Values
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_integer
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'database.port'
         expected_value: 5432
       description: "Test json_value_matches with integer value"

     - name: test_json_value_matches_boolean_true
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'debug_mode'
         expected_value: true
       description: "Test json_value_matches with boolean true"

Wildcard Array Matching
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_array_wildcard_any
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/users.json'
         key_path: 'users[*].active'
         expected_value: true
         wildcard_mode: 'any'
       description: "Test json_value_matches with array wildcard [*] in any mode"

Object Wildcard Matching
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_object_wildcard_any
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'database.*'
         expected_value: 'localhost'
         wildcard_mode: 'any'
       description: "Test json_value_matches with object wildcard * in any mode"

Regex Matching
~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_regex
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'version'
         expected_value: '^\d+\.\d+\.\d+$'
         regex_match: true
       description: "Test json_value_matches with regex pattern"

Advanced Regex with Wildcard
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_wildcard_email_regex
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/users.json'
         key_path: 'users[*].email'
         expected_value: !re '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
         wildcard_mode: 'any'
       description: "Test json_value_matches with wildcard and direct email regex"

Common Use Cases
----------------

**Configuration Validation**
  Validate specific configuration values in JSON files

**API Response Testing**
  Verify API response values match expected results

**Data Quality Assurance**
  Ensure JSON data values conform to expected formats

**Wildcard Data Validation**
  Validate multiple array elements or object properties at once

**Pattern Matching**
  Use regex to validate string formats like emails, URLs, or IDs

Wildcard Behavior
-----------------

**Array Wildcards (``[*]``)**
  - ``users[*].name`` matches all user names in the users array
  - Use with ``wildcard_mode: "any"`` to require at least one match
  - Use with ``wildcard_mode: "all"`` to require all elements match

**Object Wildcards (``*``)**
  - ``config.*.enabled`` matches the ``enabled`` field in all config objects
  - Useful for validating properties across dynamic object keys

Return Values
-------------

**Success**
  Returns success when the value matches the expected criteria

**Failure**
  Returns failure when:

  - The key path does not exist
  - The value doesn't match the expected value
  - Wildcard mode requirements are not met (e.g., "all" mode with some non-matches)
  - Regex pattern doesn't match

**Execution Error**
  Returns execution error when:

  - The file does not exist, or a glob matches no file or more than one
  - Invalid JSON syntax
  - Invalid regex pattern provided
  - Permission denied accessing the file
  - System I/O errors occur

Example Results
---------------

.. code-block:: yaml

   # Success case - exact match
   result: success
   message: "value matches expected: active"

   # Success case - wildcard any mode
   result: success
   details:
     - 'wildcard path "users[*].status" matched 3/5 values (mode: any)'
     - "matching values: element[0]: active, element[2]: active, element[4]: active"

   # Success case - wildcard all mode
   result: success
   details:
     - 'wildcard path "servers.*.enabled" matched all 4 values (mode: all)'
     - 'all values equal: "true"'

   # Failure case - value mismatch
   result: failed
   details:
     - 'expected "active", got "inactive"'

   # Failure case - wildcard all mode
   result: failed
   details:
     - 'wildcard path "users[*].status" matched 3/5 values (mode: all)'
     - 'expected: "active"'
     - "non-matching values: element[1]: inactive, element[3]: pending"

   # Execution error case
   result: execution_error
   error: "Invalid regex pattern: [unclosed - re.error: unterminated character set at position 0"