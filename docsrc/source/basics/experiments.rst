***********
Experiments
***********

Experiments are the core units of forensic research in ADARE. They contain automation scripts (playbooks), metadata configuration, and resources needed to conduct reproducible forensic analysis.

Creating Experiments
********************

Create a new experiment in your current project:

.. code-block:: bash

   adare experiment create my-experiment

This creates the experiment directory structure:

.. code-block:: text

   experiments/my-experiment/
   ├── metadata.yml    # Experiment configuration
   ├── playbook.yml    # Automation and validation script
   ├── img/           # Screenshots for GUI automation
   └── shared/        # Experiment-specific resources
       ├── data/      # Test data files
       └── tools/     # Custom tools or scripts

Experiment Metadata
*******************

The ``metadata.yml`` file configures which environments can run this experiment:

Basic Configuration
===================

.. code-block:: yaml
   :caption: experiments/my-experiment/metadata.yml

   environments:
     - ubuntu24043
     - win11

This experiment can run on both Ubuntu 24.04.3 and Windows 11 environments.

Multiple Environment Example
============================

.. code-block:: yaml
   :caption: experiments/cross-platform-test/metadata.yml

   environments:
     - ubuntu24043
     - ubuntu22045
     - win10
     - win11

Advanced Configuration
======================

You can add additional metadata for organization:

.. code-block:: yaml

   environments:
     - ubuntu24043

   description: "Analysis of file deletion artifacts in Ubuntu"
   tags:
     - filesystem
     - deletion
     - trash-analysis

   author: "Forensic Research Team"
   created: "2025-09-15"

Experiment Directory Structure
******************************

Understanding the experiment layout:

Core Files
==========

**metadata.yml**
  Defines which environments can run this experiment

**playbook.yml**
  Contains the automation script with actions, tests, variables, and settings

**img/ directory**
  Screenshots for GUI automation - ADARE matches these images to find interface elements

**shared/ directory**
  Experiment-specific resources:

  - ``shared/data/``: Test files, sample evidence, configuration files
  - ``shared/tools/``: Custom scripts, forensic tools, utilities

Example Structure
=================

.. code-block:: text

   experiments/browser-history-analysis/
   ├── metadata.yml
   ├── playbook.yml
   ├── img/
   │   ├── firefox_icon.png
   │   ├── history_menu.png
   │   └── clear_data_dialog.png
   ├── shared/
   │   ├── data/
   │   │   ├── test_bookmarks.json
   │   │   └── sample_history.sql
   │   └── tools/
   │       ├── browser_analyzer.py
   │       └── history_extractor.sh

Working with Experiments
************************

Listing Experiments
===================

.. code-block:: bash

   # List all experiments in current project
   adare experiment list

   # Show experiment details
   adare experiment info my-experiment

Running Experiments
===================

.. code-block:: bash

   # Development/test run (default: allows modifications, creates fake runs)
   adare experiment run my-experiment -e ubuntu24043

   # Production run (strict integrity checks, creates real runs)
   adare experiment run my-experiment -e ubuntu24043 --production

   # Run on all configured environments
   adare experiment run my-experiment

Managing Experiments
====================

.. code-block:: bash

   # Copy experiment for modification
   adare experiment copy my-experiment my-experiment-v2

   # Remove experiment
   adare experiment remove my-experiment

   # Develop interactively
   adare experiment develop my-experiment -e ubuntu24043

Best Practices
**************

Experiment Organization
=======================

1. **Descriptive Names**: Use clear, descriptive experiment names

   .. code-block:: bash

      # Good
      adare experiment create windows-registry-artifacts
      adare experiment create chrome-download-analysis

      # Avoid
      adare experiment create test1
      adare experiment create experiment

2. **Environment Compatibility**: Test your experiments on all specified environments

3. **Resource Management**: Keep experiment-specific files in the ``shared/`` directory

4. **Documentation**: Use clear descriptions in metadata and playbook comments

Playbook Structure
==================

Start your playbook with proper documentation:

.. code-block:: yaml

   # Experiment: File Deletion Analysis
   # Purpose: Study how different file deletion methods affect forensic artifacts
   # Environments: Ubuntu 24.04.3
   # Expected Duration: 5-10 minutes

   settings:
     idle: 1.0
     timeout: 600
     screenshot:
       format: "png"
       quality: 95

   # ... rest of playbook

Version Control
===============

Consider version control for experiment development:

.. code-block:: bash

   # Initialize git in project
   git init
   git add experiments/
   git commit -m "Initial experiment setup"

   # Track changes during development
   git add experiments/my-experiment/
   git commit -m "Add GUI automation for file deletion"

Experiment Lifecycle
********************

Development Phase
=================

1. Create experiment structure
2. Develop and test playbook with ``--test`` flag
3. Refine based on results
4. Validate on target environments

Production Phase
================

1. Run final validation
2. Execute without ``--test`` flag (locks experiment)
3. Document results and findings
4. Archive or version for future reference

.. tip::
   **Development vs Production Runs**

   - Use ``--test`` during development to keep modifying the playbook
   - Production runs (without ``--test``) lock the experiment to ensure reproducibility
   - Copy experiments before production runs if you need to continue development

Troubleshooting
***************

Common Issues
=============

**Experiment Won't Start**
  - Check that specified environments exist: ``adare environment list``
  - Verify metadata.yml syntax is correct
  - Ensure VM is accessible and not corrupted

**Playbook Syntax Errors**
  - Validate YAML syntax with an online checker
  - Check for proper indentation (use spaces, not tabs)
  - Verify all referenced variables are defined

**Image Recognition Failures**
  - Update screenshots in ``img/`` directory
  - Use text-based targeting when possible
  - Check image file formats (PNG recommended)

**Environment Mismatches**
  - Ensure experiment is compatible with target environment
  - Check OS version requirements
  - Verify required software is installed in VM

Next Steps
**********

- **Create your first experiment**: Follow the :doc:`tutorial`
- **Learn playbook automation**: See :doc:`actions`
- **Understand validation**: Explore :doc:`testfunctions/index`