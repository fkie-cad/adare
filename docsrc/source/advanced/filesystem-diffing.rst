Filesystem Diffing
==================

ADARE can snapshot and diff the complete filesystem state around experiments, capturing all
NTFS timestamps on Windows and POSIX timestamps on Linux. Diffs are exported in
forensic-tool-compatible formats (JSON, CSV, bodyfile) for further analysis.

Enabling Filesystem Diffing
---------------------------

Filesystem diffing is **disabled by default** to avoid overhead when not needed.

**Playbook setting:**

.. code-block:: yaml

   settings:
     enable_filesystem_diff: true

**CLI override** (takes precedence over playbook):

.. code-block:: bash

   # Enable diff regardless of playbook setting
   adare experiment run myexp -e win10 --diff

   # Disable diff regardless of playbook setting
   adare experiment run myexp -e win10 --no-diff

**Diff modes:**

.. code-block:: bash

   # Auto-detect best method (default)
   adare experiment run myexp -e win10 --diff --diff-mode auto

   # Guest-side diff (always available, runs inside VM)
   adare experiment run myexp -e win10 --diff --diff-mode guest

   # Host-side diff via QEMU virt-diff (faster, requires QEMU)
   adare experiment run myexp -e win10 --diff --diff-mode host

When enabled, ADARE automatically captures a filesystem snapshot before and after the
experiment, then computes and exports the diff to the ``artifacts/`` directory.

Timestamp Comparison
--------------------

The diff compares **all available timestamps**, not just modification time. A file is
considered "modified" if *any* timestamp differs between the before and after snapshots.

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Platform
     - Timestamps compared
   * - Windows (NTFS/MFT)
     - ``created``, ``modified``, ``accessed``, ``mft_modified``
   * - Linux
     - ``modified``, ``accessed``, ``changed``

For modified files, the ``timestamp_changes`` field in JSON output shows exactly which
timestamps changed and their before/after values. This makes it straightforward to
identify, for example, files where only the access time was updated versus files that
were actually written to.

Diff Categories
~~~~~~~~~~~~~~~

Files are classified into three categories:

- **added** -- present in the after snapshot but not before
- **removed** -- present in the before snapshot but not after
- **modified** -- present in both, with any timestamp or size difference

Export Formats
--------------

All exports are written to ``{run_directory}/artifacts/``.

filesystem_diffs.json
~~~~~~~~~~~~~~~~~~~~~

Full structured diff with metadata and all timestamps. Example structure for a modified file:

.. code-block:: json

   {
     "modified": [
       {
         "path": "C:\\Users\\user\\document.docx",
         "size_before": 12345,
         "size_after": 12400,
         "timestamps_before": {
           "created": 1700000000.0,
           "modified": 1700000000.0,
           "accessed": 1700000000.0,
           "mft_modified": 1700000000.0
         },
         "timestamps_after": {
           "created": 1700000000.0,
           "modified": 1700001000.0,
           "accessed": 1700001000.0,
           "mft_modified": 1700001000.0
         },
         "timestamp_changes": {
           "modified": {
             "before": 1700000000.0,
             "after": 1700001000.0,
             "before_readable": "2023-11-14T22:13:20",
             "after_readable": "2023-11-14T22:30:00"
           }
         }
       }
     ]
   }

filesystem_diffs.csv
~~~~~~~~~~~~~~~~~~~~

Flat table with all timestamp columns (before/after) and a ``Changed Timestamps`` indicator column.

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Column
     - Description
   * - ``Change Type``
     - ADDED, REMOVED, or MODIFIED
   * - ``Path``
     - Full file path
   * - ``Size Before`` / ``Size After``
     - File size in bytes
   * - ``{ts} Before`` / ``{ts} After``
     - Before/after value for each timestamp type (created, modified, accessed, mft_modified, changed)
   * - ``Changed Timestamps``
     - Semicolon-separated list of timestamp fields that changed

All timestamp columns are present in every CSV (the full Windows + Linux superset), with
empty cells where a timestamp type does not apply to the platform.

filesystem_diffs.bodyfile
~~~~~~~~~~~~~~~~~~~~~~~~~

`Mactime bodyfile format <https://wiki.sleuthkit.org/index.php?title=Body_file>`_ for
import into Plaso, log2timeline, mactime, and other forensic timeline tools.

Each line follows the pipe-delimited format::

   0|path (CHANGE_TYPE)|0||0|0|size|atime|mtime|ctime|crtime

Where:

- ``atime`` = accessed timestamp (Unix epoch)
- ``mtime`` = modified timestamp (Unix epoch)
- ``ctime`` = changed (Linux) or mft_modified (Windows) timestamp
- ``crtime`` = created timestamp (Windows only, 0 on Linux)
- ``CHANGE_TYPE`` = ADDED, REMOVED, or MODIFIED (appended to the path as a comment)

Example::

   # ADARE filesystem diff bodyfile (mactime format)
   # OS type: Windows
   # Snapshot before: 2024-01-15T10:00:00
   # Snapshot after: 2024-01-15T10:05:00
   0|C:\Users\user\document.docx (MODIFIED)|0||0|0|12400|1700001000|1700001000|1700001000|1700000000

See Also
--------

- :doc:`../basics/actions/file/snapshot_filesystem` -- the ``snapshot_filesystem`` action that captures filesystem state
- :doc:`../basics/actions/file/pull_changed_files` -- pulling files that changed between snapshots
- :doc:`output-formats` -- general output format options
