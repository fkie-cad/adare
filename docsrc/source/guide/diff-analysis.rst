*************
Diff Analysis
*************

Diff analysis captures the complete filesystem state before and after an
experiment, then computes every change -- files added, removed, or modified --
with full timestamp granularity. Where :doc:`/guide/test-driven-analysis`
validates *specific* expected outcomes, diff analysis reveals *everything* that
changed, including artifacts you did not anticipate.


When to Use Diff Analysis
=========================

Diff analysis is the right tool when:

- **Exploratory research** -- you do not yet know which artifacts an action
  produces and want to see the full picture before writing targeted tests.
- **Unknown artifact discovery** -- you suspect an application writes to
  unexpected locations (temp files, caches, prefetch, registry hives on disk)
  and want proof.
- **Timeline forensics** -- you need a precise, timestamped record of all
  filesystem activity during an experiment for import into forensic timeline
  tools.
- **Regression detection** -- you want to compare the full change sets of the
  same experiment across two OS versions or software updates to spot
  differences beyond what your tests cover.

Diff analysis vs test-driven analysis (or both)
------------------------------------------------

The two approaches are complementary:

- **Test-driven analysis** is targeted: it checks specific artifacts against
  specific expectations and produces clear pass/fail verdicts. Use it when you
  know what to look for.
- **Diff analysis** is comprehensive: it captures everything but requires manual
  review to separate signal from noise. Use it when you are exploring.

In practice, many experiments benefit from both. Run diff analysis during early
exploration to identify relevant artifacts, then encode those findings as tests
for reproducible validation. Keep diff analysis enabled alongside tests to catch
unexpected side effects.


Enabling Filesystem Diffing
============================

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
====================

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
---------------

Files are classified into three categories:

- **added** -- present in the after snapshot but not before
- **removed** -- present in the before snapshot but not after
- **modified** -- present in both, with any timestamp or size difference


Export Formats
==============

All exports are written to ``{run_directory}/artifacts/``.

filesystem_diffs.json
---------------------

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
--------------------

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
-------------------------

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


Combining Diff Analysis with Tests
===================================

For maximum coverage, use the ``snapshot_filesystem`` and
``pull_changed_files`` actions within a test-driven playbook:

.. code-block:: yaml

   settings:
     enable_filesystem_diff: true

   tests:
     - name: history_db_exists
       function: standard.file_exists
       parameter:
         dst: "C:\\Users\\adare\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\History"

   actions:
     - action: file.snapshot_filesystem
       parameter:
         label: before

     # ... perform user actions ...

     - action: test
       parameter:
         name: history_db_exists

     - action: file.snapshot_filesystem
       parameter:
         label: after

     - action: file.pull_changed_files
       parameter:
         label_before: before
         label_after: after

This approach gives you both targeted pass/fail verdicts from tests and a
complete change inventory from the diff. The pulled files are available in the
run directory for offline analysis.

See :doc:`/reference/actions/file/snapshot_filesystem` and
:doc:`/reference/actions/file/pull_changed_files` for full parameter details.


Integration with Forensic Tools
================================

The bodyfile export is designed for direct import into standard forensic
timeline tools.

Plaso / log2timeline
--------------------

Convert the bodyfile to a Plaso storage file for timeline analysis:

.. code-block:: bash

   log2timeline.py timeline.plaso artifacts/filesystem_diffs.bodyfile

Then generate a sorted timeline:

.. code-block:: bash

   psort.py -o l2tcsv -w timeline.csv timeline.plaso

mactime (Sleuth Kit)
--------------------

Generate a human-readable timeline directly from the bodyfile:

.. code-block:: bash

   mactime -b artifacts/filesystem_diffs.bodyfile -d > timeline.csv

Use date-range filtering to focus on the experiment window:

.. code-block:: bash

   mactime -b artifacts/filesystem_diffs.bodyfile -d 2024-01-15T10:00:00..2024-01-15T10:05:00 > timeline.csv

These timelines can then be correlated with ADARE test results and action
timestamps to build a complete forensic narrative of the experiment.


See Also
========

- :doc:`/reference/actions/file/snapshot_filesystem` -- the ``snapshot_filesystem`` action that captures filesystem state
- :doc:`/reference/actions/file/pull_changed_files` -- pulling files that changed between snapshots
- :doc:`/reference/output-formats` -- general output format options
- :doc:`/guide/test-driven-analysis` -- defining expected outcomes with test assertions
