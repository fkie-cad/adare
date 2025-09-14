element_count
=============

Tests the number of XML elements matching an XPath expression against expected count with various comparison modes.

Parameters
----------

* **dst** (str, required): Path to the XML file (supports glob patterns)
* **xpath** (str, required): XPath expression to locate elements
* **expected_count** (int, required): Expected number of matching elements
* **comparison_type** (str, optional): Comparison mode (default: "equals")

  * ``equals``: Exact count match
  * ``greater``: More than expected count
  * ``less``: Fewer than expected count
  * ``greater_equal``: At least expected count
  * ``less_equal``: At most expected count

* **namespaces** (dict, optional): Namespace prefix to URI mapping

Examples
--------

Exact count:

.. code-block:: yaml

   - name: check_user_count
     function: xml.element_count
     parameter:
       dst: "/path/to/users.xml"
       xpath: ".//user"
       expected_count: 10

Minimum count:

.. code-block:: yaml

   - name: check_minimum_entries
     function: xml.element_count
     parameter:
       dst: "/path/to/log.xml"
       xpath: ".//entry[@level='ERROR']"
       expected_count: 1
       comparison_type: "greater_equal"

Maximum count:

.. code-block:: yaml

   - name: check_maximum_warnings
     function: xml.element_count
     parameter:
       dst: "/path/to/log.xml"
       xpath: ".//entry[@level='WARNING']"
       expected_count: 5
       comparison_type: "less_equal"

With namespaces:

.. code-block:: yaml

   - name: check_namespaced_count
     function: xml.element_count
     parameter:
       dst: "/path/to/document.xml"
       xpath: ".//ns:item"
       expected_count: 3
       namespaces:
         ns: "http://example.com/namespace"

Notes
-----

* **Comparison Types**:

  * ``equals``: count == expected_count
  * ``greater``: count > expected_count
  * ``less``: count < expected_count
  * ``greater_equal``: count >= expected_count
  * ``less_equal``: count <= expected_count

* **Zero Count**: Returns 0 if no elements match the XPath
* **Complex XPath**: Supports attribute filters and other XPath features within ElementTree limitations