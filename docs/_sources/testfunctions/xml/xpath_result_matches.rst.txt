xpath_result_matches
====================

Tests if XPath expression result matches expected value, with support for text, number, and boolean result types.

Parameters
----------

* **dst** (str, required): Path to the XML file (supports glob patterns)
* **xpath** (str, required): XPath expression to evaluate
* **expected_result** (str/int/float/bool, required): Expected result value
* **result_type** (str, optional): Type of expected result (default: "text")

  * ``text``: String result from element text content
  * ``number``: Numeric result (converted to float)
  * ``boolean``: Boolean result (true if elements found, false otherwise)

* **namespaces** (dict, optional): Namespace prefix to URI mapping

Examples
--------

Text result:

.. code-block:: yaml

   - name: check_first_user_name
     function: xml.xpath_result_matches
     parameter:
       dst: "/path/to/users.xml"
       xpath: ".//user[1]/name"
       expected_result: "John Doe"
       result_type: "text"

Numeric result:

.. code-block:: yaml

   - name: check_total_amount
     function: xml.xpath_result_matches
     parameter:
       dst: "/path/to/invoice.xml"
       xpath: ".//total"
       expected_result: 150.75
       result_type: "number"

Boolean result:

.. code-block:: yaml

   - name: check_has_errors
     function: xml.xpath_result_matches
     parameter:
       dst: "/path/to/log.xml"
       xpath: ".//entry[@level='ERROR']"
       expected_result: true
       result_type: "boolean"

With namespaces:

.. code-block:: yaml

   - name: check_namespaced_result
     function: xml.xpath_result_matches
     parameter:
       dst: "/path/to/document.xml"
       xpath: ".//ns:value"
       expected_result: "expected_text"
       result_type: "text"
       namespaces:
         ns: "http://example.com/namespace"

Notes
-----

* **Result Types**:

  * ``text``: Returns text content of first matching element (empty string if no match)
  * ``number``: Converts element text to float (0.0 if no match or conversion fails)
  * ``boolean``: Returns true if XPath finds any elements, false otherwise

* **First Match**: For text and number types, only the first matching element is used
* **Type Conversion**: Expected values are automatically converted to match the result_type
* **XPath Limitations**: Uses ElementTree's limited XPath support (no advanced functions)