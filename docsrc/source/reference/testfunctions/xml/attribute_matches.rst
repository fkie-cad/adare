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