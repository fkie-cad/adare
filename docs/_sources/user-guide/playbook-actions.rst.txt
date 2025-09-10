****************
Playbook Actions
****************

Complete reference for all playbook action types with detailed examples.

.. contents:: Quick Navigation
   :local:
   :depth: 2

GUI Actions
***********

Click Actions
=============

**Basic Clicking**

.. code-block:: yaml

   actions:
     # Click by image recognition
     - click:
         target:
           image: "save_button.png"
           confidence: 0.8
         description: "Click the Save button"
         
     # Click by text recognition  
     - click:
         target:
           text: "OK"
           case_sensitive: false
         description: "Click OK dialog button"
         
     # Click at specific coordinates
     - click:
         target:
           coordinates: [150, 300]
         description: "Click at specific location"

**Advanced Click Strategies**

.. code-block:: yaml

   actions:
     # Handle multiple matches
     - click:
         target:
           text: "Delete"
           strategy:
             SweepStrategy:
               index: 2            # Click 3rd "Delete" button found
         retry:
           attempts: 3
           delay: 1.0
           
     # Fallback options
     - click:
         target:
           text: "Save"
         fallback:
           - target: {text: "SAVE"}        # All caps
           - target: {text: "save"}        # Lowercase
           - target: {image: "save.png"}   # Image fallback

Mouse Actions
=============

.. code-block:: yaml

   actions:
     # Double-click
     - double_click:
         target:
           image: "file_icon.png"
         description: "Open file by double-clicking"
         
     # Right-click for context menu
     - right_click:
         target:
           text: "filename.txt"
         description: "Right-click for context menu"
         
     # Drag and drop
     - drag:
         from:
           coordinates: [100, 200]
         to:
           coordinates: [300, 400]  
         description: "Drag file to trash"

Keyboard Actions
================

**Text Input**

.. code-block:: yaml

   actions:
     # Type text
     - type:
         text: "forensic evidence data"
         description: "Enter evidence data"
         
     # Type with variables
     - type:
         text: "Case ID: {{case_id}}"
         description: "Enter case information"

**Keyboard Shortcuts**

.. code-block:: yaml

   actions:
     # Simple shortcuts
     - keyboard:
         combination: ["ctrl", "s"]
         description: "Save file with Ctrl+S"
         
     # Complex key sequences
     - keyboard:
         combination: ["ctrl", "shift", "del"]
         description: "Open delete confirmation"
         
     # Special keys
     - keyboard:
         key: "delete"
         description: "Press Delete key"
         
     # Function keys
     - keyboard:
         key: "f5"
         description: "Refresh view"

System Actions
**************

Command Execution
==================

**Basic Commands**

.. code-block:: yaml

   actions:
     # Simple commands
     - command:
         name: "Create Evidence Directory"
         command: "mkdir -p /evidence/{{case_id}}"
         shell: true
         
     # Commands with output capture
     - command:
         name: "List Files"
         command: "ls -la /evidence/"
         shell: true
         capture_output: true
         save_to: "file_listing"

**Advanced Command Options**

.. code-block:: yaml

   actions:
     # Admin/elevated commands
     - command:
         name: "Install Forensic Tool"
         command: "msi /i ForensicTool.msi /quiet"
         admin: true              # Windows: Run as Administrator
         shell: true
         timeout: 300
         
     # Multi-line commands
     - command:
         name: "Complex Setup"
         command: |
           cd /evidence
           mkdir case_{{case_id}}
           chmod 755 case_{{case_id}}
           echo "Case started: {{now()}}" > case_{{case_id}}/log.txt
         shell: true
         
     # Environment-specific commands
     - command:
         name: "Platform-specific cleanup"
         command: |
           {% if os_platform == "windows" %}
           del /Q C:\temp\*
           {% else %}
           rm -rf /tmp/*
           {% endif %}
         shell: true

File Operations
===============

.. code-block:: yaml

   actions:
     # File copy
     - file_copy:
         source: "/source/evidence.txt"
         destination: "/evidence/copied_evidence.txt"
         preserve_metadata: true
         
     # File move
     - file_move:
         source: "/tmp/temp_evidence.txt"
         destination: "/evidence/final_evidence.txt"
         
     # File deletion (for testing deletion artifacts)
     - file_delete:
         path: "/evidence/to_be_deleted.txt"
         secure: false            # Normal deletion (creates artifacts)

Flow Control Actions
********************

Conditional Logic
=================

.. code-block:: yaml

   actions:
     # Simple conditionals
     - conditional:
         condition: '{{os_platform}} == "windows"'
         actions:
           - command:
               command: 'del "{{temp_file}}"'
         else:
           - command:
               command: 'rm "{{temp_file}}"'
               
     # Multiple conditions
     - conditional:
         condition: '{{file_count}} > 0 and {{cleanup_enabled}}'
         actions:
           - command:
               command: 'echo "Cleaning up {{file_count}} files"'
           - loop:
               variable: "file"
               values: '{{files_to_clean}}'
               actions:
                 - file_delete:
                     path: '{{file}}'

Loops and Iteration
===================

.. code-block:: yaml

   actions:
     # Loop over list
     - loop:
         variable: "test_file"
         values: '{{test_files}}'
         actions:
           - command:
               command: 'echo "Processing {{test_file}}"'
           - click:
               target:
                 text: '{{test_file}}'
                 
     # Numeric loop
     - loop:
         variable: "i"
         range: [1, 5]            # Loop from 1 to 5
         actions:
           - command:
               command: 'touch /evidence/file_{{i}}.txt'
               
     # Loop with conditions
     - loop:
         variable: "item"
         values: '{{all_items}}'
         condition: '{{item.process == True}}'  # Only process certain items
         actions:
           - click:
               target:
                 text: '{{item.name}}'

Error Handling
==============

.. code-block:: yaml

   actions:
     # Try-catch blocks
     - try:
         actions:
           - click:
               target:
                 text: "Advanced Settings"
         catch:
           - log:
               message: "Advanced Settings not found, trying basic settings"
           - click:
               target:
                 text: "Settings"
         finally:
           - screenshot:
               name: "settings_opened"
               
     # Ignore errors and continue
     - try:
         actions:
           - command:
               command: "risky_command_that_might_fail"
         catch:
           - log:
               message: "Command failed, continuing anyway"

Timing Control Actions
**********************

Delays and Pauses
==================

.. code-block:: yaml

   actions:
     # Simple delays
     - idle:
         duration: 2.5
         description: "Wait for application to load"
         
     # Variable delays
     - idle:
         duration: '{{load_time}}'
         description: "Wait for configurable load time"

Wait Conditions
===============

.. code-block:: yaml

   actions:
     # Wait for file to exist
     - wait_for:
         condition: "file_exists"
         parameter:
           path: "/evidence/processing_complete.flag"
         timeout: 60
         description: "Wait for processing to complete"
         
     # Wait for GUI element
     - wait_for:
         condition: "element_visible"
         parameter:
           text: "Process Complete"
         timeout: 30
         description: "Wait for completion dialog"
         
     # Wait for process to stop
     - wait_for:
         condition: "process_not_running"
         parameter:
           process_name: "analyzer.exe"
         timeout: 120
         description: "Wait for analyzer to finish"

Evidence Collection Actions
***************************

Screenshots
===========

.. code-block:: yaml

   actions:
     # Full screen capture
     - screenshot:
         name: "evidence_screen_{{timestamp}}"
         description: "Capture current screen state"
         
     # Region capture
     - screenshot:
         name: "dialog_capture"  
         region: [100, 100, 400, 300]  # x, y, width, height
         description: "Capture dialog box only"
         
     # High-quality evidence capture
     - screenshot:
         name: "forensic_evidence"
         quality: 100
         format: "png"
         description: "High-quality evidence capture"

Timestamp Recording
===================

.. code-block:: yaml

   actions:
     # Simple timestamp
     - save_timestamp:
         variable: "deletion_start"
         description: "Record when file deletion began"
         
     # Timestamp with custom format
     - save_timestamp:
         variable: "evidence_time"
         format: "%Y-%m-%d %H:%M:%S.%f"
         timezone: "UTC"
         description: "Precise forensic timestamp"

System State Snapshots
======================

.. code-block:: yaml

   actions:
     # VM snapshot for forensic preservation
     - snapshot:
         name: "pre_incident_state"
         description: "Capture clean system state"
         
     # Registry export (Windows)
     - export_registry:
         key: "HKEY_CURRENT_USER\\Software"
         file: "/evidence/registry_before.reg"
         description: "Export user software registry"
         
     # Process list capture
     - capture_processes:
         file: "/evidence/processes_{{timestamp}}.csv"
         format: "csv"
         description: "Capture running processes"
         
     # Memory dump (advanced)
     - memory_dump:
         file: "/evidence/memory_{{timestamp}}.dmp"
         type: "full"
         description: "Full memory dump for analysis"

Block Actions
*************

Grouping Actions
================

.. code-block:: yaml

   actions:
     # Group related actions
     - block:
         name: "Evidence File Setup"
         description: "Prepare evidence files for testing"
         actions:
           - command: {command: "mkdir /evidence"}
           - command: {command: "touch /evidence/test.txt"}
           - test: file_created_successfully
           
     # Nested blocks
     - block:
         name: "File Deletion Test"
         actions:
           - block:
               name: "Select File"
               actions:
                 - click: {target: {text: "test.txt"}}
                 - screenshot: {name: "file_selected"}
           - block:
               name: "Delete File"  
               actions:
                 - keyboard: {combination: ["delete"]}
                 - save_timestamp: {variable: "deletion_time"}

Conditional Blocks
==================

.. code-block:: yaml

   actions:
     # Conditional execution of entire blocks
     - conditional:
         condition: '{{run_cleanup}}'
         actions:
           - block:
               name: "Cleanup Operations"
               actions:
                 - command: {command: "rm -rf /tmp/test*"}
                 - command: {command: "echo 'Cleanup complete'"}

Advanced Action Patterns
*************************

Retry Mechanisms
================

.. code-block:: yaml

   actions:
     # Action-level retry
     - click:
         target:
           image: "unstable_button.png"
         retry:
           attempts: 5
           delay: 2.0
           backoff: 1.5        # Increase delay by 50% each retry
           
     # Block-level retry
     - block:
         name: "Flaky Operation"
         retry:
           attempts: 3
           delay: 1.0
         actions:
           - click: {target: {text: "Submit"}}
           - wait_for: {condition: "element_visible", parameter: {text: "Success"}}

Parallel Execution
==================

.. code-block:: yaml

   actions:
     # Run actions in parallel (use with caution)
     - parallel:
         actions:
           - command: {command: "long_running_process_1"}
           - command: {command: "long_running_process_2"}
           - command: {command: "long_running_process_3"}
         timeout: 300
         
     # Wait for all to complete
     - wait_for:
         condition: "all_processes_complete"
         timeout: 60

Complex Forensic Scenarios
===========================

**File System Timeline Analysis**

.. code-block:: yaml

   actions:
     # Create baseline
     - snapshot: {name: "baseline"}
     - save_timestamp: {variable: "baseline_time"}
     
     # Perform actions that create artifacts
     - block:
         name: "Evidence Creation Sequence"
         actions:
           - command: {command: 'echo "evidence" > /tmp/critical.txt'}
           - save_timestamp: {variable: "file_created"}
           - idle: {duration: 1.0}
           - command: {command: 'chmod 755 /tmp/critical.txt'}
           - save_timestamp: {variable: "permissions_changed"}
           - idle: {duration: 1.0}
           - command: {command: 'mv /tmp/critical.txt /evidence/'}
           - save_timestamp: {variable: "file_moved"}
     
     # Capture final state
     - snapshot: {name: "post_evidence"}
     - export_filesystem_timeline: {file: "/evidence/timeline.csv"}

Best Practices
**************

Action Naming
=============

.. code-block:: yaml

   # Good: Clear, descriptive names
   actions:
     - click:
         target: {text: "Delete"}
         description: "Delete selected evidence file"
         
     - command:
         name: "Export Registry Evidence"
         command: "reg export HKCU\\Software evidence_registry.reg"

   # Bad: Generic, unclear names  
   actions:
     - click: {target: {text: "Delete"}}  # No description
     - command: {command: "reg export"}   # No name

Error Handling Strategy
=======================

.. code-block:: yaml

   settings:
     on_error: "continue"        # or "stop", "retry"
     
   actions:
     # Always include error handling for critical operations
     - try:
         actions:
           - click: {target: {image: "critical_button.png"}}
         catch:
           - log: {message: "Critical button not found"}
           - screenshot: {name: "error_state"}
           - fail: {message: "Cannot proceed without critical button"}

Performance Optimization
=========================

.. code-block:: yaml

   # Minimize unnecessary delays
   settings:
     idle: 0.5              # Reduce default delays
     
   actions:
     # Use efficient selectors
     - click:
         target:
           coordinates: [150, 300]  # Fastest - direct coordinates
         # vs
         target:
           image: "button.png"      # Slower - image matching
         # vs  
         target:
           text: "Button"           # Slowest - OCR required

Next Steps
**********

**Related Documentation:**
- **Playbook Guide**: :doc:`playbooks` - Basic playbook structure and concepts
- **Variable Reference**: :doc:`playbook-variables` - Variable types and filters  
- **Test Functions**: :doc:`../advanced/testfunctions` - Custom validation functions