File Actions
============

Actions for transferring files between the guest VM and host, and tracking filesystem changes.

Available Actions
-----------------

.. toctree::
   :maxdepth: 1

   pull
   snapshot_filesystem
   pull_changed_files

Overview
--------

File actions enable forensic evidence collection:

- **pull**: Transfer specific files or directories from VM to host
- **snapshot_filesystem**: Capture complete filesystem state
- **pull_changed_files**: Automatically pull files modified between snapshots

These actions support both hypervisor-based and WebSocket-based file transfer for flexibility and performance.
