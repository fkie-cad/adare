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

.. tip::

   Watch ADARE in action! See :doc:`paper/demos` for demo videos showing file deletion experiments on Ubuntu 22.04 and Windows 11 with full playbooks.

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

1. **Install ADARE** → :doc:`getting-started/installation`
2. **Quick Tutorial** → :doc:`getting-started/tutorial`
3. **Core Concepts** → :doc:`getting-started/concepts`

Documentation Structure
-----------------------

**🚀 Getting Started**
  :doc:`getting-started/installation` - Installation, tutorial, and core concepts

**📖 User Guide**
  :doc:`guide/projects` - Workflow-oriented guides for projects, experiments, and analysis techniques

**📚 Reference**
  :doc:`reference/actions` - Actions, test functions, CLI, and output formats

**⚡ Advanced**
  :doc:`advanced/playbook-patterns` - Advanced playbook patterns and custom testfunctions

**🏗️ Architecture**
  :doc:`architecture/index` - Understanding how ADARE works internally


.. toctree::
   :hidden:

   Home <self>

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Getting Started

   getting-started/installation
   getting-started/tutorial
   getting-started/concepts

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: User Guide

   guide/projects
   guide/environments
   guide/experiments
   guide/test-driven-analysis
   guide/diff-analysis
   guide/vm-image-creation
   guide/dev-mode
   guide/sharing

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Reference

   reference/actions
   reference/testfunctions/index
   reference/cli
   reference/output-formats

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Advanced

   advanced/playbook-patterns
   advanced/testfunction-create

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Architecture

   architecture/index
   architecture/hypervisors
   architecture/file-sharing
   architecture/guest-agent
   architecture/cv-server

.. toctree::
   :hidden:
   :maxdepth: 1
   :caption: Paper

   paper/demos
