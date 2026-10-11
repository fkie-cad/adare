Output Formats, Errors and Exit Codes
=====================================

ADARE's CLI is meant to be driven by people, shell scripts and AI agents alike.
Every read-only command can print its data as Rich tables (for humans), plain
tab-separated text (for ``cut``/``awk``), JSON or YAML, and every command
reports errors and exit codes the same way.

Choosing a format
-----------------

Read-only ``list``/``info``/``show``/``status`` commands take the format flags
**after the subcommand**:

.. code-block:: bash

   adare env list --json
   adare experiment info my_experiment --format yaml
   adare run list --format plain
   adare status --json

The global options before the subcommand keep working, and an environment
variable sets a default for a whole shell or CI job:

.. code-block:: bash

   adare --format json env list           # alias: --output-format
   ADARE_FORMAT=json adare env list
   adare --output-file runs.json run list # Rich on the console + JSON file

Formats:

- ``rich``: colour tables and panels for a terminal.
- ``plain``: tab-separated text. A list is one header row plus one row per item;
  a single record is ``key<TAB>value`` lines (nested tables follow under a
  ``# name`` line). Values are never truncated (full ULIDs), nested fields become
  dotted columns (``vm.id``), booleans are ``true``/``false``, lists are
  comma-joined, and there is no colour, box drawing or emoji.
- ``json`` / ``yaml``: one parseable document on stdout. ``--json`` is shorthand
  for ``--format json``.

Precedence, highest first:

1. ``--json`` / ``--format`` after the subcommand
2. ``adare --format`` / ``--output-format`` before it
3. ``ADARE_FORMAT`` (``rich``, ``plain``, ``json`` or ``yaml``)
4. auto: ``rich`` when stdout is a terminal, ``plain`` when it is piped or redirected

``-o`` is deliberately **not** a format flag: several commands already use it for
an output file. ``NO_COLOR`` is respected by the Rich output.

Commands that cannot produce structured data (for example ``vm gui-doctor``, which
streams live probe results) still accept ``--format rich|plain`` but exit with a
usage error (exit code 2) when asked for ``json``/``yaml``, instead of printing a
table that a JSON parser would choke on.

stdout and stderr
-----------------

stdout carries only data. Logs, progress messages, warnings and errors go to
stderr, so ``adare env list --json | jq .`` works even while warnings are shown.

Errors
------

A failure prints **one** concise message on stderr:

.. code-block:: text

   Error: Experiment run "NOSUCH" not found
   Hints:
     - Use `adare run list` to list available experiment runs
     - Check if the run ULID is correct

In ``json`` (and ``yaml``) mode the message is a document instead:

.. code-block:: json

   {"error": {"code": "RUN_NOT_FOUND",
              "message": "Experiment run \"NOSUCH\" not found",
              "hint": "Use `adare run list` to list available experiment runs",
              "solutions": ["Use `adare run list` to list available experiment runs",
                            "Check if the run ULID is correct"]}}

``code`` is derived from the exception class (``TestFunctionNotFoundError`` ->
``TESTFUNCTION_NOT_FOUND``, ``VMNotFoundError`` -> ``VM_NOT_FOUND``); ``hint`` is
the first suggested fix or ``null``; ``solutions`` is always a list. Tracebacks are
only printed with ``--very-verbose``.

Exit codes
----------

=====  ===========================================================
Code   Meaning
=====  ===========================================================
``0``  success (including informational results such as "no projects found")
``1``  error
``2``  usage error (bad option or argument, unsupported ``--format``)
``3``  not found (the named run, environment, experiment, VM, profile ... does not exist)
=====  ===========================================================

Earlier versions exited ``255`` on every error and ``0`` on some failures
(e.g. ``vm info`` or ``os-profile show`` with an unknown name).

Dual Output Mode
----------------

``--output-file FILE`` shows the normal console output **and** saves the
structured data to ``FILE``:

- ``--output-file FILE`` alone: Rich (or plain) console + JSON file
- ``--format yaml --output-file FILE``: console + YAML file

.. code-block:: bash

   adare --output-file results.json experiment run my_experiment -e test_env
   adare --format yaml --output-file experiments.yaml experiment list

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
4. **Error Handling**: Check exit codes (0/1/2/3) and, in json mode, parse the ``{"error": ...}`` document on stderr
5. **Schema Validation**: Validate JSON output structure before processing in critical systems

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

**Invalid JSON output**:
   Read stdout only: logs and warnings go to stderr. Anything else on stdout in json mode is a bug.

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