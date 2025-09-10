**********
User Guide
**********

This comprehensive guide covers everything you need for daily ADARE usage. Whether you're a forensic researcher, system administrator, or automation developer, you'll find practical information for your workflow.

.. toctree::
   :maxdepth: 2
   :caption: User Guide:

   projects
   environments  
   playbooks
   playbook-actions

Overview
********

ADARE's user interface consists of several key areas:

**Project Management**
  Organize your forensic research into logical groups

**Environment Configuration**
  Set up virtual machines for different testing scenarios

**Experiment Development**
  Create automated forensic tests and artifact analysis

**Execution & Results**
  Run experiments and analyze forensic evidence

**Sharing & Collaboration**
  Share experiments via ADARE Web platform

Daily Workflow
**************

A typical ADARE workflow follows this pattern:

1. **Create/Select Project** → Organize your work
2. **Configure Environment** → Set up test VM
3. **Design Experiment** → Create forensic test scenario  
4. **Run & Iterate** → Execute and refine experiments
5. **Analyze Results** → Review forensic evidence
6. **Share Findings** → Publish to community

Quick Reference
***************

Common Commands
===============

.. code-block:: bash

   # Project management
   adare project create my-research
   adare project list
   
   # Environment setup
   adare environment load config.yml
   adare environment list
   
   # Experiment workflow
   adare experiment create test-scenario
   adare experiment run test-scenario -e my-env
   adare run list
   
   # Results analysis  
   adare run info <run_id>
   adare run export <run_id> --format json

File Locations
==============

Understanding where ADARE stores files helps with organization:

.. code-block:: text

   my-project/
   ├── environments/
   │   └── my-env/
   │       ├── experiments/           # Experiment definitions
   │       │   └── test-scenario/
   │       │       ├── playbook.yml   # Automation script
   │       │       ├── metadata.yml   # Experiment info
   │       │       └── img/           # GUI screenshots
   │       ├── results/               # Experiment results
   │       │   └── test-scenario_<timestamp>/
   │       └── logs/                  # Execution logs
   ├── programs/                      # Shared utilities
   └── tessdata/                      # OCR data

Configuration Files
===================

Key configuration file formats:

**Environment Config** (YAML)

.. code-block:: yaml

   name: windows-test
   vm: "/path/to/vm.ova"  
   os:
     os: "Windows"
     platform: "windows"
     version: "11"

**Playbook** (YAML)

.. code-block:: yaml

   settings:
     idle: 1.0
     timeout: 300
   
   actions:
     - click: {target: {text: "File"}}
     - keyboard: {combination: ["ctrl", "s"]}

**Metadata** (YAML)

.. code-block:: yaml

   environments: ["windows-test"]
   description: "Test file save behavior"
   tags: ["filesystem", "gui"]

