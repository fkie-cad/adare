namespace_matches
=================

Tests if XML namespace declarations match expected namespaces with support for exact matching or containment checking.

Parameters
----------

* **dst** (str, required): Path to the XML file (supports glob patterns)
* **expected_namespaces** (dict, required): Expected namespace prefix to URI mapping
* **check_mode** (str, optional): Matching mode (default: "contains")

  * ``contains``: XML must contain all expected namespaces (may have additional ones)
  * ``exact``: XML must have exactly the expected namespaces (no more, no less)

Examples
--------

Check for required namespaces:

.. code-block:: yaml

   - name: check_required_namespaces
     function: xml.namespace_matches
     parameter:
       dst: "/path/to/document.xml"
       expected_namespaces:
         "": "http://example.com/default"
         "ns1": "http://example.com/namespace1"
         "ns2": "http://example.com/namespace2"
       check_mode: "contains"

Exact namespace matching:

.. code-block:: yaml

   - name: check_exact_namespaces
     function: xml.namespace_matches
     parameter:
       dst: "/path/to/strict-document.xml"
       expected_namespaces:
         "": "http://example.com/default"
         "app": "http://example.com/app"
       check_mode: "exact"

Default namespace only:

.. code-block:: yaml

   - name: check_default_namespace
     function: xml.namespace_matches
     parameter:
       dst: "/path/to/simple.xml"
       expected_namespaces:
         "": "http://example.com/default"

Multiple prefixes:

.. code-block:: yaml

   - name: check_multiple_prefixes
     function: xml.namespace_matches
     parameter:
       dst: "/path/to/complex.xml"
       expected_namespaces:
         "soap": "http://schemas.xmlsoap.org/soap/envelope/"
         "tns": "http://tempuri.org/"
         "xsi": "http://www.w3.org/2001/XMLSchema-instance"

Notes
-----

* **Namespace Prefixes**:

  * Use empty string ``""`` for default namespace (xmlns="...")
  * Use prefix names for prefixed namespaces (xmlns:prefix="...")

* **Check Modes**:

  * ``contains``: Allows additional namespaces beyond expected ones
  * ``exact``: Requires exactly the specified namespaces, no more or less

* **Limitation**: Uses ElementTree's basic namespace detection (only from root element attributes)
* **URI Matching**: Both prefix and URI must match exactly (case-sensitive)