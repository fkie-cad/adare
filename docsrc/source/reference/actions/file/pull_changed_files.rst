pull_changed_files
==================

Automatically pull all files that changed or were added between two filesystem snapshots.

Usage Example
-------------

.. code-block:: yaml

   actions:
     # Capture initial filesystem state
     - snapshot_filesystem:
         variable: "fs_before"
         description: "Initial state"

     # Perform operations that modify files
     - command:
         command: "create_files.sh"
         shell: true

     # Capture final filesystem state
     - snapshot_filesystem:
         variable: "fs_after"
         description: "Final state"

     # Pull all changed/added files
     - pull_changed_files:
         snapshot_before: "fs_before"
         snapshot_after: "fs_after"
         description: "Pull modified forensic artifacts"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``snapshot_before``
     - string
     - Variable name with initial snapshot (required)
   * - ``snapshot_after``
     - string
     - Variable name with final snapshot (required)
   * - ``dst``
     - string
     - Destination folder in artifacts (default: ``changed_files``)
   * - ``mode``
     - string
     - Transfer mode: ``hypervisor`` or ``websocket`` (default: ``websocket``)
   * - ``include_modified``
     - boolean
     - Pull modified files (default: true)
   * - ``include_added``
     - boolean
     - Pull added files (default: true)
   * - ``description``
     - string
     - Human-readable description (optional)

File Categories
---------------

- **Modified**: Files that existed before and were changed
- **Added**: Files that did not exist before
- **Deleted**: Files tracked but not pulled (verify with tests)

Notes
-----

- Automatically calculates diff between snapshots
- Uses efficient chunked transfer for multiple files
- Preserves full VM path structure in destination
- At least one of ``include_modified`` or ``include_added`` must be true
- Useful for forensic artifact collection after operations

See Also
--------

- :doc:`snapshot_filesystem` for capturing filesystem state
- :doc:`pull` for pulling specific files
