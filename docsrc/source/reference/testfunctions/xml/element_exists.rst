element_exists
==============

Tests if an XML element exists at the specified XPath location.

Parameters
----------

* **dst** (str, required): Path to the XML file (supports glob patterns)
* **xpath** (str, required): XPath expression to locate the element
* **namespaces** (dict, optional): Namespace prefix to URI mapping

Example
-------

Test if a specific element exists:

.. code-block:: yaml

   - name: check_user_element
     function: xml.element_exists
     parameter:
       dst: "/path/to/users.xml"
       xpath: ".//user[@id='123']"

With namespaces:

.. code-block:: yaml

   - name: check_namespaced_element
     function: xml.element_exists
     parameter:
       dst: "/path/to/document.xml"
       xpath: ".//ns:element"
       namespaces:
         ns: "http://example.com/namespace"

Notes
-----

* Returns success if at least one element matches the XPath
* Uses Python's ``xml.etree.ElementTree`` for parsing
* XPath support is limited compared to full XPath 2.0 (basic element/attribute selection)
* For complex XPath expressions, consider using ``xpath_result_matches`` function