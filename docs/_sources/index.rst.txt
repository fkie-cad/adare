.. ADARE documentation master file

.. role:: boldprimary
   :class: boldprimary

ADARE Documentation
===================

**Automated Desktop Analysis framework for Reproducible Experiments**

.. image:: logo.png
   :width: 150px
   :align: right
   :alt: ADARE Logo

ADARE is a powerful framework designed for **forensic artifact analysis** and **digital forensics research**. It automates desktop interactions within virtual machines to detect and analyze changes in forensic artifacts across different software and operating system versions.

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
   actions:
     - click:
         target:
           image: "file_explorer.png"
     - click:
         target:
           text: "testfile.txt"
     - keyboard:
         combination: ["delete"]
   
   tests:
     - name: file_deleted
       function: file_does_not_exist
       parameter:
         dst: "/home/user/testfile.txt"
     - name: trash_artifact_created
       function: file_exists
       parameter:
         dst: "/home/user/.local/share/Trash/files/testfile.txt"

Getting Started
---------------

Ready to start? Follow our step-by-step guide:

1. **Install ADARE** → :doc:`installation/index`
2. **Quick Tutorial** → :doc:`quickstart/index`
3. **Create Your First Experiment** → :doc:`quickstart/first-experiment`

Documentation Structure
-----------------------

.. grid:: 2 2 2 2

   .. grid-item-card:: 🚀 Quick Start
      :link: quickstart/index
      :link-type: doc
      
      Get up and running with ADARE in minutes

   .. grid-item-card:: 👤 User Guide
      :link: user-guide/index
      :link-type: doc
      
      Complete guide for daily ADARE usage

   .. grid-item-card:: 💻 CLI Reference
      :link: cli-reference/index
      :link-type: doc
      
      Complete command-line interface documentation

   .. grid-item-card:: 🏗️ Architecture
      :link: architecture/index
      :link-type: doc
      
      Understanding how ADARE works internally

   .. grid-item-card:: ⚡ Advanced Topics
      :link: advanced/index
      :link-type: doc
      
      Custom test functions, VM management, and performance tuning


.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Getting Started:

   installation/index
   quickstart/index

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: User Documentation:

   user-guide/index
   cli-reference/index

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Technical Documentation:

   architecture/index
   advanced/index
   developer/index
