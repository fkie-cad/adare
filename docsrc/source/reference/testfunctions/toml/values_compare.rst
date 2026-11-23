values_compare
==============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: TOML Data
:Function Name: ``values_compare``

**Compares two values of one TOML file as numbers or timestamps (earlier/later, within a tolerance, A = B + offset).**

Passes when ``value(key_path) <comparison_type> value(other_key_path) + offset`` holds in one TOML file. Both values are compared as numbers or as points in time; the time parameters say how to read timestamps (ISO 8601 and RFC 2822 by default, ``time_format`` for others, ``timestamp_epoch`` for numeric counts).

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
     - **Required.** Dot path of the first value (syntax as in :doc:`value_matches`). It must select exactly one value (a one-element array counts as its element).
   * - ``other_key_path``
     - string
     - **Required.** Dot path of the second value; same rules.
   * - ``comparison_type``
     - string
     - **Optional.** How the first value relates to the second: ``equals`` (default), ``not_equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal`` (``less`` = earlier for timestamps).
   * - ``value_type``
     - string
     - **Optional.** ``auto`` (default: numbers if both values are numbers, else timestamps), ``number`` or ``timestamp``.
   * - ``tolerance``
     - number
     - **Optional.** Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
   * - ``offset``
     - number
     - **Optional.** Added to the second value before comparing (seconds for timestamps, may be negative): ``first <comparison_type> second + offset``.
   * - ``time_format``
     - string
     - **Optional.** ``strptime`` format of text timestamps; default ISO 8601 or RFC 2822.
   * - ``timestamp_epoch``
     - int
     - **Optional.** Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
   * - ``timestamp_unit``
     - string
     - **Optional.** Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
   * - ``utc_offset``
     - string
     - **Optional.** Zone of timestamps without one (``+02:00``); default UTC.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: saved_not_more_than_opened
       function: toml.values_compare
       parameter:
         dst: /home/user/.config/app/state.toml
         key_path: counters.saved
         other_key_path: counters.opened
         comparison_type: less_equal

Common Use Cases
----------------

**A is earlier than B**
  A last-saved value later than the first-opened one, an end after a start (``comparison_type: less`` / ``greater``).

**A within a few seconds of B**
  Two timestamps written by one action (``tolerance: 5``).

**A = B + n**
  A counter or sequence number one above another (``offset: 1``), or a time a fixed interval after another (``offset`` in seconds).

See Also
--------

* :doc:`value_matches` — one value against a constant (also ``greater``/``less``). TOML local date-times (no zone) are read in ``utc_offset``.
* :ref:`ordered-comparison` — how numbers and timestamps are read.

Return Values
-------------

**Success**
  ``first <comparison_type> second + offset`` holds.

**Failure**
  The file was read and a side selects nothing, or the comparison does not hold.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or is invalid;
  a side selects several values; a value is no number or timestamp (or one is a number, the other a timestamp);
  invalid parameters (``comparison_type``, ``value_type``, ``tolerance`` with an order comparison, ``timestamp_epoch``, ...).
