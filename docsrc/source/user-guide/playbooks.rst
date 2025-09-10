***************
Playbook Guide
***************

Playbooks are the heart of ADARE experiments - YAML files that define automated forensic scenarios through GUI actions, system commands, and validation tests.

.. contents:: Quick Navigation
   :local:
   :depth: 2

Playbook Structure
******************

Basic Template
==============

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
         
     # Conditional templating
     - command:
         command: "{% if cleanup_after %}rm -rf /tmp/test*{% endif %}"
         
     # Loop templating
     - command:
         command: |
           {% for file in test_files %}
           touch "{{base_path}}/{{file}}"
           {% endfor %}

Variable Filters
===============

.. warning::
   **Variable Filter Validation Limitation**
   
   Variable filters currently have **limited validation** during playbook parsing. Filter syntax errors or incorrect parameters may only be discovered during experiment execution, potentially causing failures mid-experiment. 
   
   **Recommendation**: Always test playbooks with filters in development mode first: ``adare experiment develop <name> -e <env>``

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
- ``add_seconds(n)``: Add/subtract seconds from timestamp
- ``add_minutes(n)``: Add/subtract minutes from timestamp
- ``add_hours(n)``: Add/subtract hours from timestamp

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

**String Filters**

.. code-block:: yaml

   variables:
     file_name: "Evidence Document"
     
   actions:
     - command:
         # Convert to lowercase, replace spaces with underscores
         command: "touch {{file_name | lower | replace(' ', '_')}}.txt"

**Available String Filters:**

- ``upper``: Convert to uppercase
- ``lower``: Convert to lowercase  
- ``title``: Title case conversion
- ``replace(old, new)``: Replace text
- ``trim``: Remove whitespace
- ``truncate(length)``: Limit string length

**Path Filters**

.. code-block:: yaml

   variables:
     evidence_file: "/home/user/evidence/case001/document.pdf"
     
   tests:
     - name: check_parent_directory
       function: directory_exists
       parameter:
         # Extract directory path
         dst: "{{ evidence_file | dirname }}"
         
     - name: check_file_extension
       function: file_extension_equals
       parameter:
         dst: "{{ evidence_file }}"
         # Extract file extension
         expected: "{{ evidence_file | extension }}"

**Available Path Filters:**

- ``dirname``: Extract directory path
- ``basename``: Extract filename only
- ``extension``: Extract file extension
- ``absolute``: Convert to absolute path
- ``normalize``: Normalize path separators

**Forensic-Specific Filters**

.. code-block:: yaml

   variables:
     evidence_hash: "abc123def456"
     registry_path: "HKEY_CURRENT_USER\\Software\\TestApp"
     
   tests:
     - name: verify_hash_format
       function: hash_format_valid
       parameter:
         # Validate hash format and convert to uppercase
         hash: "{{ evidence_hash | hash_format('sha256') | upper }}"
         
     - name: check_registry_key
       function: registry_key_exists  
       parameter:
         # Convert registry path format
         key: "{{ registry_path | registry_normalize }}"

**Available Forensic Filters:**

- ``hash_format(algorithm)``: Validate and format hash values
- ``registry_normalize``: Normalize registry key paths
- ``file_size_human``: Convert bytes to human-readable format
- ``timestamp_unix``: Convert to Unix timestamp
- ``base64_encode/decode``: Base64 encoding operations

**Filter Chaining**

Combine multiple filters for complex transformations:

.. code-block:: yaml

   variables:
     raw_filename: "  Evidence Document #1.PDF  "
     
   actions:
     - command:
         # Chain: trim whitespace → lowercase → replace spaces → replace # → add extension
         command: "touch {{ raw_filename | trim | lower | replace(' ', '_') | replace('#', 'num') | replace('.pdf', '') }}.txt"

**Conditional Filters**

Use filters with conditions:

.. code-block:: yaml

   variables:
     os_type: "windows"
     file_path: "/evidence/test.txt"
     
   actions:
     - command:
         # Apply different filters based on OS
         command: |
           {% if os_type == "windows" %}
           type "{{ file_path | replace('/', '\\') }}"
           {% else %}
           cat "{{ file_path }}"
           {% endif %}

Test Definitions
****************

Test Structure
==============

Tests validate forensic artifacts and system state:

.. code-block:: yaml

   tests:
     - name: unique_test_name
       description: "Human-readable test description"
       function: test_function_name
       parameter:
         param1: "value1"
         param2: "{{variable}}"
       timeout: 30                    # Test-specific timeout
       critical: true                 # Fail experiment if test fails
       retry:
         attempts: 3
         delay: 1.0

Built-in Test Functions
=======================

**File System Tests**

.. code-block:: yaml

   tests:
     # File existence
     - name: evidence_exists
       function: file_exists
       parameter:
         dst: "/evidence/case001.txt"
         
     - name: temp_cleaned
       function: file_does_not_exist  
       parameter:
         dst: "/tmp/sensitive_data.txt"
         
     # File content validation
     - name: verify_evidence_content
       function: file_content_contains
       parameter:
         dst: "/evidence/report.txt"
         content: "Case ID: 2025-001"
         
     # File metadata
     - name: check_creation_time
       function: file_created_after
       parameter:
         dst: "/evidence/artifact.log"
         timestamp: "{{ experiment_start | format('%Y-%m-%d %H:%M:%S') }}"

**Registry Tests (Windows)**

.. code-block:: yaml

   tests:
     # Registry key existence
     - name: app_key_created
       function: registry_key_exists
       parameter:
         key: "HKEY_CURRENT_USER\\Software\\TestApp"
         
     # Registry value validation
     - name: version_stored
       function: registry_value_equals
       parameter:
         key: "HKEY_CURRENT_USER\\Software\\TestApp"
         value_name: "Version"
         expected: "1.0.0"
         
     # Registry structure validation
     - name: uninstall_entry_complete
       function: registry_key_has_values
       parameter:
         key: "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TestApp"
         required_values: ["DisplayName", "InstallLocation", "UninstallString"]

**Process and System Tests**

.. code-block:: yaml

   tests:
     # Process validation
     - name: service_running
       function: process_running
       parameter:
         process_name: "forensic_agent.exe"
         
     # Network validation  
     - name: port_listening
       function: port_open
       parameter:
         port: 8080
         protocol: "tcp"
         
     # System state validation
     - name: firewall_enabled
       function: service_status_equals
       parameter:
         service: "Windows Defender Firewall"
         expected_status: "running"

Action Types
************

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

Flow Control Actions
====================

**Conditional Logic**

.. code-block:: yaml

   actions:
     - conditional:
         condition: '{{os_platform}} == "windows"'
         actions:
           - command:
               command: 'del "{{temp_file}}"'
         else:
           - command:
               command: 'rm "{{temp_file}}"'

**Loops and Iteration**

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

**Error Handling**

.. code-block:: yaml

   actions:
     # Try-catch blocks
     - try:
         actions:
           - click:
               target:
                 text: "Advanced Settings"
         catch:
           - click:
               target:
                 text: "Settings"
         finally:
           - screenshot:
               name: "settings_opened"

**Timing Control**

.. code-block:: yaml

   actions:
     # Simple delays
     - idle:
         duration: 2.5
         description: "Wait for application to load"
         
     # Wait for condition
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

**Timestamp Recording**

.. code-block:: yaml

   actions:
     - save_timestamp:
         variable: "deletion_start"
         description: "Record when file deletion began"
         
     - command:
         command: "rm /evidence/test.txt"
         
     - save_timestamp:
         variable: "deletion_complete"
         description: "Record when file deletion completed"

**System State Snapshots**

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
         
     # Process list capture
     - capture_processes:
         file: "/evidence/processes_{{timestamp}}.csv"
         format: "csv"

Best Practices
**************

Playbook Organization
====================

**Use Descriptive Names**

.. code-block:: yaml

   # Good: Clear, specific names
   - name: verify_trash_bin_metadata
   - name: capture_deletion_timestamp
   
   # Bad: Generic, unclear names  
   - name: test1
   - name: check_stuff

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

**Error Handling Strategy**

.. code-block:: yaml

   settings:
     on_error: "continue"        # or "stop", "retry"
     
   actions:
     - try:
         actions:
           - click: {target: {image: "primary_button.png"}}
         catch:
           - log: {message: "Primary button not found, trying fallback"}
           - click: {target: {text: "OK"}}
         finally:
           - screenshot: {name: "after_button_click"}

Variable Management
===================

**Use Environment-Specific Variables**

.. code-block:: yaml

   variables:
     # Platform-specific paths
     evidence_path:
       type: path
       value: |
         {% if os_platform == "windows" %}
         C:\Evidence\{{case_id}}
         {% else %}
         /evidence/{{case_id}}
         {% endif %}
         
     # User-specific settings
     username:
       type: string
       value: "{{env_username | default('adare')}}"

**Validate Critical Variables**

.. code-block:: yaml

   variables:
     case_id:
       type: string
       value: "CASE-2025-001"
       validation:
         pattern: "^CASE-[0-9]{4}-[0-9]{3}$"
         required: true
         
   actions:
     # Always validate before using critical variables
     - conditional:
         condition: '{{case_id | length > 0}}'
         actions:
           - command: {command: "mkdir /evidence/{{case_id}}"}
         else:
           - fail: {message: "Case ID is required"}

Testing Strategy
================

**Comprehensive Test Coverage**

.. code-block:: yaml

   tests:
     # Test different artifact types
     - name: filesystem_artifact_check
       function: file_exists
       parameter: {dst: "/evidence/deleted_file.txt"}
       
     - name: timestamp_artifact_check
       function: file_modified_within
       parameter: 
         dst: "/evidence/metadata.log"
         seconds: 10
         
     - name: content_artifact_check  
       function: file_content_matches
       parameter:
         dst: "/evidence/log.txt"
         pattern: "Deletion completed at.*"

**Test Data Validation**

.. code-block:: yaml

   tests:
     # Always test with realistic data
     - name: hash_validation
       function: file_hash_equals
       parameter:
         dst: "/evidence/critical_file.bin"
         algorithm: "sha256"
         expected: "{{expected_hash | hash_format('sha256')}}"

Performance Optimization
========================

**Minimize Unnecessary Actions**

.. code-block:: yaml

   # Good: Direct, efficient actions
   actions:
     - keyboard: {combination: ["ctrl", "shift", "del"]}  # Direct shortcut
     
   # Bad: Slow, indirect actions
   actions:
     - click: {target: {text: "Edit"}}
     - click: {target: {text: "Select All"}}  
     - click: {target: {text: "Delete"}}

**Optimize Screenshot Usage**

.. code-block:: yaml

   settings:
     screenshot:
       on_action: false          # Don't screenshot every action
       on_error: true            # Only on errors
       format: "jpg"             # Smaller file size
       quality: 80               # Reduce quality for speed

**Use Appropriate Timeouts**

.. code-block:: yaml

   settings:
     timeout: 300               # Overall experiment timeout
     
   actions:
     - click:
         target: {text: "Save"}
         timeout: 5              # Quick timeout for simple actions
         
     - wait_for:
         condition: "file_exists"
         timeout: 30             # Longer for file operations

Next Steps
**********

With playbook fundamentals mastered:

- **Run Experiments**: :doc:`running-experiments` - Execute your playbooks
- **Analyze Results**: :doc:`results` - Review forensic evidence
- **Advanced Techniques**: :doc:`../advanced/index` - Custom functions and optimization