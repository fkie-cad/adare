**************
Key Concepts
**************

Understanding these core concepts will help you work effectively with ADARE and create better forensic experiments.

Forensic Artifacts
******************

**What are forensic artifacts?**

Forensic artifacts are digital traces left behind by user activities or system processes. In digital forensics, these artifacts provide evidence of what happened on a system.

Common Artifact Types
=====================

**File System Artifacts**
  - File creation, modification, deletion timestamps
  - Temporary files and caches
  - Trash/Recycle bin contents
  - File metadata and attributes

**Registry Artifacts** (Windows)
  - Application installation records
  - User activity traces
  - System configuration changes
  - Recent document lists

**Browser Artifacts**
  - Browsing history and bookmarks
  - Cookies and session data
  - Downloads and form data
  - Cache files

**System Artifacts**
  - Event logs and audit trails
  - Process execution evidence
  - Network connection logs
  - User login/logout records

Why ADARE Matters for Artifacts
===============================

Traditional forensic analysis is manual and time-consuming. ADARE automates:

- **Artifact Creation**: Simulate user actions that create artifacts
- **Artifact Validation**: Verify artifacts exist and contain expected data
- **Cross-Platform Testing**: Test how artifacts behave across OS versions
- **Reproducibility**: Ensure findings can be replicated by others

ADARE Architecture
******************

Understanding ADARE's architecture helps you design better experiments.

Components Overview
===================

.. code-block:: text

   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
   │   Host System   │    │  Virtual Machine │    │   MCP Server    │
   │                 │    │                 │    │                 │
   │ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
   │ │    adare    │◄┼────┼►│   adarevm   │◄┼────┼►│ GUI Analysis│ │
   │ │   (client)  │ │    │ │  (agent)    │ │    │ │   Server    │ │
   │ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
   │                 │    │                 │    │                 │
   │ • Project Mgmt  │    │ • Playbook Exec │    │ • Screenshot    │
   │ • VM Control    │    │ • Test Runner   │    │ • Image Match   │
   │ • Result Store  │    │ • Artifact Scan │    │ • Text Extract  │
   └─────────────────┘    └─────────────────┘    └─────────────────┘

**adare (Host Client)**
  - Manages projects, environments, experiments
  - Controls virtual machine lifecycle  
  - Stores and analyzes results
  - Provides CLI and web interfaces

**adarevm (VM Agent)**
  - Runs inside virtual machines
  - Executes playbook actions
  - Performs forensic tests
  - Collects artifacts and evidence

**MCP Server (GUI Automation)**  
  - Analyzes screenshots for GUI elements
  - Matches images and text on screen
  - Provides coordinates for clicking
  - Handles OCR and computer vision

Data Flow
=========

1. **Host** starts VM and loads playbook
2. **VM Agent** receives playbook and begins execution
3. **Actions** are performed (clicks, typing, commands)
4. **Screenshots** sent to MCP Server for analysis
5. **Tests** validate artifacts and system state
6. **Results** collected and sent back to host
7. **Reports** generated with forensic evidence

Projects, Environments & Experiments
************************************

ADARE uses a hierarchical organization system:

Project Hierarchy
=================

.. code-block:: text

   Project (e.g., "Windows Forensics Research")
   │
   ├── Environment 1: "Windows 10 Pro"
   │   ├── Experiment A: "Registry Analysis"
   │   ├── Experiment B: "Browser Artifacts" 
   │   └── Experiment C: "File Deletion"
   │
   ├── Environment 2: "Windows 11 Home"
   │   ├── Experiment A: "Registry Analysis"
   │   ├── Experiment B: "Browser Artifacts"
   │   └── Experiment D: "USB Device Detection"
   │
   └── Shared Resources
       ├── Custom test functions
       ├── Common utilities
       └── Reference images

**Projects**
  Top-level containers for related forensic research. Examples:
  
  - "Mobile Device Forensics"
  - "Network Artifact Analysis" 
  - "Malware Behavior Study"

**Environments**
  Specific VM configurations for testing. Examples:
  
  - "iOS 16.1 Jailbroken"
  - "Ubuntu 22.04 Server"
  - "Windows 11 with Office 365"

**Experiments** 
  Individual forensic tests or scenarios. Examples:
  
  - "WhatsApp Message Deletion"
  - "SSH Key Extraction"
  - "Word Document Metadata Analysis"

Why This Structure?
===================

**Reusability**
  Run the same experiment across multiple OS versions

**Organization** 
  Logically group related forensic research

**Sharing**
  Share specific experiments or entire project templates

**Scalability**
  Manage hundreds of experiments across dozens of environments

Playbooks and Actions
*********************

Playbooks are YAML files that define automated forensic scenarios.

Playbook Structure
==================

.. code-block:: yaml

   # Experiment configuration
   settings:
     idle: 1.0              # Default pause between actions
     timeout: 300           # Maximum experiment duration
     
   # Reusable variables  
   variables:
     username: "forensics"
     evidence_file: "/home/{{username}}/evidence.txt"
     
   # Validation tests
   tests:
     - name: file_deleted
       function: file_does_not_exist
       parameter:
         dst: '{{evidence_file}}'
   
   # Automation sequence
   actions:
     - command: 
         command: "touch {{evidence_file}}"
     - click:
         target:
           text: "evidence.txt"
     - keyboard:
         combination: ["delete"]
     - test: file_deleted

Action Types
============

**GUI Actions**
  - ``click``: Mouse clicks on images or text
  - ``double_click``: Double-click actions
  - ``right_click``: Context menu interactions
  - ``type``: Keyboard text input
  - ``keyboard``: Key combinations and shortcuts

**System Actions**
  - ``command``: Execute shell commands
  - ``file_operation``: File/directory operations
  - ``registry``: Windows registry modifications

**Test Actions**
  - ``test``: Execute validation tests
  - ``assert``: Inline assertions

**Flow Control**
  - ``idle``: Pause execution
  - ``block``: Group related actions
  - ``conditional``: Execute based on conditions
  - ``loop``: Repeat actions

**Evidence Collection**
  - ``screenshot``: Capture screen images
  - ``save_timestamp``: Record precise timing
  - ``snapshot``: VM state snapshots

Variables and Templating
========================

Use Jinja2 templating for dynamic playbooks:

.. code-block:: yaml

   variables:
     os_type: "windows"
     username: "admin"
     test_files:
       - "document1.pdf"
       - "spreadsheet.xlsx"
       - "presentation.pptx"
   
   actions:
     # Conditional logic
     - conditional:
         condition: '{{os_type}} == "windows"'
         actions:
           - command: 'del "{{item}}"'
         
     # Loop over files  
     - loop:
         variable: "item"
         values: '{{test_files}}'
         actions:
           - click:
               target:
                 text: '{{item}}'

Tests and Validation
********************

Tests verify that forensic artifacts behave as expected.

Test Functions
==============

ADARE provides built-in test functions:

**File System Tests**
  - ``file_exists`` / ``file_does_not_exist``
  - ``directory_exists`` / ``directory_does_not_exist``
  - ``file_content_equals`` / ``file_content_contains``
  - ``file_size_equals`` / ``file_modified_since``

**Registry Tests** (Windows)
  - ``registry_key_exists`` / ``registry_key_does_not_exist``
  - ``registry_value_equals`` / ``registry_value_contains``
  - ``registry_key_has_subkeys``

**System Tests**
  - ``process_running`` / ``process_not_running``
  - ``service_running`` / ``service_stopped``
  - ``port_open`` / ``port_closed``

**Forensic Tests**
  - ``artifact_timestamp_within`` 
  - ``hash_matches``
  - ``metadata_contains``

Test Parameters
===============

Tests use parameters to specify what to validate:

.. code-block:: yaml

   tests:
     - name: check_file_timestamp
       description: "Verify file was modified recently"
       function: file_modified_since
       parameter:
         dst: "/evidence/important.txt"
         since: "2025-01-01 00:00:00"
         
     - name: verify_hash
       description: "Confirm file integrity"  
       function: hash_matches
       parameter:
         file: "/evidence/critical.bin"
         algorithm: "sha256"
         expected: "abc123def456..."

Custom Test Functions
=====================

Create specialized tests for your research:

.. code-block:: python

   # In testfunctions/custom/my_tests.py
   def browser_history_contains_url(url: str, browser: str = "chrome") -> bool:
       """Check if browser history contains specific URL"""
       # Implementation here
       return found
       
   def registry_mru_contains_file(filepath: str) -> bool:
       """Check if Windows MRU contains file reference"""
       # Implementation here  
       return found

GUI Automation Concepts
***********************

Understanding GUI automation helps create reliable experiments.

Target Selection
================

ADARE can find GUI elements using multiple strategies:

**Image Matching**
  Match visual elements using reference screenshots:
  
  .. code-block:: yaml
  
     click:
       target:
         image: "firefox_icon.png"
         confidence: 0.8

**Text Recognition**
  Find elements by their visible text:
  
  .. code-block:: yaml
  
     click:
       target:
         text: "File"
         case_sensitive: false

**Coordinate-Based** 
  Click at specific screen coordinates:
  
  .. code-block:: yaml
  
     click:
       target:
         coordinates: [100, 200]

**Smart Strategies**
  Handle multiple matches intelligently:
  
  .. code-block:: yaml
  
     click:
       target:
         text: "Delete"
         strategy:
           SweepStrategy:
             index: 2  # Click the 3rd "Delete" button found

Reliability Best Practices
===========================

**Use Multiple Approaches**
  Combine image and text matching for robustness

**Add Appropriate Delays**
  Allow time for GUI elements to load

**Handle Failures Gracefully**
  Include retry logic and error handling

**Test Across Resolutions**  
  Verify experiments work at different screen sizes

**Screenshot Everything**
  Visual evidence is crucial for forensic work

VM and Snapshot Management
**************************

Understanding VM management optimizes experiment performance.

VM Lifecycle
============

1. **Base VM Creation**: Clean system state
2. **Environment Setup**: Install required software
3. **Base Snapshot**: Save clean, configured state  
4. **Experiment Execution**: Run forensic tests
5. **Results Collection**: Gather artifacts and evidence
6. **VM Reset**: Return to base snapshot
7. **Cleanup**: Remove temporary data

Snapshot Strategy
=================

**Base Snapshots**
  Clean system with required software installed

**Checkpoint Snapshots**
  Key points during experiment execution

**Evidence Snapshots**  
  Preserve system state for later analysis

**Performance Snapshots**
  Optimize for repeated experiment runs

Storage Management
==================

VMs and results consume significant storage:

.. code-block:: bash

   # Monitor disk usage
   adare vm list --storage
   
   # Clean up old results
   adare vm clear environment <env_id> --older-than 30d
   
   # Compress snapshots
   adare vm compress <vm_id>

Next Steps
**********

With these concepts mastered, you're ready to:

- **Create Complex Experiments**: :doc:`../user-guide/experiments`
- **Master the CLI**: :doc:`../cli-reference/index` 
- **Understand Architecture**: :doc:`../architecture/index`
- **Advanced Techniques**: :doc:`../advanced/index`