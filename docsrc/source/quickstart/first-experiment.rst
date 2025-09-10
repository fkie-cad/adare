*****************
First Experiment
*****************

This detailed tutorial walks you through creating a comprehensive forensic experiment from scratch. You'll build a Windows registry analysis experiment that demonstrates advanced ADARE features.

Overview
********

We'll create an experiment that:

- Modifies Windows registry keys
- Captures before/after snapshots  
- Analyzes registry forensic artifacts
- Tests across different Windows versions
- Demonstrates advanced GUI automation

Prerequisites
*************

For this tutorial, you need:

- ADARE installed and working
- A Windows VM image (Windows 10/11)
- Basic knowledge of Windows registry
- Completed the :doc:`index` tutorial

Project Setup
*************

If you haven't already, create a new project for advanced experiments:

.. code-block:: bash

   adare project create advanced-forensics
   cd advanced-forensics

Environment Configuration
**************************

Create a Windows environment:

.. code-block:: yaml
   :caption: windows11-env.yml

   name: win11-test
   vm: "/path/to/Windows11.ova"  # Update path!
   os:
     os: "Windows"
     platform: "windows" 
     distribution: "Pro"
     version: "11 22H2"
     language: "English"
   tags:
     - windows
     - win11
     - registry

Load the environment:

.. code-block:: bash

   adare environment load windows11-env.yml

Registry Analysis Experiment
****************************

Create the experiment structure:

.. code-block:: bash

   adare experiment create registry-modification-analysis

Experiment Metadata
===================

.. code-block:: yaml
   :caption: experiments/registry-modification-analysis/metadata.yml

   environments:
     - win11-test
   description: "Analyze registry artifacts from software installation simulation"
   tags:
     - registry
     - windows-artifacts
     - forensics
   author: "Your Name"
   created: "2025-09-10"

Advanced Playbook
=================

Create a comprehensive playbook that demonstrates advanced features:

.. code-block:: yaml
   :caption: experiments/registry-modification-analysis/playbook.yml

   settings:
     idle: 1.5
     timeout: 600
     screenshot:
       format: "png"
       quality: 95
       on_action: true    # Screenshot every action
     
     retry:
       attempts: 3        # Retry failed actions
       delay: 2.0

   variables:
     app_name:
       type: string
       value: "TestForensicsApp"
       description: "Simulated application name"
     
     registry_key:
       type: string
       value: "HKEY_CURRENT_USER\\Software\\{{app_name}}"
       description: "Registry key to create"
     
     install_path:
       type: path
       value: "C:\\Program Files\\{{app_name}}"
       description: "Simulated install location"
     
     username:
       type: string
       value: "forensics"
       description: "Windows username"

   tests:
     # Pre-experiment tests
     - name: registry_key_absent_before
       description: "Verify registry key doesn't exist initially"
       function: registry_key_does_not_exist
       parameter:
         key: '{{registry_key}}'

     - name: install_dir_absent_before  
       description: "Verify install directory doesn't exist"
       function: directory_does_not_exist
       parameter:
         path: '{{install_path}}'

     # Post-experiment tests
     - name: registry_key_created
       description: "Verify registry key was created"
       function: registry_key_exists
       parameter:
         key: '{{registry_key}}'

     - name: registry_value_correct
       description: "Verify registry value is correct"
       function: registry_value_equals
       parameter:
         key: '{{registry_key}}'
         value_name: 'InstallPath'
         expected: '{{install_path}}'

     - name: install_dir_created
       description: "Verify installation directory created"
       function: directory_exists
       parameter:
         path: '{{install_path}}'

     - name: uninstall_entry_created
       description: "Verify uninstall registry entry"
       function: registry_key_exists
       parameter:
         key: 'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{{app_name}}'

   actions:
     # Initial state verification
     - test: registry_key_absent_before
     - test: install_dir_absent_before

     # Take system snapshot
     - snapshot:
         name: "pre_install_state"
         description: "Capture system state before installation"

     # Simulate software installation via registry
     - command:
         name: "Create Registry Key"
         description: "Create main application registry key"
         command: 'reg add "{{registry_key}}" /f'
         shell: true
         admin: true

     - command:
         name: "Set Install Path"
         description: "Set installation path in registry"
         command: 'reg add "{{registry_key}}" /v "InstallPath" /t REG_SZ /d "{{install_path}}" /f'
         shell: true
         admin: true

     - command:
         name: "Set Version Info"
         description: "Add version information"
         command: 'reg add "{{registry_key}}" /v "Version" /t REG_SZ /d "1.0.0" /f'
         shell: true
         admin: true

     # Create installation directory
     - command:
         name: "Create Install Directory"
         description: "Create program installation directory"
         command: 'mkdir "{{install_path}}"'
         shell: true
         admin: true

     - command:
         name: "Create Executable Stub"
         description: "Create fake executable for realism"
         command: 'echo "Fake executable" > "{{install_path}}\\{{app_name}}.exe"'
         shell: true
         admin: true

     # Add uninstall information
     - command:
         name: "Add Uninstall Entry"
         description: "Create Windows uninstall registry entry"
         command: |
           reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{{app_name}}" /f
           reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{{app_name}}" /v "DisplayName" /t REG_SZ /d "{{app_name}}" /f
           reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{{app_name}}" /v "InstallLocation" /t REG_SZ /d "{{install_path}}" /f
         shell: true
         admin: true

     # Record installation timestamp  
     - save_timestamp:
         description: "Record installation completion time"
         variable: install_timestamp

     # GUI verification - open registry editor
     - keyboard:
         combination: ["win", "r"]
         description: "Open Run dialog"

     - idle:
         duration: 1.0

     - type:
         text: "regedit"
         description: "Type registry editor command"

     - keyboard:
         combination: ["enter"]
         description: "Launch registry editor"

     - idle:
         duration: 3.0
         description: "Wait for registry editor to open"

     # Navigate to our registry key
     - click:
         target:
           text: "HKEY_CURRENT_USER"
         description: "Expand HKEY_CURRENT_USER"

     - click:
         target:
           text: "Software"
         description: "Navigate to Software key"

     - click:
         target:
           text: "{{app_name}}"
         description: "Find our application key"

     # Take screenshot of registry for evidence
     - screenshot:
         name: "registry_evidence"
         description: "Capture registry state for forensic evidence"

     # Close registry editor
     - keyboard:
         combination: ["alt", "f4"]
         description: "Close registry editor"

     # Post-installation verification
     - test: registry_key_created
     - test: registry_value_correct
     - test: install_dir_created
     - test: uninstall_entry_created

     # Create final system snapshot
     - snapshot:
         name: "post_install_state"  
         description: "Capture final system state"

     # Generate forensic report
     - generate_report:
         name: "Registry Analysis Report"
         description: "Comprehensive forensic analysis of registry changes"
         include:
           - registry_diff
           - file_system_changes
           - timestamps
           - screenshots

Advanced Features Demonstrated
******************************

This experiment showcases several advanced ADARE capabilities:

Conditional Logic
=================

Add conditional tests that only run on certain Windows versions:

.. code-block:: yaml

   actions:
     - conditional:
         condition: '{{os_version}} >= "Windows 10"'
         actions:
           - test: modern_registry_features
         else:
           - test: legacy_registry_features

Loops and Iteration
===================

Test multiple registry keys:

.. code-block:: yaml

   actions:
     - loop:
         variable: "test_key"
         values: ["TestKey1", "TestKey2", "TestKey3"]
         actions:
           - command:
               command: 'reg add "HKEY_CURRENT_USER\Software\{{test_key}}" /f'
           - test: 
               name: "verify_{{test_key}}_created"
               function: registry_key_exists
               parameter:
                 key: 'HKEY_CURRENT_USER\Software\{{test_key}}'

Error Handling
==============

Handle failures gracefully:

.. code-block:: yaml

   actions:
     - try:
         actions:
           - command:
               command: 'reg add "HKEY_LOCAL_MACHINE\Software\TestKey" /f'
               admin: true
         catch:
           - log:
               message: "Failed to create HKLM key, trying HKCU instead"
           - command:
               command: 'reg add "HKEY_CURRENT_USER\Software\TestKey" /f'

Running the Experiment
**********************

Execute your advanced experiment:

.. code-block:: bash

   # Run with debug screenshots enabled
   adare experiment run registry-modification-analysis -e win11-test --debug-screenshots

   # Run in development mode for iterative testing
   adare experiment develop registry-modification-analysis -e win11-test

   # Run and preserve VM snapshot for later analysis
   adare experiment run registry-modification-analysis -e win11-test --preserve-snapshot

Analyzing Results
*****************

The experiment generates comprehensive forensic data:

Registry Diff Report
====================

View changes to the Windows registry:

.. code-block:: bash

   adare run info <run_id> --section registry

This shows:

- New registry keys created
- Modified registry values
- Timestamps of all changes
- Before/after comparisons

File System Changes
===================

Analyze file system modifications:

.. code-block:: bash

   adare run info <run_id> --section filesystem

Screenshots Timeline
====================

Review GUI interactions:

.. code-block:: bash

   # Open results directory
   cd environments/win11-test/results/registry-modification-analysis_<timestamp>/screenshots

   # View screenshot timeline
   ls -la *.png

Custom Analysis
===============

Export data for external forensic tools:

.. code-block:: bash

   # Export registry changes as JSON
   adare run export <run_id> --format json --output registry_analysis.json

   # Export timeline data
   adare run export <run_id> --format timeline --output forensic_timeline.csv

Best Practices Learned
**********************

From this advanced experiment, you've learned:

**Forensic Methodology**
  - Always capture before/after system state
  - Document every change with timestamps
  - Verify artifacts are created as expected

**Automation Design**  
  - Use variables for maintainable playbooks
  - Include comprehensive error handling
  - Test on multiple OS versions

**Evidence Collection**
  - Take screenshots at key moments
  - Generate reports for non-technical audiences
  - Export data in standard forensic formats

**Performance Optimization**
  - Use appropriate idle delays
  - Optimize image recognition for reliability
  - Leverage conditional logic to avoid unnecessary steps

Next Steps
**********

Now you're ready for advanced ADARE usage:

- **Advanced Topics**: :doc:`../advanced/index` - Custom functions, performance tuning, and advanced techniques
- **CLI Reference**: :doc:`../cli-reference/index` - Complete command documentation
- **User Guide**: :doc:`../user-guide/index` - Daily usage patterns and best practices