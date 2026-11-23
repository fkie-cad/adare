values_compare
==============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: XML Data
:Function Name: ``values_compare``

**Compares two values (element text or attribute) of one XML file as numbers or timestamps (earlier/later, within a tolerance, A = B + offset).**

Passes when ``first <comparison_type> second + offset`` holds, where each side is the text or an attribute of the one element its XPath selects. Both values are compared as numbers or as points in time.

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
     - **Required.** Path to the XML file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``xpath``
     - string
     - **Required.** Selects the element of the first value (the ElementPath subset of :doc:`element_text_matches`). It must select exactly one element (with ``attribute``: one element that has it).
   * - ``other_xpath``
     - string
     - **Required.** Selects the element of the second value; same rules. May equal ``xpath`` to compare two attributes of one element.
   * - ``attribute``
     - string
     - **Optional.** Take the first value from this attribute (``{uri}name`` for namespaced attributes). Default: the element text (``element.text``, before the first child).
   * - ``other_attribute``
     - string
     - **Optional.** The same for the second value.
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
   * - ``namespaces``
     - dict
     - **Optional.** Prefix -> URI map for prefixed names in both XPaths.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: modified_after_created
       function: xml.values_compare
       parameter:
         dst: /home/user/data/list.xml
         xpath: "//entry[@ref='item-42']"
         attribute: modified
         other_xpath: "//entry[@ref='item-42']"
         other_attribute: created
         comparison_type: greater_equal

     - name: saved_one_above_opened
       function: xml.values_compare
       parameter:
         dst: /home/user/.config/app/stats.xml
         xpath: ./counters/saved
         other_xpath: ./counters/opened
         offset: 1

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

* :doc:`element_text_matches`, :doc:`attribute_matches` — one value against a constant (also ``greater``/``less``).
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
