.. ADARE documentation master file

.. role:: boldprimary
   :class: boldprimary

Welcome to ADARE!
===================

**The Automated Desktop Analysis framework for Reproducible Experiments**

.. image:: logo.png
   :width: 150px
   :align: right
   :alt: ADARE Logo

ADARE is a powerful framework designed for **forensic artifact analysis** and **digital forensics research**. It automates desktop interactions within virtual machines to detect and analyze changes in forensic artifacts across different software and operating system versions.

.. raw:: html

   <!-- Placeholder for demo video/gif -->
   <div style="text-align: center; margin: 30px 0; padding: 20px; border: 2px dashed #ccc; background-color: #f9f9f9;">
     <p style="margin: 0; color: #666; font-size: 16px;">📹 <strong>Demo Video Coming Soon!</strong></p>
     <p style="margin: 5px 0 0 0; color: #888; font-size: 14px;">A short video demonstration showing ADARE in action</p>
   </div>

What makes ADARE unique?
------------------------

🔬 **Forensic Focus**
   Specifically designed for digital forensics research with built-in artifact analysis capabilities

🤖 **GUI Automation**
   Uses advanced computer vision and GUI automation to simulate realistic user interactions

📊 **Reproducible Experiments**
   YAML-based playbooks ensure experiments can be shared, reproduced, and validated by others

🔄 **Cross-Platform Testing**
   Test forensic tools and artifacts across multiple OS versions and software configurations

🌐 **Community Sharing**
   Integration with `ADARE Web <https://adare.seclab-bonn.de/>`_ for sharing experiments and results

Key Use Cases
-------------

**Forensic Tool Validation**
   Test how forensic tools behave across different OS versions and validate their reliability

**Artifact Analysis**
   Analyze how user actions create, modify, or delete forensic artifacts (registry entries, file timestamps, browser history, etc.)

**Research & Education**
   Create reproducible experiments for forensic research papers or educational content

**Compliance Testing**
   Ensure forensic procedures work consistently across different system configurations

Quick Example
-------------

Here's what a simple ADARE experiment looks like:

.. code-block:: yaml

   # Delete a file and verify trash bin artifacts
   tests:
     - name: file_exists_before_deletion
       function: file_exists
       parameter:
         dst: "/home/user/testfile.txt"
     - name: file_deleted
       function: file_does_not_exist
       parameter:
         dst: "/home/user/testfile.txt"
     - name: trash_artifact_created
       function: file_exists
       parameter:
         dst: "/home/user/.local/share/Trash/files/testfile.txt"

   actions:
     - click:
         target:
           image: "file_explorer.png"
     - click:
         target:
           text: "testfile.txt"
     - test: file_exists_before_deletion
     - keyboard:
         combination: ["delete"]
     - test: file_deleted
     - test: trash_artifact_created

Getting Started
---------------

Ready to start?

1. **Install ADARE** → :doc:`basics/installation`
2. **Quick Tutorial** → :doc:`basics/tutorial`

Documentation Structure
-----------------------

**📚 Basics**
  :doc:`basics/installation` - Complete guide for daily ADARE usage - from installation to creating experiments

**⚡ Advanced**
  :doc:`advanced/cli` - CLI reference and advanced topics

**🏗️ Architecture**
  :doc:`architecture/index` - Understanding how ADARE works internally


.. toctree::
   :hidden:

   Home <self>

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Basics

   basics/installation
   basics/tutorial
   basics/projects
   basics/environments
   basics/experiments
   basics/actions
   basics/testfunctions/index

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Advanced

   advanced/cli
   advanced/testfunction-create
   advanced/vm-create

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Architecture

   architecture/index
