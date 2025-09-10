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

Best Practices
**************

Organization
============

**Use Descriptive Names**
  ``browser-history-analysis`` not ``test1``

**Logical Grouping**
  Group related experiments in the same environment

**Version Control**
  Track changes to playbooks and configurations

**Documentation**
  Include clear descriptions and comments

Performance  
===========

**Optimize Images**
  Use small, high-contrast screenshots for matching

**Appropriate Timeouts**
  Balance speed vs. reliability with idle times

**Resource Management**
  Clean up old VMs and results regularly

**Parallel Execution**
  Run compatible experiments simultaneously

Security
========

**VM Isolation**  
  Keep test VMs isolated from production networks

**Sensitive Data**
  Don't include real passwords or personal data

**Clean Snapshots**
  Ensure base VM snapshots are clean and trusted

**Access Control**
  Limit access to experiment results and VMs

Troubleshooting
===============

When things go wrong:

1. **Check Logs**: ``adare run info <run_id> --logs``
2. **Screenshot Analysis**: Review captured screenshots
3. **VM Status**: ``adare vm list`` to check VM health
4. **Resource Usage**: Monitor disk space and memory
5. **Network Issues**: Verify MCP server connectivity

Getting Help
************

Resources for learning and support:

**Documentation**
  - :doc:`../cli-reference/index` - Complete command reference
  - :doc:`../architecture/index` - Technical architecture documentation

**Community**
  - `ADARE Web <https://adare.seclab-bonn.de/>`_ - Experiment sharing platform
  - `GitHub Issues <https://github.com/fkie-cad/Adare/issues>`_ - Bug reports and feature requests
  - `GitHub Discussions <https://github.com/fkie-cad/Adare/discussions>`_ - Community help

**Professional Support**
  Contact the development team for enterprise support and custom development.

What's Next?
************

Choose your learning path based on your role:

**New Users**
  Start with :doc:`projects` to understand the basics

**Forensic Researchers**  
  Focus on :doc:`playbooks` for automation and testing

**System Administrators**
  Emphasize :doc:`environments` and VM management

**Advanced Users**
  Explore :doc:`../advanced/index` for customization and performance tuning