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
   inside a VM (browsing a website, opening a document, deleting a file, etc.).
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

Browse the testsets to find functions that match your artifact type:

- **standard** -- file existence, content matching, hash comparison, file size
- **json** -- key existence, value assertions in JSON files
- **csv** -- column checks, row matching in CSV/TSV files
- **xml** -- XPath queries, element assertions
- **sqlite** -- SQL queries against SQLite databases (browser history, logs)
- **linux** -- syslog entries, package state, service status
- **windows** -- registry keys/values, event log entries, Prefetch files

Defining pass/fail criteria
---------------------------

For each artifact, decide:

- **Must exist** -- e.g., a browser history database must be present after
  visiting a URL.
- **Must contain specific data** -- e.g., the visited URL must appear in the
  ``moz_places`` table.
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
     target_url: "https://example.com/research"
     history_db: "C:\\Users\\adare\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\*.default-release\\places.sqlite"

   tests:
     - name: history_db_exists
       function: standard.file_exists
       parameter:
         dst: "{{ history_db }}"

     - name: url_recorded
       function: sqlite.query_result_contains
       parameter:
         dst: "{{ history_db }}"
         query: "SELECT url FROM moz_places WHERE url LIKE '%example.com%'"
         expected: "{{ target_url }}"

     - name: favicon_stored
       function: standard.file_exists
       parameter:
         dst: "C:\\Users\\adare\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\*.default-release\\favicons.sqlite"

   actions:
     - action: gui.open_application
       parameter:
         name: firefox

     - action: gui.type_text
       parameter:
         text: "{{ target_url }}"

     - action: keyboard.press
       parameter:
         key: enter

     - action: general.wait
       parameter:
         seconds: 5

     - action: test
       parameter:
         name: history_db_exists

     - action: test
       parameter:
         name: url_recorded

     - action: test
       parameter:
         name: favicon_stored

     - action: gui.close_application
       parameter:
         name: firefox

How tests integrate with actions
--------------------------------

Tests are *declared* in the ``tests`` section and *executed* as ``test`` actions
within the ``actions`` sequence. This lets you control exactly when each
assertion runs -- after the relevant action has completed but before subsequent
actions might alter state.

You can also set per-test timeouts for long-running validations:

.. code-block:: yaml

   tests:
     - name: large_db_check
       function: sqlite.query_result_contains
       timeout: 300
       parameter:
         dst: "/path/to/large.db"
         query: "SELECT count(*) FROM events"
         expected: "1000"


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

   adare run info

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


End-to-End Example: Browser History Analysis
=============================================

This example investigates which artifacts Firefox creates on Windows 11 when
a user visits a URL, bookmarks it, and then clears recent history.

Step 1 -- Design the test plan
------------------------------

We want to verify:

1. After visiting a URL, the history database records it.
2. After bookmarking, the bookmark entry exists.
3. After clearing recent history (last hour), the URL is removed from history
   but the bookmark persists.

Step 2 -- Create the experiment
-------------------------------

.. code-block:: bash

   adare experiment create firefox-history-analysis

Step 3 -- Write the playbook
-----------------------------

.. code-block:: yaml
   :caption: experiments/firefox-history-analysis/playbook.yml

   settings:
     idle: 1.5
     timeout: 600
     screenshot:
       format: png

   variables:
     profile_glob: "C:\\Users\\adare\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\*.default-release"
     places_db: "{{ profile_glob }}\\places.sqlite"
     target_url: "https://www.iana.org/help/example-domains"

   tests:
     - name: url_in_history
       function: sqlite.query_result_contains
       parameter:
         dst: "{{ places_db }}"
         query: "SELECT url FROM moz_places WHERE url LIKE '%iana.org%'"
         expected: "{{ target_url }}"

     - name: bookmark_exists
       function: sqlite.query_result_contains
       parameter:
         dst: "{{ places_db }}"
         query: >
           SELECT p.url FROM moz_bookmarks b
           JOIN moz_places p ON b.fk = p.id
           WHERE p.url LIKE '%iana.org%'
         expected: "{{ target_url }}"

     - name: history_cleared
       function: sqlite.query_result_not_contains
       parameter:
         dst: "{{ places_db }}"
         query: >
           SELECT url FROM moz_historyvisits v
           JOIN moz_places p ON v.place_id = p.id
           WHERE p.url LIKE '%iana.org%'
         expected: "{{ target_url }}"

     - name: bookmark_survives_clear
       function: sqlite.query_result_contains
       parameter:
         dst: "{{ places_db }}"
         query: >
           SELECT p.url FROM moz_bookmarks b
           JOIN moz_places p ON b.fk = p.id
           WHERE p.url LIKE '%iana.org%'
         expected: "{{ target_url }}"

   actions:
     # --- Open Firefox and visit URL ---
     - action: gui.open_application
       parameter:
         name: firefox

     - action: gui.type_text
       parameter:
         text: "{{ target_url }}"

     - action: keyboard.press
       parameter:
         key: enter

     - action: general.wait
       parameter:
         seconds: 5

     # --- Verify history was recorded ---
     - action: test
       parameter:
         name: url_in_history

     # --- Bookmark the page ---
     - action: keyboard.hotkey
       parameter:
         keys: ctrl+d

     - action: general.wait
       parameter:
         seconds: 2

     - action: keyboard.press
       parameter:
         key: enter

     - action: general.wait
       parameter:
         seconds: 2

     # --- Verify bookmark exists ---
     - action: test
       parameter:
         name: bookmark_exists

     # --- Clear recent history (last hour) ---
     - action: keyboard.hotkey
       parameter:
         keys: ctrl+shift+delete

     - action: general.wait
       parameter:
         seconds: 2

     - action: gui.click_text
       parameter:
         text: "Last hour"

     - action: gui.click_text
       parameter:
         text: "Clear now"

     - action: general.wait
       parameter:
         seconds: 3

     # --- Verify history cleared but bookmark survived ---
     - action: test
       parameter:
         name: history_cleared

     - action: test
       parameter:
         name: bookmark_survives_clear

     - action: gui.close_application
       parameter:
         name: firefox

Step 4 -- Iterate in test mode
------------------------------

.. code-block:: bash

   adare experiment run firefox-history-analysis -e win11

Review results with ``adare run info``. Adjust wait times, fix image references,
or refine SQL queries as needed. Repeat until all four tests pass consistently.

Step 5 -- Production run
------------------------

.. code-block:: bash

   adare experiment run firefox-history-analysis -e win11 --production

The production run locks the playbook and generates the official forensic
record. To compare behavior across OS versions, run the same experiment against
additional environments:

.. code-block:: bash

   adare experiment run firefox-history-analysis -e win10 --production


See Also
========

- :doc:`/reference/actions` -- complete action reference
- :doc:`/reference/testfunctions/index` -- all available testfunctions by testset
- :doc:`/guide/experiments` -- experiment structure and lifecycle
- :doc:`/guide/diff-analysis` -- combining test-driven analysis with filesystem diffing
- :doc:`/guide/dev-mode` -- interactive playbook development
