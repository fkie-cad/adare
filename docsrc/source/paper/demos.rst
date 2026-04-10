Demo Videos
===========

These demonstrations accompany the ADARE research paper. Each demo shows a complete experiment: creating a test file, deleting it through the GUI, and verifying that the expected forensic artifacts (trash bin entries, metadata) are produced.

Ubuntu 22.04 — File Deletion & Trash Bin Verification
------------------------------------------------------

This experiment creates a file in the user's Documents folder, opens the Nautilus file manager, and moves the file to Trash via right-click context menu. ADARE then verifies that the file appears in ``~/.local/share/Trash/files/`` and that the ``.trashinfo`` metadata contains the correct original path and deletion timestamp.

.. raw:: html

   <video controls width="100%" preload="metadata">
     <source src="../demo/ubuntu2204.mp4" type="video/mp4">
     Your browser does not support the video element.
   </video>

**Playbook:**

.. literalinclude:: ../../../paper/demo/playbook_ubuntu2204.yml
   :language: yaml
   :caption: playbook_ubuntu2204.yml
   :linenos:

Key concepts demonstrated:

- :doc:`Variable templating </advanced/playbook-patterns>` with ``{{ adare_user_documents }}`` and ``{{ adare_user_home }}``
- :doc:`Test functions </reference/testfunctions/index>` ``file_exists``, ``file_does_not_exist``, and ``file_content_equals``
- :doc:`Actions </reference/actions>` including ``command``, ``click``, ``idle``, ``save_timestamp``
- Timestamp tolerance matching with ``| tolerance(5, -5)``

Windows 11 — File Deletion & Recycle Bin Verification
------------------------------------------------------

This experiment follows the same pattern on Windows 11: a test file is created, selected in File Explorer, and deleted via the ``Delete`` key. ADARE then runs ``RBCmd.exe`` to parse the Recycle Bin ``$I`` files into CSV and verifies that the deleted file's metadata (path, timestamp) appears correctly.

.. raw:: html

   <video controls width="100%" preload="metadata">
     <source src="../demo/windows11.mp4" type="video/mp4">
     Your browser does not support the video element.
   </video>

**Playbook:**

.. literalinclude:: ../../../paper/demo/playbook_windows11.yml
   :language: yaml
   :caption: playbook_windows11.yml
   :linenos:

Key concepts demonstrated:

- :doc:`Variable templating </advanced/playbook-patterns>` with Windows-style paths
- :doc:`Test function </reference/testfunctions/index>` ``csv.contains_line`` with regex and timestamp matchers
- :doc:`Actions </reference/actions>` including ``keyboard`` combination and ``block`` grouping
- External forensic tool integration (``RBCmd.exe``) via the ``command`` action with ``tool`` parameter
