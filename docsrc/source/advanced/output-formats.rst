Output Formats (in development)
===============================

ADARE CLI supports multiple output formats to enable automation and integration with external tools.
By default, commands use Rich formatting for human-readable terminal output, but you can also
export data in structured formats like JSON and YAML.

Global Options
--------------

All ADARE commands support the following output format options:

.. code-block:: bash

   adare --output-format <format> [command]
   adare --format <format> [command]            # Short form
   adare --output-file <file> [command]         # Save to file

Supported formats:
- ``rich`` (default): Human-readable terminal output with colors and formatting
- ``json``: Machine-readable JSON format
- ``yaml``: Human and machine-readable YAML format

Examples
--------

Basic Usage
~~~~~~~~~~~

.. code-block:: bash

   # Default Rich output
   adare show projects

   # JSON output to console
   adare --format json show projects

   # YAML output to file
   adare --format yaml --output-file projects.yaml show projects

   # Dual output: Rich to console AND JSON to file
   adare --output-file results.json show projects

   # Dual output: Rich to console AND YAML to file
   adare --format yaml --output-file results.yaml show projects

Information Commands
~~~~~~~~~~~~~~~~~~~~

All ``show`` commands support structured output:

.. code-block:: bash

   # List all projects in JSON
   adare --format json show projects

   # List experiments with YAML output
   adare --format yaml show experiments

   # Get specific experiment details
   adare --format json show experiment my_experiment

   # List runs for automation
   adare --format json show runs

Experiment Execution
~~~~~~~~~~~~~~~~~~~~

Experiment runs provide comprehensive results in structured formats:

.. code-block:: bash

   # Run experiment with JSON summary
   adare --format json experiment run my_experiment test_env

   # Run batch experiments with YAML output
   adare --format yaml experiment run "exp_*" "*_env"

   # Save results to file for analysis
   adare --format json --output-file results.json experiment run my_experiment

   # DUAL OUTPUT: Normal Rich console + JSON file (perfect for automation!)
   adare --output-file results.json experiment run my_experiment test_env

Dual Output Mode
~~~~~~~~~~~~~~~~

ADARE supports **dual output** - showing human-readable Rich output on the console while simultaneously saving structured data to a file. This is perfect for interactive use with automation capabilities.

.. code-block:: bash

   # Show normal Rich output + save JSON to file
   adare --output-file test.json experiment run test_sqlite -t

   # Show normal Rich output + save YAML to file
   adare --format yaml --output-file test.yaml show experiments

**How it works:**
- ``--output-file FILE`` = Always enables dual output (Rich console + structured file)
- ``--format FORMAT --output-file FILE`` = Rich console + FORMAT file
- ``--format FORMAT`` (without --output-file) = FORMAT to console only
- Default file format is JSON, unless ``--format`` specifies otherwise

Output Schema
-------------

Project List
~~~~~~~~~~~~

.. code-block:: json

   {
     "projects": [
       {
         "name": "MyProject",
         "description": "Project description",
         "created_at": "2024-01-01T12:00:00",
         "experiment_count": 5,
         "environment_count": 3
       }
     ]
   }

Experiment List
~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "experiments": [
       {
         "name": "test_experiment",
         "ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
         "project": "MyProject",
         "environment": "Windows10",
         "description": "Test experiment",
         "tags": ["forensics", "registry"],
         "created_at": "2024-01-01T12:00:00",
         "run_count": 3,
         "last_run": "2024-01-01T15:30:00",
         "web_status": "published"
       }
     ]
   }

Experiment Run Results
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "summary": {
       "total_combinations": 2,
       "successful_runs": 1,
       "failed_runs": 1,
       "interrupted_runs": 0,
       "success_rate": 50.0,
       "total_duration_seconds": 300.5
     },
     "results": [
       {
         "environment": "Windows10",
         "experiment": "test_experiment",
         "status": "SUCCESS",
         "duration_seconds": 180.2,
         "error_message": null,
         "run_ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
         "start_time": "2024-01-01T12:00:00",
         "end_time": "2024-01-01T12:03:00"
       },
       {
         "environment": "Windows11",
         "experiment": "test_experiment",
         "status": "FAILED",
         "duration_seconds": 120.3,
         "error_message": "Test assertion failed",
         "run_ulid": "01ARZ3NDEKTSV4RRFFQ69G5GAW",
         "start_time": "2024-01-01T12:03:30",
         "end_time": "2024-01-01T12:05:30"
       }
     ]
   }

Single Run Details
~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
     "experiment": {
       "name": "test_experiment",
       "ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAV"
     },
     "environment": {
       "name": "Windows10",
       "ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAW"
     },
     "project": "MyProject",
     "timing": {
       "start_time": "2024-01-01T12:00:00",
       "end_time": "2024-01-01T12:03:00",
       "duration_seconds": 180.2
     },
     "status": "SUCCESS",
     "metadata": {
       "published": true,
       "fake": false,
       "os_info": "Windows 10 Pro 21H2",
       "vm_box": "windows10-21h2"
     },
     "test_results": {
       "overall_result": "SUCCESS",
       "tests": [
         {
           "name": "registry_check",
           "testfunction_name": "check_registry_key",
           "result_status": "SUCCESS",
           "parameters": [
             {
               "name": "key_path",
               "dtype": "str",
               "value": "HKEY_LOCAL_MACHINE\\Software\\MyApp"
             }
           ]
         }
       ]
     }
   }

Integration Examples
--------------------

Python Integration
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import subprocess
   import json

   # Run experiment and capture JSON output
   result = subprocess.run([
       'adare', '--format', 'json',
       'experiment', 'run', 'my_experiment', 'test_env'
   ], capture_output=True, text=True)

   # Parse results
   experiment_data = json.loads(result.stdout)
   success_rate = experiment_data['summary']['success_rate']
   print(f"Success rate: {success_rate}%")

Shell Scripting
~~~~~~~~~~~~~~~

.. code-block:: bash

   #!/bin/bash

   # Run experiments and save results
   adare --format json --output-file results.json experiment run "exp_*" "*_env"

   # Extract success rate using jq
   SUCCESS_RATE=$(cat results.json | jq '.summary.success_rate')

   if (( $(echo "$SUCCESS_RATE < 100" | bc -l) )); then
       echo "Some experiments failed!"
       exit 1
   fi

CI/CD Integration
~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # GitHub Actions example
   - name: Run ADARE experiments
     run: |
       adare --format json --output-file results.json experiment run test_suite

   - name: Upload results
     uses: actions/upload-artifact@v3
     with:
       name: experiment-results
       path: results.json

Best Practices
--------------

1. **Automation**: Use ``--format json`` for scripts and automation
2. **Human Review**: Use ``--format yaml`` for configuration files and human review
3. **File Output**: Always use ``--output-file`` for large result sets to avoid terminal overflow
4. **Error Handling**: Check exit codes in addition to parsing output for robust automation
5. **Schema Validation**: Validate JSON output structure before processing in critical systems

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

**Invalid JSON output**:
   Ensure no other output (like warnings) is mixed with JSON. Use ``--very-verbose`` flag carefully.

**Missing fields in output**:
   Some fields may be null/empty if data is not available. Always check for existence before accessing.

**Large output files**:
   For batch experiments, output can be large. Consider filtering or processing incrementally.

**Rich markup in structured output**:
   If you see markup like ``[bold]`` in JSON/YAML, this indicates a bug in data preparation.

Migration from Rich Output
~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're migrating scripts from parsing Rich terminal output:

1. Replace text parsing with JSON/YAML parsing
2. Update field names to match new schema (e.g., ``duration`` → ``duration_seconds``)
3. Handle new nested structure (e.g., experiment info is now under ``experiment`` key)
4. Use proper datetime parsing for ISO format timestamps