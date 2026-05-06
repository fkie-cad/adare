pull
====

Transfer files or directories from the guest VM to the host artifacts directory.

Usage Examples
--------------

**Pull Single File**

.. code-block:: yaml

   actions:
     - pull:
         src: "/var/log/app.log"
         description: "Application logs"

**Pull with Custom Name**

.. code-block:: yaml

   actions:
     - pull:
         src: "{{test_file_path}}"
         dst: "my_log.txt"
         description: "Custom named log"

**Pull Directory**

.. code-block:: yaml

   actions:
     - pull:
         src: "/home/user/evidence"
         description: "Evidence directory (recursive)"

**Pull Windows File**

.. code-block:: yaml

   actions:
     - pull:
         src: "C:\\Users\\adare\\Documents\\data.csv"
         dst: "windows_data.csv"
         description: "Windows data file"

**Pull Multiple Files**

.. code-block:: yaml

   actions:
     - pull:
         src:
           - "/tmp/log1.txt"
           - "/tmp/log2.txt"
         mode: "websocket"
         description: "Pull multiple files"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``src``
     - string or list
     - Source file/directory path(s) on VM (required)
   * - ``dst``
     - string
     - Custom destination name in artifacts folder (optional)
   * - ``mode``
     - string
     - Transfer mode: ``hypervisor`` or ``websocket`` (default: ``hypervisor``)
   * - ``description``
     - string
     - Human-readable description (optional)

Transfer Modes
--------------

- **hypervisor**: Uses VM hypervisor tools (VBoxManage) - more reliable
- **websocket**: Uses WebSocket connection - faster for multiple files

Notes
-----

- Files saved to ``<run-directory>/artifacts/``
- Without ``dst``, full VM path structure is preserved
- Supports both Linux (/) and Windows (\\) paths
- Directories are transferred recursively

See Also
--------

- :doc:`snapshot_filesystem` for capturing filesystem state
- :doc:`pull_changed_files` for pulling only changed files
