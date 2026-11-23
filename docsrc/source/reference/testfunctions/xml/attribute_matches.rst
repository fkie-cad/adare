attribute_matches
=================

Tests if XML element attribute matches expected value with support for regex patterns and timestamp tolerance through placeholders.

Parameters
----------

* **dst** (str, required): Path to the XML file (supports glob patterns)
* **xpath** (str, required): XPath expression to locate the element
* **attribute_name** (str, required): Name of the attribute to check
* **expected_value** (str, required): Expected attribute value (supports placeholders)
* **regex_match** (bool, optional): Enable regex matching (default: false)
* **case_sensitive** (bool, optional): Case-sensitive comparison (default: true)
* **namespaces** (dict, optional): Namespace prefix to URI mapping
* **comparison_type** (str, optional): ``equals`` (default), ``not_equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Anything but ``equals``, or any of the parameters below, compares the value with ``expected_value`` as a number or timestamp (see :ref:`ordered-comparison`); a ``!re`` tag or ``regex_match`` is then an ERROR, a lone ``{{ name }}`` is the saved variable's value, and ``case_sensitive`` is ignored
* **value_type** (str, optional): ``auto`` (default: numbers if both sides are numbers, else timestamps), ``number`` or ``timestamp``
* **tolerance** (number, optional): Allowed difference for ``equals``/``not_equals`` (seconds for timestamps)
* **time_format** (str, optional): ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822
* **timestamp_epoch** (int, optional): Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``
* **timestamp_unit** (str, optional): Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``
* **utc_offset** (str, optional): Zone of timestamps without one (``+02:00``); default UTC
* **value_decode** (list or str, optional): Decode the value read from the file before comparing: one step or a list applied in order: ``url``, ``base64``, ``hex``, ``utf16``, ``json`` (see "Decoding a stored value" under :ref:`ordered-comparison`). A value a step cannot decode, or an unknown step, is an ERROR
* **decoded_key_path** (str, optional): With ``json`` in ``value_decode``: key path into the decoded value (syntax of :doc:`/reference/testfunctions/json/value_matches`); it must select one value. Required with ``json``

Numbers and Timestamps
----------------------

With ``comparison_type``, ``value_type``, ``tolerance`` or a time parameter the value is compared as a number or a point in time instead of by equality: greater/less (earlier/later), or equal within a tolerance. To compare two values of one file use :doc:`values_compare`. A value that is no number or timestamp is an ERROR (the test looked at the wrong field), as is a regex ``expected_value``; a lone ``{{ name }}`` placeholder compares with the saved variable. See :ref:`ordered-comparison`.

.. code-block:: yaml

   tests:
     - name: ordered_value
       function: xml.attribute_matches
       parameter:
         dst: /home/user/data/list.xml
         xpath: "//entry[@ref='item-42']"
         attribute: modified
         expected_value: "2026-03-01T10:00:00Z"
         tolerance: 60

Examples
--------

Basic attribute matching:

.. code-block:: yaml

   - name: check_element_id
     function: xml.attribute_matches
     parameter:
       dst: "/path/to/document.xml"
       xpath: ".//user"
       attribute_name: "id"
       expected_value: "12345"

Regex matching:

.. code-block:: yaml

   - name: check_version_pattern
     function: xml.attribute_matches
     parameter:
       dst: "/path/to/config.xml"
       xpath: ".//application"
       attribute_name: "version"
       expected_value: "\\d+\\.\\d+\\.\\d+"
       regex_match: true

Using placeholders for regex:

.. code-block:: yaml

   - name: check_timestamp_attribute
     function: xml.attribute_matches
     parameter:
       dst: "/path/to/log.xml"
       xpath: ".//entry"
       attribute_name: "timestamp"
       expected_value: "{{ timestamp_pattern }}"

Case-insensitive matching:

.. code-block:: yaml

   - name: check_status_case_insensitive
     function: xml.attribute_matches
     parameter:
       dst: "/path/to/status.xml"
       xpath: ".//service"
       attribute_name: "state"
       expected_value: "ACTIVE"
       case_sensitive: false

With namespaces:

.. code-block:: yaml

   - name: check_namespaced_attribute
     function: xml.attribute_matches
     parameter:
       dst: "/path/to/document.xml"
       xpath: ".//ns:element"
       attribute_name: "value"
       expected_value: "expected_value"
       namespaces:
         ns: "http://example.com/namespace"

Notes
-----

* **First Match**: If XPath matches multiple elements, only the first element's attribute is checked
* **Missing Attribute**: Test fails if the attribute doesn't exist on the element
* **Placeholder Support**: Use ``{{ placeholder_name }}`` for regex patterns and timestamp tolerance
* **Case Sensitivity**: Can be disabled with ``case_sensitive: false``