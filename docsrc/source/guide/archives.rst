Files inside archives
=====================

Evidence often sits in an archive: a rotated log (``syslog.2.gz``), a backup
(``backup.tar.gz``), an export (``.zip``) or an LZ4-compressed store (``.jsonlz4``). Every
file testfunction (``json``, ``jsonl``, ``csv``, ``excel``, ``xml``, ``sqlite``, ``ini``,
``plist``, ``yaml``, ``toml``, ``image``, ``text`` and the ``standard`` file tests) can read
a file inside an archive. Point ``dst`` at the member with ``!``. This works the same way in
guest mode and in host mode.

Syntax
------

.. code-block:: yaml

   tests:
     - name: app_config_in_backup
       function: json.value_matches
       parameter:
         dst: /home/user/backup.tar.gz!/etc/app/config.json   # a member of a tar or zip
         key_path: port
         expected_value: 8080

     - name: login_in_rotated_log
       function: standard.file_content_contains
       parameter:
         dst: /var/log/syslog.2.gz!                           # decompressed content of a .gz/.bz2/.xz/.lz4
         content: Accepted password for alice

     - name: nested
       function: json.contains_key
       parameter:
         dst: /home/user/outer.zip!/inner.tar.gz!/data.json   # an archive inside an archive
         key_path: id

     - name: newest_export
       function: standard.file_exists
       parameter:
         dst: /home/user/backup-*.zip!/logs/app-*.log         # globs on both sides

     - name: mapping_form
       function: json.value_matches
       parameter:
         dst:                                                 # same meaning as the first test
           archive: /home/user/backup.tar.gz
           member: etc/app/config.json
         key_path: port
         expected_value: 8080

- The separator is ``!/``, or ``!`` at the end of the path. A ``!`` followed by anything
  else (``wow!.txt``) or inside a glob bracket (``[!a]``) is part of the name.
- Member paths always use ``/``, also on Windows guests: ``C:\Users\u\b.zip!/x.json``.
- A member is named by its path inside the archive. A leading ``./`` or ``/`` in the
  archive does not matter.
- The mapping form is turned into the string form before the test runs. It takes exactly
  ``archive`` and ``member``. Without ``member`` it means the decompressed content.
  ``adare experiment playbook validate`` rejects other keys.
- Only file members can be read; a directory member gives ERROR.

Formats
-------

tar (plain, ``.gz``, ``.bz2``, ``.xz``, ``.lz4``, ``.sz``), zip (also ``.docx``/``.xlsx``/``.odt``,
which are zip files), and single-file gzip, bzip2, xz, LZ4 and Snappy.

The format comes from the file's **content** (its magic bytes), not from its extension, so
a renamed or extensionless archive works. A compressed file that holds a tar is a tar:
``backup.tar.gz!/etc/x`` reads a member, and ``backup.tar.gz!`` gives the decompressed
``.tar``. 7z is not supported yet.

LZ4 comes in two forms, both read by a decoder in pure Python:

- the **LZ4 frame format** (``.lz4``, magic ``04 22 4D 18``): block and content checksums
  are verified; linked and independent blocks, uncompressed blocks, concatenated and
  skippable frames work. Frames that need a dictionary and the legacy frame format give
  ERROR.
- an **LZ4 block with an 8-byte magic and size header**, which some applications use for
  JSON stores (``.jsonlz4``). ``store.jsonlz4!`` is the JSON text, so any ``json`` test
  reads it:

  .. code-block:: yaml

     - name: entry_in_compressed_store
       function: json.value_count
       parameter:
         dst: /home/user/.config/app/store.jsonlz4!
         key_path: entries[*].title
         expected_value: Example
         expected_count: 1

A size header or frame content size over the size cap is refused before decoding.

**Snappy** is read in its framing format (``.sz``), detected by its stream identifier; chunk
checksums are verified (``data.json.sz!``, ``backup.tar.sz!/etc/app.json``). Raw Snappy blocks
have no magic bytes and are not detected.

Office and OpenDocument metadata
--------------------------------

Office Open XML (``.docx``, ``.xlsx``, ``.pptx``) and OpenDocument (``.odt``, ``.ods``,
``.odp``) files are zip archives whose document metadata is a small XML member, so the
``xml`` tests read it through the archive separator. ``xpath`` is evaluated on the member's
root element; prefixed names need ``namespaces``.

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Member
     - Holds
   * - ``docProps/core.xml``
     - Office Open XML core properties: ``dc:creator`` (author), ``cp:lastModifiedBy``,
       ``cp:revision``, ``dcterms:created``, ``dcterms:modified``, ``dc:title``
   * - ``docProps/app.xml``
     - Office Open XML extended properties (default namespace): ``TotalTime`` (editing
       minutes), ``Pages``, ``Company``, the writing application and its version
   * - ``meta.xml``
     - OpenDocument metadata under ``office:meta``: ``meta:initial-creator``,
       ``dc:creator`` (last modified by), ``meta:editing-cycles``, ``meta:creation-date``,
       ``dc:date``

.. code-block:: yaml

   - name: author_and_last_editor
     function: xml.element_text_matches
     parameter:
       dst: /home/user/Documents/report.docx!/docProps/core.xml
       xpath: ./cp:lastModifiedBy
       expected_value: analyst
       namespaces:
         cp: http://schemas.openxmlformats.org/package/2006/metadata/core-properties
         dc: http://purl.org/dc/elements/1.1/
         dcterms: http://purl.org/dc/terms/

   - name: saved_twice
     function: xml.element_text_matches
     parameter:
       dst: /home/user/Documents/report.docx!/docProps/core.xml
       xpath: ./cp:revision
       expected_value: '2'
       namespaces:
         cp: http://schemas.openxmlformats.org/package/2006/metadata/core-properties

   - name: odt_editing_cycles
     function: xml.element_text_matches
     parameter:
       dst: /home/user/Documents/doc.odt!/meta.xml
       xpath: ./office:meta/meta:editing-cycles
       expected_value: '3'
       namespaces:
         office: urn:oasis:names:tc:opendocument:xmlns:office:1.0
         meta: urn:oasis:names:tc:opendocument:xmlns:meta:1.0

   - name: xlsx_company
     function: xml.element_text_matches
     parameter:
       dst: /home/user/Documents/book.xlsx!/docProps/app.xml
       xpath: ./ep:Company
       expected_value: Example Ltd
       namespaces:
         ep: http://schemas.openxmlformats.org/officeDocument/2006/extended-properties

An element the application did not write (no ``cp:lastModifiedBy`` in a never-edited file) is
absent, not empty: ``xml.element_count`` with ``expected_count: 0`` asserts that.

Results
-------

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Situation
     - Result
   * - Archive missing, unreadable, corrupt or of an unsupported format
     - **ERROR**, for every test, also ``standard.file_does_not_exist``
   * - A member over the size cap
     - **ERROR**
   * - The member is a link, or its path contains ``..``
     - **ERROR**: links are not followed
   * - An archive glob that does not match exactly one file
     - **ERROR**
   * - A member glob with no match or several, where the test needs one
     - **ERROR**, as for a glob on the file system
   * - Archive read fine, member absent
     - Like a missing file: content tests give ERROR, ``file_does_not_exist`` passes,
       ``file_exists`` fails

Every result gets a provenance line, for example::

   archive member: etc/app/config.json from /home/user/backup.tar.gz sha256=9f2c…, 31 bytes

For a nested archive the hash is the hash of the outer file, the one on the guest's disk.
Messages show members by their archive path (``backup.tar.gz!/etc/app/config.json``), not
by the temporary copy.

How it works
------------

Only the requested member is extracted, by streaming it into a temporary directory under a
sanitized name. Nothing is ever written by the name stored in the archive, so a hostile
archive cannot write outside that directory. The directory is removed when the test ends.
In host mode only the archive is pulled from the guest; the member is extracted on the
host. For ``sqlite.query_result``, ``-wal`` and ``-journal`` files next to the database in
the same archive are extracted with it.

Size cap
--------

A member larger than ``ADARE_ARCHIVE_MAX_BYTES`` (default 1 GiB) gives ERROR. The cap
applies to each extracted file, also to the decompressed content of a ``.gz``. Raise it in
the environment of the process that runs the test: the guest agent in guest mode, the
``adare`` CLI in host mode.
