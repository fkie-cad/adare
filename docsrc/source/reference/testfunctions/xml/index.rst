XML
===

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 7
:Category: XML Data

.. adare-testfunction-collection:: xml

XPath and Namespaces
--------------------

Every ``xpath`` is the ``ElementPath`` subset of XPath from the Python standard library, the same
parser on every guest, evaluated on the root element:

* ``//tag`` (any depth), ``./child/grandchild`` or ``child/grandchild`` (relative to the root),
  ``/root/child`` (the first step must be the root tag; another root matches nothing), ``*``.
* Predicates ``[@attr]``, ``[@attr='v']``, ``[tag='v']`` and positions such as ``[1]``.
* An expression with ``(``, ``::``, ``..`` or ``|``, even inside a quoted value, is an error
  instead of matching nothing: no functions (``text()``, ``contains()``), axes or unions.

Prefixed names need a ``namespaces`` map (``{dc: 'http://purl.org/dc/elements/1.1/'}`` with
``./dc:creator``); ``{uri}tag`` works without it. A default namespace has no prefix in the
file, so give it one in ``namespaces``. Office documents are zip containers: their metadata
is read through ``report.docx!/docProps/core.xml``.

"Text" is ``element.text``: the text before the element's first child, not stripped.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_xml.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: xml-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   element_exists
   element_text_matches
   attribute_matches
   element_count
   xpath_result_matches
   namespace_matches
   values_compare
