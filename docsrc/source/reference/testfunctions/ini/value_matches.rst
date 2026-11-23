value_matches
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: INI Configuration
:Function Name: ``value_matches``

**Tests if an INI value equals or matches an expected value (regex and placeholders supported).**

Compares the raw value text of ``key`` in ``section``. With duplicate keys or a section that appears more than
once, one matching occurrence is enough (``wildcard_mode: all``: every occurrence must match). A missing key fails.

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
     - **Required.** Section name without brackets; ``''`` = keys before the first header.
   * - ``key``
     - string
     - **Required.** Key name; the first ``=`` on a line splits key and value.
   * - ``expected_value``
     - string/int/float/bool
     - **Required.** Compared with the stripped raw value (quotes and inline comments kept). A YAML number or boolean is compared as its text (``8080``, ``true``/``false``). A ``!re``/``!timestamp`` tag or ``{{placeholder}}`` is matched by type.
   * - ``regex_match``
     - boolean
     - **Optional.** Search ``expected_value`` as a regex (``re.search``, unanchored). Default: ``false``.
   * - ``case_sensitive``
     - boolean
     - **Optional.** ``false`` compares section and key names case-insensitively; values are always compared as given. Default: ``true``.
   * - ``encoding``
     - string
     - **Optional.** Text encoding. Default: auto (BOM, BOM-less UTF-16, else UTF-8).
   * - ``wildcard_mode``
     - string
     - **Optional.** With several occurrences (duplicate keys or sections): ``any``: one must match; ``all``: every one must match. Other values are an error. Default: ``any``.
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

With ``comparison_type``, ``value_type``, ``tolerance`` or a time parameter the value is compared as a number or a point in time instead of by equality: greater/less (earlier/later), or equal within a tolerance. A value that is no number or timestamp is an ERROR (the test looked at the wrong field), as is a regex or placeholder ``expected_value``. See :ref:`ordered-comparison`.

.. code-block:: yaml

   tests:
     - name: ordered_value
       function: ini.value_matches
       parameter:
         dst: /home/user/.config/app/settings.ini
         section: General
         key: port
         expected_value: 1024
         comparison_type: greater

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: ini_language
       function: ini.value_matches
       parameter:
         dst: /home/user/.config/app/settings.ini
         section: General
         key: language
         expected_value: de_DE

     - name: ini_recent_file
       function: ini.value_matches
       parameter:
         dst: /home/user/backup.zip!/settings.ini
         section: RecentFiles
         key: file
         expected_value: 'report\.txt$'
         regex_match: true

     - name: ini_all_recent_files_in_documents
       function: ini.value_matches
       parameter:
         dst: /home/user/.config/app/settings.ini
         section: RecentFiles
         key: file
         expected_value: '^/home/user/Documents/'
         regex_match: true
         wildcard_mode: all

Return Values
-------------

**Success**
  The value matches (with several occurrences: one of them, or every one with ``wildcard_mode: all``).

**Failure**
  The file was read and the key is missing, no occurrence matches, or (``wildcard_mode: all``) one
  does not match; the details list the non-matching values with their line numbers.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or
  decoded, the encoding is unknown, the regex is invalid, or ``wildcard_mode`` is not ``any``/``all``.
