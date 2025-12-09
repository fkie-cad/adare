**************************
Advanced Playbook Patterns
**************************

This guide covers advanced playbook patterns and complex syntax for experienced ADARE users. These patterns demonstrate sophisticated control flow, error handling, and dynamic behavior that goes beyond basic playbook concepts.

.. note::
   If you're new to ADARE playbooks, start with :doc:`../basics/actions` for basic conditional flow control examples.

Conditional Flow Control
************************

Complex Stop Patterns
======================

**Stop with Regex Matching**

Use regex patterns to validate complex string formats and stop on invalid data.

.. code-block:: yaml

   actions:
     - command:
         command: "echo 'Version: 3.14.159'"
         capture:
           variable: version_string
           parser: "re.search(r'Version: (.+)', output).group(1) if re.search(r'Version: (.+)', output) else ''"

     - stop:
         condition:
           variable: version_string
           matches: '^\d+\.\d+\.\d+$'
         description: "Stop if version doesn't match X.Y.Z format"

**Stop with JSON Data Validation**

Parse JSON output and validate specific fields before continuing.

.. code-block:: yaml

   actions:
     - command:
         command: "echo '{\"status\": \"success\", \"code\": 200, \"data\": {\"count\": 42}}'"
         capture:
           variable: api_response
           parser: "json.loads(output)"

     # Stop if status is not success
     - stop:
         condition:
           variable: api_response
           contains: '"status": "error"'
         description: "Stop if API returned error"

     # Extract nested field for further validation
     - command:
         command: "echo '{{api_response}}'"
         capture:
           variable: response_code
           parser: "json.loads(output)['code']"

     - stop:
         condition:
           variable: response_code
           greater_than: 299
         description: "Stop if HTTP status code indicates failure"

**Multi-Stage Validation with Stops**

Chain multiple validation steps to create robust error checking.

.. code-block:: yaml

   actions:
     # Stage 1: Capture system state
     - command:
         command: "df -h / | tail -1 | awk '{print $5}' | sed 's/%//'"
         capture:
           variable: disk_usage_percent
           parser: "int(output.strip())"

     - stop:
         condition:
           variable: disk_usage_percent
           greater_than: 90
         description: "Stop if disk usage exceeds 90%"

     # Stage 2: Check process status
     - command:
         command: "pgrep -c nginx"
         capture:
           variable: nginx_count
           parser: "int(output.strip())"

     - stop:
         condition:
           variable: nginx_count
           equals: 0
         description: "Stop if nginx is not running"

     # Stage 3: Validate configuration
     - command:
         command: "nginx -t 2>&1"
         capture:
           variable: config_status
           source: all
           parser: "'valid' if output['returncode'] == 0 else 'invalid'"

     - stop:
         condition:
           variable: config_status
           equals: "invalid"
         description: "Stop if nginx configuration is invalid"

Complex Continue Patterns
==========================

**Continue with Substring Matching**

Skip loop iterations based on partial string matches.

.. code-block:: yaml

   variables:
     file_patterns:
       type: list
       value: ["report_2024.pdf", "temp_data.csv", "report_2025.pdf", "cache.tmp"]

   actions:
     - loop:
         items: "{{file_patterns}}"
         item_var: filename
         description: "Process only report files"
         actions:
           - continue:
               condition:
                 variable: filename
                 contains: "temp"
               description: "Skip temporary files"

           - continue:
               condition:
                 variable: filename
                 contains: "cache"
               description: "Skip cache files"

           - command:
               command: "echo 'Processing {{filename}}'"

**Skip Iterations Based on Computed Values**

Use captured values from within the loop to decide whether to continue.

.. code-block:: yaml

   actions:
     - loop:
         times: 10
         description: "Process even iterations only"
         actions:
           - command:
               command: "echo $(({{index}} % 2))"
               capture:
                 variable: is_odd
                 parser: "int(output.strip())"

           - continue:
               condition:
                 variable: is_odd
                 equals: 1
               description: "Skip odd iterations"

           - command:
               command: "echo 'Processing even iteration {{index}}'"

**Continue with Multiple Conditions (Pattern)**

While ADARE doesn't support AND/OR logic in VariableCondition, you can chain continues for complex logic.

.. code-block:: yaml

   actions:
     - loop:
         times: 20
         actions:
           # Skip if index < 5
           - continue:
               condition:
                 variable: index
                 less_than: 5
               description: "Skip first 5 iterations"

           # Skip if index > 15
           - continue:
               condition:
                 variable: index
                 greater_than: 15
               description: "Skip after iteration 15"

           # Only iterations 5-15 will execute this
           - command:
               command: "echo 'Processing iteration {{index}}'"

Advanced Command Capture
=========================

**JSON Parsing with Error Handling**

Safely parse JSON with fallback values for malformed data.

.. code-block:: yaml

   actions:
     - command:
         command: "curl -s https://api.example.com/data || echo '{\"error\": true}'"
         allow_failure: true
         capture:
           variable: api_data
           parser: |
             try:
                 result = json.loads(output)
                 return result if 'error' not in result else None
             except:
                 return None

     - stop:
         condition:
           variable: api_data
           is_empty: true
         description: "Stop if API call failed or returned error"

**Regex Extraction with Groups**

Extract specific patterns from complex output.

.. code-block:: yaml

   actions:
     - command:
         command: "systemctl status nginx"
         capture:
           variable: nginx_pid
           parser: |
             match = re.search(r'Main PID: (\d+)', output)
             return int(match.group(1)) if match else 0

     - stop:
         condition:
           variable: nginx_pid
           equals: 0
         description: "Stop if nginx PID not found"

**Multi-Output Capture (stdout + stderr + returncode)**

Capture all command outputs for comprehensive analysis.

.. code-block:: yaml

   actions:
     - command:
         command: "make build 2>&1"
         allow_failure: true
         capture:
           variable: build_result
           source: all
           parser: |
             return {
                 'success': output['returncode'] == 0,
                 'warnings': output['stderr'].count('warning'),
                 'errors': output['stderr'].count('error'),
                 'output_lines': len(output['stdout'].split('\n'))
             }

     # Access nested dictionary values in subsequent commands
     - command:
         command: "echo '{{build_result}}'"
         capture:
           variable: build_success
           parser: "json.loads(output)['success']"

     - stop:
         condition:
           variable: build_success
           equals: false
         description: "Stop if build failed"

**Chaining Captured Variables**

Use captured variables to build complex workflows.

.. code-block:: yaml

   actions:
     # Step 1: Get username
     - command:
         command: "whoami"
         capture:
           variable: current_user

     # Step 2: Get home directory based on username
     - command:
         command: "echo $HOME"
         capture:
           variable: home_dir

     # Step 3: Check for specific file in home directory
     - command:
         command: "test -f {{home_dir}}/.config/app.conf && echo 'exists' || echo 'missing'"
         capture:
           variable: config_exists

     # Step 4: Conditional action based on chain
     - stop:
         condition:
           variable: config_exists
           equals: "missing"
         description: "Stop if user config is missing"

Conditional Blocks and Keyboard
================================

**When Conditions with Multiple Checks**

Check for multiple UI elements before executing a block.

.. code-block:: yaml

   actions:
     # Wait for specific UI state before proceeding
     - wait_until:
         condition:
           all:
             - exists:
                 text: "Ready"
             - not_exists:
                 text: "Loading"
         timeout: 30.0

     - block:
         when:
           - exists:
               text: "Save"
           - exists:
               text: "Cancel"
         description: "Save dialog is present"
         actions:
           - click:
               target:
                 text: "Save"
           - wait_until:
               condition:
                 not_exists:
                   text: "Save"
               timeout: 10.0

**Combining When Conditions with Variable Conditions**

Use both UI-based and variable-based conditions together.

.. code-block:: yaml

   actions:
     # Capture system state
     - command:
         command: "date +%H"
         capture:
           variable: current_hour
           parser: "int(output.strip())"

     # Skip during off-hours (example pattern)
     - continue:
         condition:
           variable: current_hour
           less_than: 9
         description: "Skip if before 9 AM"

     # Now check UI state
     - block:
         when:
           - exists:
               text: "Submit"
         actions:
           - click:
               target:
                 text: "Submit"

**Real-World Conditional UI Automation**

Handle optional dialogs that may or may not appear.

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Open File"

     # Optional: Handle "unsaved changes" dialog if it appears
     - keyboard:
         combination: ["ctrl", "s"]
         when:
           - exists:
               text: "Unsaved Changes"
         description: "Save if prompted"

     - keyboard:
         key: "enter"
         when:
           - exists:
               text: "Unsaved Changes"
         description: "Confirm dialog if present"

     # Continue with main workflow
     - click:
         target:
           text: "File Explorer"

Complex Loop Patterns
======================

**Nested Loops with Continue**

Use continue in nested loops for granular control.

.. code-block:: yaml

   variables:
     users:
       type: list
       value: ["alice", "bob", "charlie"]
     actions_list:
       type: list
       value: ["read", "write", "execute"]

   actions:
     - loop:
         items: "{{users}}"
         item_var: user
         actions:
           - loop:
               items: "{{actions_list}}"
               item_var: action
               actions:
                 # Skip write/execute for specific users
                 - continue:
                     condition:
                       variable: action
                       contains: "write"
                   description: "Skip write action (example)"

                 - command:
                     command: "echo 'User {{user}} can {{action}}'"

**Loops with Captured Variable Iteration**

Dynamically generate loop items from captured command output.

.. code-block:: yaml

   actions:
     # Get list of files from command
     - command:
         command: "ls /tmp/*.txt"
         capture:
           variable: txt_files
           parser: "output.strip().split('\n')"

     # Loop over captured file list
     - loop:
         items: "{{txt_files}}"
         item_var: filepath
         actions:
           - command:
               command: "cat {{filepath}}"
               capture:
                 variable: file_content

           - continue:
               condition:
                 variable: file_content
                 is_empty: true
               description: "Skip empty files"

           - command:
               command: "echo 'Processing {{filepath}}'"

**Dynamic Loop Control with Stops**

Stop the entire playbook from within a loop based on critical conditions.

.. code-block:: yaml

   actions:
     - loop:
         times: 100
         description: "Process up to 100 items"
         actions:
           - command:
               command: "check_system_health.sh"
               capture:
                 variable: health_status
                 source: returncode

           # Stop entire playbook if system health check fails
           - stop:
               condition:
                 variable: health_status
                 greater_than: 0
               description: "Critical: System health check failed"

           - command:
               command: "process_item.sh {{index}}"

Real-World Patterns
*******************

Error Recovery Pattern
======================

Try an action, capture the result, and stop on failure with detailed diagnostics.

.. code-block:: yaml

   actions:
     # Attempt critical operation
     - command:
         command: "docker build -t myapp:latest ."
         allow_failure: true
         capture:
           variable: build_result
           source: all
           parser: |
             {
                 'success': output['returncode'] == 0,
                 'exit_code': output['returncode'],
                 'error_log': output['stderr'][-500:] if output['stderr'] else ''  # Last 500 chars
             }

     # Capture success flag
     - command:
         command: "echo '{{build_result}}'"
         capture:
           variable: build_success
           parser: "json.loads(output)['success']"

     # Stop with diagnostic info if failed
     - stop:
         condition:
           variable: build_success
           equals: false
         description: "Docker build failed - check artifacts for error logs"

     # Continue with deployment if successful
     - command:
         command: "docker push myapp:latest"

Validation Chain Pattern
=========================

Capture → validate → conditional continue for robust data processing.

.. code-block:: yaml

   variables:
     endpoints:
       type: list
       value: ["/api/users", "/api/posts", "/api/comments"]

   actions:
     - loop:
         items: "{{endpoints}}"
         item_var: endpoint
         description: "Validate each API endpoint"
         actions:
           # Step 1: Capture response
           - command:
               command: "curl -s -o /dev/null -w '%{http_code}' https://example.com{{endpoint}}"
               capture:
                 variable: http_code
                 parser: "int(output.strip())"

           # Step 2: Validate response code
           - continue:
               condition:
                 variable: http_code
                 greater_than: 399
               description: "Skip failed endpoints"

           # Step 3: Only successful endpoints reach here
           - command:
               command: "echo '✓ Endpoint {{endpoint}} is healthy ({{http_code}})'"

           # Step 4: Pull detailed response for successful endpoints
           - command:
               command: "curl -s https://example.com{{endpoint}}"
               capture:
                 variable: response_data

Dynamic Behavior Pattern
=========================

Capture system state and adjust actions accordingly.

.. code-block:: yaml

   actions:
     # Detect operating system
     - command:
         command: "uname -s"
         capture:
           variable: os_name

     # Detect available memory
     - command:
         command: "free -m | awk '/^Mem:/{print $7}'"
         capture:
           variable: available_memory
           parser: "int(output.strip())"

     # Adjust behavior based on available resources
     - continue:
         condition:
           variable: available_memory
           less_than: 1000
         description: "Skip heavy operations on low memory systems"

     # This heavy operation only runs on systems with sufficient memory
     - command:
         command: "run_memory_intensive_task.sh"

     # OS-specific commands
     - command:
         command: "apt update"
         when:
           - exists:
               text: "Ubuntu"
         description: "Update packages on Ubuntu"

Tips and Best Practices
************************

**Keep Conditions Simple**
  Complex conditions are harder to debug. Chain multiple simple conditions instead of trying to create one complex condition.

**Use Descriptive Variable Names**
  ``captured_username`` is better than ``var1``. Descriptive names make playbooks self-documenting.

**Add Description to Every Stop/Continue**
  Explain *why* the condition exists. Future maintainers (including yourself) will thank you.

**Test Parsers Separately**
  Complex parser expressions can be tested in Python REPL before adding to playbooks.

**Capture Diagnostic Info Before Stopping**
  When stopping due to errors, ensure you've captured enough information to debug the issue.

**Use allow_failure for Exploratory Commands**
  Commands that might fail (like testing file existence) should use ``allow_failure: true``.

**Consider Stop vs Continue**
  - Use ``stop`` for critical failures that invalidate the entire experiment
  - Use ``continue`` for expected variations that should skip non-critical actions

Future Extensions
*****************

This advanced patterns guide will be expanded with additional topics:

- File operation patterns (bulk file processing, recursive operations)
- Complex testing patterns (conditional test execution, test result branching)
- Performance optimization patterns (parallel execution, caching strategies)
- Error handling patterns (retry logic, fallback actions)
- Integration patterns (external API workflows, database interactions)

Check back for updates as new patterns are documented.
