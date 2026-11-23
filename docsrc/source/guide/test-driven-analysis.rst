********************
Test-Driven Analysis
********************

Test-driven analysis is the primary workflow in ADARE. Rather than running an
experiment and then manually inspecting what happened, you define expected
forensic outcomes *before* execution. ADARE runs the experiment, evaluates
every assertion, and reports which artifacts matched expectations and which
did not.

This approach turns forensic experiments into repeatable, auditable test suites
that can be re-run across OS versions, software updates, or configuration
changes to detect when artifact behavior diverges.


What Is Test-Driven Analysis?
=============================

In a test-driven workflow you:

1. **Define expectations first** -- specify which files, registry keys, database
   entries, or log lines should exist (or not exist) after a set of user actions.
2. **Automate the actions** -- write a playbook that performs those user actions
   inside a VM (creating an entry in an application, opening a document, deleting
   a file, etc.).
3. **Let ADARE evaluate** -- the framework executes the actions, runs every test
   assertion, and records pass/fail results with full context.

Each test maps to a *testfunction* -- a small, reusable validation routine from
one of the built-in testsets (``standard``, ``json``, ``csv``, ``xml``,
``sqlite``, ``linux``, ``windows``). See :doc:`/reference/testfunctions/index`
for the complete catalog.


Designing a Test Plan
=====================

Before writing a playbook, decide what you want to verify.

Choosing testfunctions
----------------------

Pick one testfunction per finding. :doc:`choosing-testfunctions` maps goals to functions
(and names the look-alike *not* to use); ``adare test search "<goal>"`` searches the
catalog from the command line.

Defining pass/fail criteria
---------------------------

For each artifact, decide:

- **Must exist** -- e.g., an application's database must be present after
  the first entry was saved.
- **Must contain specific data** -- e.g., the new entry must appear in the
  database's ``items`` table.
- **Must not exist** -- e.g., a file must be absent after secure deletion.
- **Must match a value** -- e.g., a registry key must hold a specific DWORD.

Each criterion becomes one test entry in the playbook.


Writing the Playbook
====================

A test-driven playbook has four main sections: ``settings``, ``variables``,
``tests``, and ``actions``.

.. code-block:: yaml

   settings:
     idle: 1.0
     timeout: 600
     screenshot:
       format: png
       quality: 95

   variables:
     entry_title: "Research notes"
     app_db: "C:\\Users\\adare\\AppData\\Roaming\\SomeApp\\data\\app.db"

   tests:
     - name: app_db_exists
       function: standard.file_exists
       parameter:
         dst: "{{ app_db }}"

     - name: entry_recorded
       function: sqlite.row_count
       parameter:
         dst: "{{ app_db }}"
         query: "SELECT title FROM items WHERE title = '{{ entry_title }}'"
         expected_count: 1

     - name: thumbnail_stored
       function: standard.file_exists
       parameter:
         dst: "C:\\Users\\adare\\AppData\\Roaming\\SomeApp\\data\\thumbnails.db"

   actions:
     # open SomeApp through the Windows Run dialog
     - keyboard: {combination: ["win", "r"]}
     - keyboard: {text: "someapp"}
     - keyboard: {key: "enter"}
     - idle: {duration: 5}

     - keyboard: {text: "{{ entry_title }}"}
     - keyboard: {key: "enter"}
     - idle: {duration: 5}

     - test: app_db_exists
     - test: entry_recorded
     - test: thumbnail_stored

     - keyboard: {combination: ["alt", "f4"]}

How tests integrate with actions
--------------------------------

Tests are *declared* in the ``tests`` section and *executed* as ``- test: <name>`` actions
within the ``actions`` sequence. This lets you control exactly when each
assertion runs -- after the relevant action has completed but before subsequent
actions might alter state.

You can also set per-test timeouts for long-running validations:

.. code-block:: yaml

   tests:
     - name: large_db_check
       function: sqlite.query_result
       timeout: 300
       parameter:
         dst: "/path/to/large.db"
         query: "SELECT count(*) AS n FROM events"
         expected_result: [{n: 1000}]


Running the Workflow
====================

ADARE uses a two-phase workflow: **test mode** for iterative development and
**production mode** for final, integrity-verified runs.

Test mode (default)
-------------------

.. code-block:: bash

   adare experiment run my-experiment -e win11

In test mode:

- The playbook can be modified between runs.
- Runs are marked as test runs in the database.
- No integrity checks are enforced.
- Only the 10 newest test runs per experiment and environment are kept: after
  each test run, up to 5 older finished ones of that environment are removed with
  their run folders, and a line such as
  ``removed 3 older test runs (1.2 GiB; ADARE_TEST_RUNS_KEEP=10)`` says so.
  The run that just finished counts toward the 10 and is never removed, and
  neither is the newest successful run (finished, all tests passed), however
  many failed attempts followed it. Runs started less than an hour ago, runs
  still in progress and dev sessions' runs are never removed either. Change the
  number with ``adare system settings set ADARE_TEST_RUNS_KEEP 25`` (``0`` keeps
  only the run that just finished, plus the last good one; ``-1`` switches
  retention off). Production runs are never touched. Details:
  :ref:`test-run retention <cli-test-run-retention>`.
- Use this phase to refine actions, fix timing issues, and tune test
  parameters until all assertions pass reliably.

Production mode
---------------

.. code-block:: bash

   adare experiment run my-experiment -e win11 --production

In production mode:

- The playbook is locked; integrity hashes are verified before execution.
- Runs are recorded as official production results.
- Any playbook modification after loading invalidates the hash and prevents
  execution.

The typical cycle is: iterate in test mode until satisfied, then execute one
or more production runs to generate the official forensic record.


Interpreting Results
====================

After a run completes, use the following tools to review outcomes.

Run info
--------

.. code-block:: bash

   adare runs info

This displays a summary of every test execution: pass/fail status, execution
time, and any error messages for failed assertions.

Screenshots
-----------

ADARE captures screenshots at key points during execution. They are stored in
the run directory and are useful for diagnosing GUI automation failures or
confirming that the correct application state was reached before a test ran.

Logs
----

Three log files provide progressively deeper detail:

- **adare.log** -- host-side orchestration log (experiment lifecycle, VM
  management, result collection).
- **adarevm.log** -- guest-side agent log (action execution, test evaluation,
  file operations inside the VM).
- **mcp_gui.log** -- GUI automation server log (screenshot analysis, element
  location, click/type operations).


End-to-End Example: Recent Items Analysis
=========================================

This example investigates which artifacts a made-up application, SomeApp,
leaves on Windows 11 when a user creates an entry, pins it, and then clears the
recent-items list. Swap in the application, paths and tables you study.

Step 1 -- Design the test plan
------------------------------

We want to verify:

1. After creating an entry, the application's database records it as recent.
2. After pinning, the pin exists.
3. After clearing the recent items, the entry is gone from the recent list but
   the pin persists.

Step 2 -- Create the experiment
-------------------------------

.. code-block:: bash

   adare experiment create recent-items-analysis

Step 3 -- Write the playbook
-----------------------------

.. code-block:: yaml
   :caption: experiments/recent-items-analysis/playbook.yml

   settings:
     idle: 1.5
     timeout: 600
     screenshot:
       format: png

   variables:
     data_dir: "C:\\Users\\adare\\AppData\\Roaming\\SomeApp\\data"
     app_db: "{{ data_dir }}\\app.db"
     entry_title: "Example entry"

   tests:
     - name: entry_in_recent
       function: sqlite.row_count
       parameter:
         dst: "{{ app_db }}"
         query: >
           SELECT i.title FROM recent r
           JOIN items i ON r.item_id = i.id
           WHERE i.title = '{{ entry_title }}'
         expected_count: 1

     - name: pin_exists
       function: sqlite.row_count
       parameter:
         dst: "{{ app_db }}"
         query: >
           SELECT i.title FROM pins p
           JOIN items i ON p.item_id = i.id
           WHERE i.title = '{{ entry_title }}'
         expected_count: 1

     - name: recent_cleared
       function: sqlite.row_count
       parameter:
         dst: "{{ app_db }}"
         query: >
           SELECT i.title FROM recent r
           JOIN items i ON r.item_id = i.id
           WHERE i.title = '{{ entry_title }}'
         expected_count: 0

     - name: pin_survives_clear
       function: sqlite.row_count
       parameter:
         dst: "{{ app_db }}"
         query: >
           SELECT i.title FROM pins p
           JOIN items i ON p.item_id = i.id
           WHERE i.title = '{{ entry_title }}'
         expected_count: 1

   actions:
     # --- Open SomeApp (Windows Run dialog) and create an entry ---
     - keyboard: {combination: ["win", "r"]}
     - keyboard: {text: "someapp"}
     - keyboard: {key: "enter"}
     - idle: {duration: 5}
     - keyboard: {combination: ["ctrl", "n"]}
     - keyboard: {text: "{{ entry_title }}"}
     - keyboard: {key: "enter"}
     - idle: {duration: 5}

     # --- Verify the entry is listed as recent ---
     - test: entry_in_recent

     # --- Pin the entry ---
     - keyboard: {combination: ["ctrl", "p"]}
     - idle: {duration: 2}

     # --- Verify the pin exists ---
     - test: pin_exists

     # --- Clear the recent items ---
     - click: {target: {text: "Clear recent items"}}
     - click: {target: {text: "Clear now"}}
     - idle: {duration: 3}

     # --- Verify recent items cleared but the pin survived ---
     - test: recent_cleared
     - test: pin_survives_clear

     - keyboard: {combination: ["alt", "f4"]}

Step 4 -- Iterate in test mode
------------------------------

.. code-block:: bash

   adare experiment run recent-items-analysis -e win11

Review results with ``adare runs info``. Adjust ``idle`` durations or click targets,
or refine SQL queries as needed. Repeat until all four tests pass consistently.

Step 5 -- Production run
------------------------

.. code-block:: bash

   adare experiment run recent-items-analysis -e win11 --production

The production run locks the playbook and generates the official forensic
record. To compare behavior across OS versions, run the same experiment against
additional environments:

.. code-block:: bash

   adare experiment run recent-items-analysis -e win10 --production


See Also
========

- :doc:`/reference/actions` -- complete action reference
- :doc:`/reference/testfunctions/index` -- all available testfunctions by testset
- :doc:`/guide/experiments` -- experiment structure and lifecycle
- :doc:`/guide/diff-analysis` -- combining test-driven analysis with filesystem diffing
- :doc:`/guide/dev-mode` -- interactive playbook development
