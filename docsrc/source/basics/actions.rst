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
     auto_pull_on_test_failure: true # Automatically pull files on test failure for analysis

     # Forensic features
     collect_system_info: true      # Capture VM system info (default: true)
     forensic_logging: true         # Generate YAML audit logs (default: true)
     enable_filesystem_diff: true   # Auto snapshots at start/end (default: true)

     # GUI automation mode (QEMU only)
     gui_execution_mode: 'auto'     # 'auto' (choose best), 'agent' (VM-based),
                                    # 'host' (CV server)

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

Automatic Variables
===================

ADARE provides automatic variables based on VM configuration (no declaration needed):

**User Variables:**

- ``adare_username`` - Target VM username
- ``adare_user_home`` - User home directory (/home/user or C:/Users/user)
- ``adare_user_documents`` - Documents folder
- ``adare_user_desktop`` - Desktop folder
- ``adare_user_downloads`` - Downloads folder

**System Variables:**

- ``adare_os`` - Operating system ('windows' or 'linux')
- ``adare_temp_dir`` - Temporary directory (/tmp or C:/Windows/Temp)
- ``adare_system_drive`` - Windows system drive (C:)
- ``adare_root_dir`` - Linux root directory (/)

**Shared Mount Variables:**

- ``adare_shared`` - Experiment-level shared directory mount
- ``adare_shared_data`` - Experiment shared data mount
- ``adare_shared_tools`` - Experiment shared tools mount
- ``adare_project_shared`` - Project-level shared directory mount
- ``adare_project_shared_data`` - Project shared data mount
- ``adare_project_shared_tools`` - Project shared tools mount
- ``adare_run_dir`` - Run directory mount

These variables can be overridden by defining them in the ``variables`` section.

Variable Scope & Persistence
=============================

Variables created in loops and blocks persist to parent scope:

.. code-block:: yaml

   actions:
     - loop:
         times: 3
         actions:
           - save_variable:
               name: "var_{{index}}"
               value: "value_{{index}}"

     # Variables var_0, var_1, var_2 still accessible
     - command:
         command: "echo '{{var_0}} {{var_1}} {{var_2}}'"

**Dynamic Variable Naming:**

.. code-block:: yaml

   - loop:
         items: ["alpha", "beta", "gamma"]
         item_var: name
         actions:
           - save_timestamp:
               variable: "timestamp_{{name}}"  # Creates timestamp_alpha, etc.

Variable Filters
================

.. warning::
   **Variable Filter Validation Limitation**

   Variable filters currently have **limited validation** during playbook parsing. Filter syntax errors or incorrect parameters may only be discovered during experiment execution, potentially causing failures mid-experiment.

   **Recommendation**: Test playbooks thoroughly in test mode (the default) before using ``--production`` flag

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

**Auto-Pull on Test Failure**

When ``auto_pull_on_test_failure`` is enabled (default: ``true``), ADARE automatically pulls all files mentioned in pull actions when any test fails. This provides valuable forensic data for failure analysis:

.. code-block:: yaml

   settings:
     auto_pull_on_test_failure: true  # Pull files for failure analysis (default)
     continue_on_test_failure: true   # Continue after test failures

   actions:
     - command:
         command: "echo 'log entry' > /var/log/app.log"
     - pull:
         src: "/var/log/app.log"
         description: "Application logs"
     - test: validate_log_content

If ``validate_log_content`` fails, ADARE will automatically pull ``/var/log/app.log`` to the artifacts directory for analysis, even if the explicit pull action hasn't been reached yet.

Key behaviors:

* Auto-pull only triggers once per experiment execution
* Files are pulled with variable resolution applied
* Failed auto-pulls are logged but don't cause experiment failure
* Auto-pulled files are stored in the standard artifacts directory

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

Custom YAML Tags
================

Use custom tags in test parameters for precise matching:

.. code-block:: yaml

   tests:
     - name: exact_match
       function: csv.line_matches
       parameter:
         pattern: [!s "exact text"]  # Exact string match

     - name: regex_match
       function: csv.line_matches
       parameter:
         pattern: [!re "^[a-z]+$"]   # Regex pattern

     - name: path_match
       function: file_exists
       parameter:
         dst: !path "/home/user"     # Path comparison

     - name: wildcard_match
       function: json.value_matches
       parameter:
         value: !reALL                # Match any value

     - name: timestamp_match
       function: file_modified_time_matches
       parameter:
         timestamp: !timestamp
           timestamp: "{{deletion_time}}"
           tolerance: 5
           timezone: "UTC"

**Available Tags:**

- ``!s`` - Exact string match
- ``!re <pattern>`` - Regex pattern match
- ``!path`` - Path exact match
- ``!reALL`` - Wildcard (match any value)
- ``!timestamp {timestamp, tolerance, timezone, format}`` - Timestamp with tolerance

Actions Reference
*****************

For detailed action documentation, see :doc:`actions/index`.

This section provides a quick overview. For comprehensive documentation of all actions organized by category, refer to the full actions reference.

Quick Action Overview
=====================

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Action Type
     - Description
   * - :doc:`actions/gui/index`
     - Click, keyboard input, drag-and-drop, scrolling
   * - :doc:`actions/command/index`
     - Shell command execution with output capture
   * - :doc:`actions/test/index`
     - Execute forensic validation tests
   * - :doc:`actions/flow/index`
     - Delays, loops, conditional execution, branching
   * - :doc:`actions/variable/index`
     - Save timestamps and computed values
   * - :doc:`actions/file/index`
     - File transfer and filesystem tracking
   * - :doc:`actions/debug/index`
     - Interactive pauses and screenshots

**For complete action reference with all parameters and examples, see:**

.. toctree::
   :maxdepth: 1

   actions/index

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