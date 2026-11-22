contains_key
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: TOML Data
:Function Name: ``contains_key``

**Tests if a TOML file contains the specified key path.**

Passes when the key path selects at least one value. To check the value use :doc:`value_matches`; to check that a key is absent use :doc:`value_count` with ``expected_count: 0`` (or ``expect_to_fail: true`` here — a missing file stays an error).

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
     - **Required.** Path to the TOML file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``key_path``
     - string
     - **Required.** Dot path from the root, e.g. ``a.b.c``. ``*`` expands all values of a dictionary, ``name[*]`` all elements of array ``name``, ``name[0]`` / ``name[-1]`` one element; a leading ``[0]`` / ``[*]`` addresses a top-level array. ``['a.b']`` is a key that contains dots.

Key Paths and Values
--------------------

Tables are dictionaries: ``[server]`` with ``port = 8080`` is ``server.port``. An array of tables (``[[items]]``) is an array: ``items[*].name`` selects every entry, ``items[0].name`` the first. A quoted table or key name with dots (``["app.window"]``) uses quotes in brackets: ``['app.window'].width``. Files are read as UTF-8.

Values keep their TOML types (integers, floats, booleans, strings). Dates and times become ISO 8601 strings: ``1979-05-27`` (local date), ``07:32:00`` (local time), ``1979-05-27T07:32:00`` (local date-time), ``1979-05-27T07:32:00-08:00`` (offset date-time; ``Z`` becomes ``+00:00``).

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: toml_has_key
       function: toml.contains_key
       parameter:
         dst: /home/user/.config/app/settings.toml
         key_path: "server.port"

Return Values
-------------

**Success**
  The key path selects at least one value.

**Failure**
  The file was read and the key path selects nothing.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read,
  the content is not valid TOML (syntax error, duplicate key, impossible date or time, bytes that are not UTF-8).
