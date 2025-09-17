*******
Actions
*******

Playbooks are the heart of ADARE experiments - YAML files that define automated forensic scenarios through GUI actions, system commands, and validation tests. This comprehensive guide covers everything you need to create effective playbooks.

Getting Started
***************

Every playbook follows this structure:

.. code-block:: yaml

   # Global experiment settings
   settings:
     idle: 1.0              # Default pause between actions
     timeout: 300           # Maximum experiment duration
     screenshot:
       format: "png"
       quality: 95

   # Reusable variables with templating
   variables:
     username:
       type: string
       value: "adare"
       description: "System username"

     evidence_file:
       type: path
       value: "/home/{{username}}/evidence.txt"
       description: "File path for evidence"

   # Validation tests for forensic artifacts
   tests:
     - name: file_exists_check
       description: "Verify evidence file was created"
       function: file_exists
       parameter:
         dst: '{{evidence_file}}'

   # Automation sequence
   actions:
     - command:
         name: "Create Evidence"
         command: "touch {{evidence_file}}"
     - test: file_exists_check

Required Sections
=================

**settings** (Optional)
  Global configuration for the experiment

**variables** (Optional)
  Reusable values with templating support

**tests** (Required)
  Forensic validation definitions

**actions** (Required)
  Sequence of automated interactions

Settings Configuration
**********************

Global Settings
===============

Configure experiment-wide behavior:

.. code-block:: yaml

   settings:
     # Timing configuration
     idle: 1.5                    # Default pause between actions (seconds)
     timeout: 600                 # Max experiment duration (seconds)

     # Screenshot settings
     screenshot:
       format: "png"              # or "jpg"
       quality: 95                # 1-100 (PNG) or 1-100 (JPG)
       on_action: true            # Screenshot after each action
       on_error: true             # Screenshot on failures

     # Test failure handling
     continue_on_test_failure: true # Continue experiment even if tests fail

     # Retry behavior
     retry:
       attempts: 3                # Retry failed actions
       delay: 2.0                 # Delay between retries

     # GUI automation settings
     gui:
       click_delay: 0.1           # Delay after clicks
       type_delay: 0.05           # Delay between keystrokes

     # OCR configuration
     ocr:
       language: "eng"            # Tesseract language code
       confidence: 0.8            # Text matching confidence

     # Performance settings
     performance:
       parallel_tests: false      # Run tests in parallel
       cache_screenshots: true    # Cache images for speed

Platform-Specific Settings
===========================

.. code-block:: yaml

   settings:
     # Windows-specific
     windows:
       disable_animations: true   # Speed up GUI
       use_win32_api: true       # Native Windows APIs

     # Linux-specific
     linux:
       display: ":0"             # X11 display
       window_manager: "gnome"   # Desktop environment

Variables and Templating
************************

Variable Types
==============

Define typed variables for better validation:

.. code-block:: yaml

   variables:
     # String variables
     username:
       type: string
       value: "forensics"
       description: "System username for testing"

     # Path variables (with validation)
     evidence_dir:
       type: path
       value: "/home/{{username}}/evidence"
       description: "Directory for storing evidence"

     # Integer variables
     file_count:
       type: integer
       value: 5
       description: "Number of test files to create"

     # Boolean variables
     cleanup_after:
       type: boolean
       value: true
       description: "Clean up test files after experiment"

     # List variables
     test_files:
       type: list
       value:
         - "document1.pdf"
         - "spreadsheet.xlsx"
         - "presentation.pptx"
       description: "Files to test deletion behavior"

Template Syntax
===============

ADARE uses Jinja2 templating for dynamic content:

.. code-block:: yaml

   variables:
     base_path: "/home/adare"
     username: "forensics"
     case_id: "CASE-2025-001"

   actions:
     # Basic variable substitution
     - command:
         command: "mkdir {{base_path}}/{{case_id}}"

Variable Filters
================

.. warning::
   **Variable Filter Validation Limitation**

   Variable filters currently have **limited validation** during playbook parsing. Filter syntax errors or incorrect parameters may only be discovered during experiment execution, potentially causing failures mid-experiment.

   **Recommendation**: Always test playbooks with filters in development mode first: ``adare experiment run <name> -e <env> --test``

ADARE supports powerful filters for data transformation:

**Date and Time Filters**

.. code-block:: yaml

   variables:
     current_time:
       type: timestamp
       value: "{{ now() }}"

   tests:
     - name: check_modification_time
       function: file_modified_since
       parameter:
         dst: "/evidence/test.txt"
         # Format timestamp and add tolerance for timing variations
         since: "{{ current_time | format('%Y-%m-%d %H:%M:%S') | tolerance(10, -10) }}"

**Available Date/Time Filters:**

- ``format(pattern)``: Format timestamp using strftime patterns
- ``tolerance(+seconds, -seconds)``: Add time range for flexible matching
- ``timezone(tz)``: Convert to specified timezone (e.g., "UTC", "America/New_York")
- ``localtime(bool)``: Interpret timestamp as local time if true

.. code-block:: yaml

   variables:
     deletion_time: "2025-09-10T10:30:00"

   actions:
     - save_timestamp:
         variable: actual_deletion

   tests:
     - name: verify_deletion_time
       function: timestamp_within_range
       parameter:
         actual: "{{ actual_deletion | format('%Y-%m-%d %H:%M:%S') }}"
         expected: "{{ deletion_time | format('%Y-%m-%d %H:%M:%S') | tolerance(5, -5) }}"

Test Definitions
****************

Basic Test Structure
====================

.. code-block:: yaml

   tests:
     - name: file_created_successfully
       description: "Verify the evidence file was created"
       function: file_exists
       parameter:
         dst: "/evidence/test.txt"

Test Failure Handling
======================

**Expect Test to Fail**

Use ``expect_to_fail`` when testing negative conditions:

.. code-block:: yaml

   tests:
     - name: file_should_not_exist
       description: "Verify file was deleted completely"
       function: file_exists
       expect_to_fail: true    # Test passes if function fails
       parameter:
         dst: "/evidence/deleted.txt"

     - name: invalid_registry_key
       description: "Confirm registry key doesn't exist"
       function: windows.registry_key_exists
       expect_to_fail: true
       parameter:
         key: "HKEY_CURRENT_USER\\Software\\NonExistentApp"

**Continue on Test Failure**

Configure behavior when tests fail:

.. code-block:: yaml

   settings:
     continue_on_test_failure: true  # Don't stop experiment on test failures

   tests:
     - name: optional_check
       description: "This test might fail, but experiment continues"
       function: file_exists
       parameter:
         dst: "/optional/file.txt"

Actions Reference
*****************

GUI Actions
===========

**Click Actions**

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

     # Advanced click with strategy
     - click:
         target:
           text: "Delete"
           strategy:
             SweepStrategy:
               index: 2            # Click 3rd "Delete" button found
         retry:
           attempts: 3
           delay: 1.0

**Keyboard Actions**

.. code-block:: yaml

   actions:
     # Type text
     - type:
         text: "forensic evidence data"
         description: "Enter evidence data"

     # Keyboard shortcuts
     - keyboard:
         combination: ["ctrl", "s"]
         description: "Save file with Ctrl+S"

     # Complex key sequences
     - keyboard:
         combination: ["alt", "f4"]
         description: "Close application"

     # Special keys
     - keyboard:
         key: "delete"
         description: "Press Delete key"

     # Function keys
     - keyboard:
         key: "f5"
         description: "Refresh view"

     # Arrow keys
     - keyboard:
         key: "arrow_down"
         description: "Navigate down"

     # Other special keys
     - keyboard:
         key: "escape"
         description: "Press Escape"

     - keyboard:
         key: "enter"
         description: "Press Enter"

     - keyboard:
         key: "tab"
         description: "Press Tab"

     - keyboard:
         key: "space"
         description: "Press Space"

**Available Special Keys:**

- Function keys: ``f1``, ``f2``, ... ``f12``
- Arrow keys: ``arrow_up``, ``arrow_down``, ``arrow_left``, ``arrow_right``
- Navigation: ``home``, ``end``, ``page_up``, ``page_down``
- Editing: ``insert``, ``delete``, ``backspace``
- System: ``escape``, ``enter``, ``tab``, ``space``
- Modifiers: ``ctrl``, ``alt``, ``shift``, ``cmd`` (Mac)

**Mouse Actions**

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

System Actions
==============

**Command Execution**

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

     # Admin/elevated commands
     - command:
         name: "Install Forensic Tool"
         command: "msi /i ForensicTool.msi /quiet"
         admin: true              # Windows: Run as Administrator
         shell: true

     # Multi-line commands
     - command:
         name: "Complex Setup"
         command: |
           cd /evidence
           mkdir case_{{case_id}}
           chmod 755 case_{{case_id}}
           echo "Case started: {{now()}}" > case_{{case_id}}/log.txt
         shell: true

**File Operations**

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

Timing Control Actions
======================

**Delays and Pauses**

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

**Interactive Pauses**

.. code-block:: yaml
     - pause:
         name: "Configuration Check"


Evidence Collection Actions
===========================

**Screenshots**

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

**Timestamp Recording**

.. code-block:: yaml

   actions:
     # Simple timestamp
     - save_timestamp:
         variable: "deletion_start"
         description: "Record when file deletion began"


Block Actions
=============

**Grouping Actions**

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

Best Practices
**************

Playbook Organization
=====================

**Group Related Actions**

.. code-block:: yaml

   actions:
     # Setup phase
     - block:
         name: "Evidence File Setup"
         actions:
           - command: {command: "mkdir /evidence"}
           - command: {command: "touch /evidence/test.txt"}
           - test: file_created_successfully

     # Execution phase
     - block:
         name: "File Deletion Test"
         actions:
           - click: {target: {text: "test.txt"}}
           - keyboard: {combination: ["delete"]}
           - save_timestamp: {variable: "deletion_time"}

     # Validation phase
     - block:
         name: "Artifact Verification"
         actions:
           - test: file_deleted_from_original_location
           - test: file_exists_in_trash_bin
           - test: trash_metadata_correct

Troubleshooting
***************

When experiments fail or behave unexpectedly, detailed logs can help identify issues:

Run Directory Logs
==================

Each experiment run creates a dedicated log directory:

**Location:** ``<project>/runs/<experiment_name>/<timestamp>/logs/``

**adare.log**
  Main ADARE application log containing experiment setup, VM lifecycle, integrity checks, and detailed error messages

**adarevm.log**
  Guest VM agent logs with GUI action execution, target detection results, and WebSocket communication status

**mcp_gui.log**
  Computer vision server logs with screenshot analysis, target recognition, and GUI element detection

These logs are created automatically when running experiments (controlled by ``--no-runlog`` flag).