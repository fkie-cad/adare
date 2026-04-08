snapshot_filesystem
===================

Capture the current filesystem state (files, directories, metadata) into a variable for later comparison.

Usage Example
-------------

.. code-block:: yaml

   actions:
     # Capture initial state
     - snapshot_filesystem:
         variable: "fs_before"
         description: "Capture filesystem before operation"

     # Perform operation that modifies files
     - command:
         command: "some_operation"

     # Capture final state
     - snapshot_filesystem:
         variable: "fs_after"
         description: "Capture filesystem after operation"

     # Pull changed files
     - pull_changed_files:
         snapshot_before: "fs_before"
         snapshot_after: "fs_after"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``variable``
     - string
     - Variable name to store the snapshot (required)
   * - ``root_path``
     - string
     - Root path to scan (default: ``/`` on Linux, ``C:\`` on Windows)
   * - ``timeout``
     - float
     - Timeout in seconds (default: 300)
   * - ``description``
     - string
     - Human-readable description (optional)

Captured Information
--------------------

The snapshot captures for each file/directory:

- Full path
- File size
- **Windows (NTFS/MFT):** created, modified, accessed, and mft_modified timestamps
- **Linux:** modified, accessed, and changed timestamps

All timestamps are stored as Unix epoch seconds for precise comparison.

Notes
-----

- Snapshots stored in execution context for use by other actions
- Useful for detecting filesystem changes during experiments
- Can be used with ``pull_changed_files`` to automatically pull modified files
- Large filesystems may take time to scan - adjust timeout accordingly

See Also
--------

- :doc:`pull_changed_files` for pulling files that changed between snapshots
- :doc:`pull` for transferring specific files
- :doc:`../../../advanced/filesystem-diffing` for diff export formats and forensic timeline integration
