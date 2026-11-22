contains_key
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: YAML Data
:Function Name: ``contains_key``

**Tests if a YAML file contains the specified key path.**

Passes when the key path selects at least one value (a ``null`` value counts). To check the value use :doc:`value_matches`; to check that a key is absent use :doc:`value_count` with ``expected_count: 0`` (or ``expect_to_fail: true`` here — a missing file stays an error).

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
     - **Required.** Path to the YAML file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``key_path``
     - string
     - **Required.** Dot path from the root, e.g. ``a.b.c``. ``*`` expands all values of a dictionary, ``name[*]`` all elements of array ``name``, ``name[0]`` / ``name[-1]`` one element; a leading ``[0]`` / ``[*]`` addresses a top-level array. ``['a.b']`` is a key that contains dots.

Key Paths and Values
--------------------

A file with one document is addressed from its root. A file with several documents (separated by ``---``) is a top-level list with one entry per document: ``[0].kind`` is ``kind`` in the first document, ``[*].kind`` in all of them. An empty file has no keys. Files are read as UTF-8, or UTF-16 with a byte order mark.

Values keep their YAML 1.1 types: ``5`` is an integer, ``true``/``yes``/``on`` and ``false``/``no``/``off`` are booleans, ``null`` is ``None``. Dates and timestamps become ISO 8601 strings: ``2024-01-15``, ``2024-01-15T10:30:00``, and a ``Z`` zone becomes ``+00:00``. ``!!binary`` values become lowercase hex strings.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: yaml_has_key
       function: yaml.contains_key
       parameter:
         dst: /home/user/.config/app/config.yaml
         key_path: "display.font.size"

Return Values
-------------

**Success**
  The key path selects at least one value.

**Failure**
  The file was read and the key path selects nothing.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read,
  the content is not valid YAML (syntax error, unknown or unsafe tag, impossible date, undecodable bytes).
