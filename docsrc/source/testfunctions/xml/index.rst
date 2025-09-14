XML
=================

The XML testfunctions allow testing XML files with support for XPath queries, namespace handling, regex matching, and timestamp tolerance.

All XML testfunctions support:

* **XPath expressions** for element selection
* **Namespace support** via optional namespaces parameter
* **Placeholder system** for regex patterns and timestamp tolerance (using ``{{ placeholder_name }}``)
* **Case sensitivity** control in text/attribute matching
* **Wildcard modes** (any/all) for multiple element matching

Features:

* **Regex Support**: Use ``regex_match: true`` or placeholders like ``{{ regex_pattern }}``
* **Timestamp Tolerance**: Use placeholders like ``{{ timestamp_with_tolerance }}`` for flexible timestamp comparison
* **Multiple Elements**: Handle multiple matching elements with ``wildcard_mode`` (any/all)
* **Namespaces**: Support XML namespaces with prefix mapping

.. csv-table:: 
   :file: ../../_static/tables/testfunctions_xml.csv
   :widths: 30, 5, 45, 20
   :header-rows: 1

.. toctree::
   :maxdepth: 2

   element_exists
   element_text_matches
   attribute_matches
   element_count
   xpath_result_matches
   namespace_matches