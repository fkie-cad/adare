element_text_matches
====================

Tests if XML element text content matches expected value with support for regex patterns and timestamp tolerance through placeholders.

Parameters
----------

* **dst** (str, required): Path to the XML file (supports glob patterns)
* **xpath** (str, required): XPath expression to locate the element(s)
* **expected_text** (str, required): Expected text content (supports placeholders)
* **regex_match** (bool, optional): Enable regex matching (default: false)
* **case_sensitive** (bool, optional): Case-sensitive comparison (default: true)
* **wildcard_mode** (str, optional): Mode for multiple elements: "any" or "all" (default: "any")
* **namespaces** (dict, optional): Namespace prefix to URI mapping

Examples
--------

Basic text matching:

.. code-block:: yaml

   - name: check_element_text
     function: xml.element_text_matches
     parameter:
       dst: "/path/to/document.xml"
       xpath: ".//title"
       expected_text: "My Document Title"

Regex matching:

.. code-block:: yaml

   - name: check_element_regex
     function: xml.element_text_matches
     parameter:
       dst: "/path/to/document.xml"
       xpath: ".//version"
       expected_text: "\\d+\\.\\d+\\.\\d+"
       regex_match: true

Using placeholders for regex:

.. code-block:: yaml

   - name: check_element_with_placeholder
     function: xml.element_text_matches
     parameter:
       dst: "/path/to/document.xml"
       xpath: ".//timestamp"
       expected_text: "{{ timestamp_pattern }}"

Timestamp tolerance example:

.. code-block:: yaml

   - name: check_timestamp_tolerance
     function: xml.element_text_matches
     parameter:
       dst: "/path/to/document.xml"
       xpath: ".//created_at"
       expected_text: "{{ creation_time }}"
     # Variable metadata should define creation_time with tolerance

Multiple elements with wildcard mode:

.. code-block:: yaml

   - name: check_all_status_elements
     function: xml.element_text_matches
     parameter:
       dst: "/path/to/statuses.xml"
       xpath: ".//status"
       expected_text: "active"
       wildcard_mode: "all"  # All elements must match

Notes
-----

* **Placeholder Support**: Use ``{{ placeholder_name }}`` for regex patterns and timestamp tolerance
* **Wildcard Modes**:

  * ``any``: At least one element must match (default)
  * ``all``: All elements must match

* **Case Sensitivity**: Can be disabled with ``case_sensitive: false``
* **Multiple Elements**: When XPath matches multiple elements, wildcard_mode determines success criteria