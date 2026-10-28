*************
CLI Reference
*************

Complete reference for the ADARE command-line interface. The CLI provides access to all framework functionality including project management, environment configuration, experiment execution, VM lifecycle management, and web platform integration.

Every command also documents itself: ``adare <group> --help`` lists a group's
commands, ``adare <group> <command> --help`` shows all options and examples.

.. contents:: Quick Navigation
   :local:
   :depth: 2

Global Options
**************

All ADARE commands support the following global options:

* ``--logfile PATH`` - Path to logfile for detailed logging
* ``--verbose`` - Verbose output (loglevel=INFO)
* ``--very-verbose`` - Very verbose output (loglevel=DEBUG; also prints tracebacks on errors)
* ``--log-level LEVEL`` - Specific log level for logfile
* ``--output-format``/``--format [rich|plain|json|yaml]`` - Output format for commands that print data
* ``--output-file PATH`` - Also save the structured result to a file
* ``--version`` - Show version information
* ``--help`` - Show help message

Output, errors and exit codes
=============================

Every read-only ``list``/``info``/``show``/``status`` command also accepts
``--json`` and ``--format [rich|plain|json|yaml]`` *after* the subcommand
(``adare env list --json``). Precedence: subcommand flag > global ``--format`` >
``ADARE_FORMAT`` environment variable > auto (``rich`` on a terminal, ``plain``
tab-separated text when stdout is piped). stdout carries only data; logs,
progress, warnings and errors go to stderr. Errors are one concise message
(``{"error": {...}}`` in json mode). Exit codes: ``0`` ok, ``1`` error,
``2`` usage error, ``3`` not found. Details: :doc:`output-formats`.

Projects and aliases
====================

Commands that work on a project use the project in the current directory, or the
one named with ``-p, --project`` (a name or a path). Environments, VMs and
testfunctions are global and need no project.

Group aliases: ``exp`` = ``experiment``, ``environment`` = ``env``,
``tf``/``testfunction`` = ``test``. Within groups, ``l`` = ``list`` and
``rm`` = ``remove`` wherever both exist.

Command Groups
**************

Project Management
==================

Projects are top-level containers that organize experiments and their runs.

``adare project create <name>``
  Create a new project with the specified name. Creates a directory structure with shared resources like tools and templates.

  Options:
    * ``-d, --description TEXT`` - Description of the project

``adare project remove <name>``
  Remove an existing project and all its contents.

``adare project list``
  List all available projects in the system.

``adare status``
  Quick overview: current project, active dev sessions, VM count and database status.

Host Resources
==============

``adare system`` reports what the host has, what ADARE's VMs use and how many more
runs fit (see :doc:`../guide/host-resources`). Every subcommand takes the global
``--format`` option.

``adare system resources``
  Live CPU, memory and disk, and every running QEMU VM with its resident memory and CPU.

``adare system capacity``
  How many more runs of each current environment fit right now, the limiting
  resource, and whether the per-run need is measured or the configured size.

``adare system usage``
  What recent experiment runs actually used: peak RAM, average CPU, disk, duration.

  Options:
    * ``-e, --environment TEXT`` - Only runs of this environment
    * ``--limit INTEGER`` - Number of runs to show (default: 50)

``adare system storage``
  Physical size of ADARE's directories and projects, and run disks without a
  database owner (reclaimable with ``adare vm prune --force``).

  Options:
    * ``--refresh`` - Re-measure instead of using the report cached for a few minutes

``adare system settings [list|get|set|unset]``
  Host limits ADARE keeps to, saved in ``~/.adare/settings.json``. Each resolves
  environment variable > saved setting > default, and ``list`` shows where each
  value comes from. ``set`` validates the value; ``unset`` returns to the default.

  * ``ADARE_MAX_VMS`` (20) - VMs that may run at once across all adare processes
  * ``ADARE_VM_SLOT_TIMEOUT`` (30) - seconds a run waits for a free VM slot
  * ``ADARE_MIN_FREE_DISK_GB`` (10) - GiB that must be free on the project and ADARE
    disks before a run starts; 0 switches the check off
  * ``ADARE_DEV_SESSION_MAX_AGE_DAYS`` (off) - stopped dev sessions unused for longer
    are removed by every experiment run and ``adare vm prune --force``

  Example: ``adare system settings set ADARE_DEV_SESSION_MAX_AGE_DAYS 30``

Environment Management
======================

Environments describe the VM an experiment runs on. They are global (shared by
all projects) and versioned.

``adare env create <name>``
  Create a new environment descriptor (YAML).

  Options:
    * ``--with-vm PATH`` - Disk image to reference in the new environment file (registered by ``adare env load``)

``adare env load <environment>``
  Register an environment from its YAML descriptor. A baked environment's disk is
  copied into managed storage; a recipe environment's disk is built here from the
  declared inputs.

  Options:
    * ``-f, --force`` - Load a changed file as a new version (old version and its runs are kept);
      for a recipe environment this also rebuilds the disk
    * ``--no-copy`` - Keep the VM file at its original location instead of copying it
      to managed storage. Useful for very large VMs. **Important:** the VM file must
      remain at its original path. Only works with local files (URLs are always downloaded).
    * ``--iso PATH`` - Recipe: installer ISO (or a directory to search), e.g. for a consumer-supplied ("BYO") recipe
    * ``--reprovision`` - Recipe: keep the cached base disk but re-run provisioning (retry after a failed step)
    * ``--allow-emulation`` - Allow QEMU TCG software emulation for a foreign guest architecture (slow)

``adare env extend <source>``
  Extend an environment (or VM) into a new environment that reuses the same base
  disk. ``source`` is an environment name, environment ULID or VM name.
  Declarative mode (default) adds post-setup installs on top of the source's;
  interactive mode (``--interactive``, QEMU only) boots an overlay in a GUI window
  for manual installs and stores the result as a new base VM + environment.
  Alias: ``ext``.

  Options:
    * ``-n, --name TEXT`` - Name for the new environment (required)
    * ``-i, --install TEXT`` - Post-setup install as ``name:command`` (repeatable)
    * ``--from-file PATH`` - YAML file with post-setup installations to add
    * ``--interactive/--manual`` - Boot the base in a GUI window for manual customization
    * ``--console`` - With ``--interactive``: also open a REPL that records typed commands as installs
    * ``-d, --description TEXT``, ``-t, --tag TEXT`` - Metadata for the new environment
    * ``-f, --force`` - Overwrite if the new name already exists

``adare env list``
  List all environments (current versions). The **disk** column reports the
  backing disk of each environment's registered VM: ``ok``, ``MISSING`` (registered
  but the disk is gone, so a run will fail at VM setup), or ``-`` (nothing local to
  check). Note this is not the *file path* column, which is the environment's YAML
  descriptor and outlives the disk it points at.

``adare env info <name>``
  Show detailed information about an environment, including a **disk** row with
  the backing disk path and whether it is present.

``adare env remove <name-or-ulid>``
  Remove an environment, including all of its versions. Without ``--force``,
  removal fails while any version has experiment runs or is the only environment
  of an experiment; with ``--force`` those runs are deleted and the experiments are
  kept, without this environment.

``adare env verify <name>``
  Verify an environment by running the built-in ``verify_vm`` experiment on it.

``adare env publish-prepare <name>``
  Prepare a local baked environment for sharing: hashes the local disk and
  rewrites the descriptor to reference the hosted URL plus its sha256.

  Options:
    * ``--vm-url TEXT`` - Published http(s) URL where the disk is hosted (required)
    * ``--verify-url`` - Download the URL and confirm it hash-matches the local disk
    * ``--compress`` - qcow2 only: zstd-compress into a ``<name>-published.qcow2`` sibling first

``adare env recipe-byo <name>``
  Turn a Windows recipe environment's local ISO path into a consumer-supplied ISO
  (``iso_name`` + ``iso_notes``), so it can be published without rehosting the ISO.

Experiment Management
=====================

Experiments contain the actual test automation logic using YAML-based playbooks.

``adare experiment create <experiment>``
  Create a new experiment skeleton with template files.

``adare experiment example [name]``
  Create the example experiment with a complete playbook and test configuration.

``adare experiment load <experiment>``
  Load an experiment configuration into the project database.

  Options:
    * ``-e, --environment TEXT`` - Name of the environment
    * ``-f, --force`` - Force update of the experiment

.. _test-mode-development:

``adare experiment run <experiment>``
  Execute an experiment in the specified environment. By default runs in test mode.

  Options:
    * ``-e, --environment TEXT`` - Name of the environment (if not specified, runs on all configured environments)
    * ``--production, --prod`` - Run in production mode with strict integrity checks (default: test mode)
    * ``--debug-screenshots`` - Save screenshots to experiment run directory for debugging
    * ``-s, --preserve-snapshot`` - VirtualBox: snapshot the final VM state (QEMU runs are discarded; use ``--export-disk-image``)
    * ``--vm-memory INTEGER``, ``--vm-cpus INTEGER`` - VM resources
    * ``--gui-mode [auto|agent|host]``, ``--test-mode [auto|agent|host]`` - Run GUI actions / tests through the guest agent or from the host (QMP/QGA, QEMU only)
    * ``--diff/--no-diff``, ``--diff-mode [auto|guest|host]`` - Filesystem diff (overrides the playbook setting)
    * ``--export-disk-image``, ``--capture-pcap``, ``--export-memory-dump`` - Forensic artifacts (overrides the playbook setting)
    * ``--no-runlog`` - Do not save the adare log to the run directory
    * ``--allow-emulation`` - Allow QEMU TCG software emulation for a foreign guest architecture (slow)

**Batch Execution with Glob Patterns**

ADARE supports advanced batch execution allowing you to run multiple experiments across multiple environments using glob patterns:

* **Run experiment on all environments**::

    adare experiment run test_sqlite

* **Run multiple experiments on specific environment**::

    adare experiment run "test_*" -e ubuntu24043

* **Run multiple experiments on multiple environments**::

    adare experiment run "test_*" -e "ubuntu*"

* **Complex patterns**::

    adare experiment run "file_*" -e "*win*"

**Glob Pattern Support:**
  * ``*`` - Matches any number of characters
  * ``?`` - Matches single character
  * ``[abc]`` - Matches any character in brackets
  * Combinations run alphabetically (environments first, then experiments)

**Batch Features:**
  * Live flow console showing experiment progress
  * Rich summary table with success/failure status
  * Automatic error handling and continuation
  * Duration tracking for each combination

**Test vs Production Mode**

By default, experiments run in **test mode** which is ideal for development:

* **Test Mode (Default)**:

  * Allows continuous modification and testing of playbook files
  * Creates "fake runs" that can be cleaned up with ``adare experiment clean``
  * Skips integrity checks to enable rapid iteration
  * Perfect for developing and debugging experiments

* **Production Mode (--production flag)**:

  * Enforces strict integrity checks for reproducibility
  * Creates real runs that are tracked in the database
  * Prevents modifications to experiments with existing runs
  * Use only when ready for production data collection

**Workflow**: Develop and test in default test mode, then use ``--production`` only when ready for final data collection.
For interactive development against a live VM, use :ref:`dev mode <cli-dev-mode>`.

``adare experiment diff <experiment>``
  Run an experiment in visual diff mode for manual side-by-side comparison
  between OS/software versions: QEMU only, visual actions only, no database
  records. Not to be confused with ``experiment run --diff`` (filesystem diff).

  Options:
    * ``-e, --environment TEXT`` - QEMU-based environment (required)

``adare experiment replicate <ulid>``
  Download a published experiment bundle and run it end to end (experiment,
  testfunction sets, environment and VM disk).

  Options:
    * ``-e, --environment TEXT`` - Environment to use (required if the bundle has more than one)
    * ``--production, --prod`` - Run in production mode
    * ``--skip-run`` - Download and load only

``adare experiment list``
  List all experiments across all projects. Alias: ``l``.

``adare experiment info [name]``
  Show detailed information about a specific experiment.

  Options:
    * ``-u, --ulid TEXT`` - Find experiment by ULID
    * ``-d, --dotnotation TEXT`` - Find by dotnotation (project.environment.experiment)

``adare experiment clone <source> <target>``
  Copy an experiment to create a variation.

  Options:
    * ``-e, --environments TEXT`` - Override environments for the clone (repeatable)

``adare experiment add-env <pattern> <environments...>`` / ``adare experiment remove-env <pattern> <environments...>``
  Add environments to, or remove them from, every experiment matching the name or
  glob pattern. ``remove-env`` alias: ``rm-env``.

  Options:
    * ``-f, --force`` - Proceed even if an experiment would be left without environments

``adare experiment clean <experiment>``
  Delete the finished fake (test-mode) runs of an experiment: their database rows and
  their run folders (see :ref:`run folders <cli-run-folders>`). Fake runs that are
  still pending or running, and dev sessions' runs, are kept.

``adare experiment remove <experiment>``
  Remove an experiment, all its runs and (unless ``--keep-files``) its directory and
  the runs' folders (see :ref:`run folders <cli-run-folders>`). Alias: ``rm``.

  Options:
    * ``-f, --force`` - Remove even if the experiment has production runs
    * ``--keep-files`` - Keep the experiment directory and the run folders (only remove from the database)

**Playbook Sub-commands (adare experiment playbook)**

``adare experiment playbook show <experiment>``
  Print an experiment's playbook YAML (from disk, falling back to the database). Alias: ``cat``.

``adare experiment playbook validate <file>``
  Statically validate a playbook YAML file (parse + schema, no VM).

``adare experiment playbook set <experiment> <file>``
  Validate a playbook file, write it as the experiment's ``playbook.yml`` and
  re-ingest the project database.

  Options:
    * ``--no-backup`` - Do not back up the existing playbook.yml to ``.bak``

Run Management
==============

``adare runs`` views and manages the history and results of experiment runs;
``adare experiment run`` is what starts one.

``adare runs list``
  List all experiment runs with filtering capabilities. Alias: ``l``.

  Options:
    * ``--filter TEXT`` - Filter by dotnotation: [project][.environment][.experiment]

``adare runs info <ulid>``
  Show detailed information about a specific experiment run, including results and logs.

``adare runs remove <ulid>``
  Remove a single experiment run: its database rows and its run folder. A folder
  that fails the run-folder test below is kept and the reason is printed; the
  database rows are removed either way. Alias: ``rm``.

  Options:
    * ``--keep-files`` - Keep the run folder (only remove the database rows)

  The web API equivalent is ``DELETE /api/runs/{ulid}`` (query ``keep_files=true``
  keeps the folder).

``adare runs prune``
  Free disk space in the current project's ``run/`` directory. By default a dry
  run: lists the run folders that nothing refers to, with their sizes and a total,
  and deletes nothing. A folder is kept when

  * a run in the database or a dev session (any status) has it as its folder;
  * a run without a recorded folder (one that failed or was interrupted before it
    got one, e.g. during VM preparation) of the same experiment started within 16 h
    of the folder's timestamp name (a run without an experiment counts for every
    experiment). The window is wide on purpose: run folder names and start times are
    UTC, but older ones were local time;
  * the folder belongs to another registered project: the runs of every registered
    project whose ``run/`` resolves to the same directory (e.g. through a symlink)
    count as well. If one of those projects' databases cannot be read, nothing is
    pruned.

  Options:
    * ``--fake`` - Also target finished fake (test-mode) runs that started more than
      an hour ago: their database rows and their folders. Fake runs that are not
      finished (pending, running, paused, or without a status) and dev sessions'
      runs are skipped
    * ``--older-than DAYS`` - Only targets last changed (fake runs: started) at least
      ``DAYS`` days ago
    * ``-y, --yes`` - Delete exactly the listed targets (fake run rows in one
      transaction first, then the folders)
    * ``--json`` / ``--format`` - Machine-readable output

  .. code-block:: bash

     adare runs prune                       # what would be removed
     adare runs prune --fake --older-than 7 # include fake runs older than a week
     adare runs prune --fake --yes          # delete

.. _cli-run-folders:

**Run folders.** A run's files live in ``<project>/run/<experiment>/<timestamp>``.
``run/`` may also hold your own files, so ADARE only ever deletes a folder there
(``runs remove``, ``runs prune``, ``experiment clean``, ``experiment remove``) when
all of these hold:

* it resolves to a path inside the project's ``run/`` directory, and neither it nor
  its ``<experiment>`` directory is a symlink;
* it is exactly ``run/<experiment>/<timestamp>``, ``<experiment>`` is a known
  experiment, and ``<timestamp>`` looks like ``2025-01-31_14-05-09`` (optionally
  ``_2``, ``_3`` ...);
* it contains a ``logs/`` or ``reporting/`` subdirectory;
* nothing in it (the folder, ``logs/``, ``reporting/``, the files in ``logs/``)
  changed in the last hour.

A folder a dev session refers to (its run folder, or the folder of the run whose id
is the session id; any session status, any project) is never deleted, and when the
dev sessions cannot be read no folder is deleted. Database run paths are matched by
their ``run/<experiment>/<timestamp>`` tail, so a moved project still finds its run
folders. Folders of fake runs that the automatic
post-run cleanup removes from the database stay on disk (useful for debugging) until
``adare runs prune`` deletes them.

.. _cli-dev-mode:

Development Mode
================

Interactive development commands for building and testing playbooks with a live VM session.
Session IDs are auto-detected when only one session is running; use ``-s <session_id>`` when multiple sessions are active.

**Session Management**

``adare dev start``
  Start a new dev mode session. Boots the VM, takes a base snapshot, and prepares for interactive use.

  Options:
    * ``-e, --environment TEXT`` - Environment name (required)
    * ``-p, --project TEXT`` - Project name or path
    * ``--name TEXT`` - Human-friendly session label, selectable later via ``-s <name>``
    * ``--gui-mode [auto|agent|host]``, ``--test-mode [auto|agent|host]`` - Execution modes (default: auto)
    * ``--vm-memory INTEGER`` - VM RAM in MB (default: 4096 Linux, 8192 Windows)
    * ``--vm-cpus INTEGER`` - VM CPU count (default: 4)
    * ``--shared-dir TEXT`` - Shared directories in format ``HOST_PATH:VM_PATH`` (repeatable)
    * ``--debug-screenshots`` - Save screenshots for debugging
    * ``--reuse`` - Attach to the most recent running session of the project instead of booting a new VM
    * ``--watch`` - Open the VM's live screen in the browser (needs ``adare ui start``)

``adare dev stop [session_id]``
  Stop a running dev mode session. Shuts down the VM but preserves all resources for later resumption.

  Options:
    * ``-s, --session TEXT`` - Session ID or name (alternative to the positional argument)
    * ``--rm`` - Remove all resources (VM, snapshots, database entries) permanently
    * ``--all`` - Stop every running session (confirms first unless ``-y, --yes``)

``adare dev remove``
  Remove a dev mode session and all associated resources. Alias for ``adare dev stop --rm``.
  A stopped session keeps a full copy of its VM disk (often 5-50 GiB) until it is removed.

  Options:
    * ``--stopped`` - Remove every stopped or crashed session; lists them with their disk size and asks first
    * ``--older-than AGE`` - With ``--stopped``: only sessions unused for this long (``14d``, ``12h``)
    * ``-y, --yes`` - Skip the confirmation

  Automatic expiry is opt-in: with the ``ADARE_DEV_SESSION_MAX_AGE_DAYS`` setting
  (``adare system settings set``), every experiment run and ``adare vm prune --force`` remove stopped or crashed sessions
  unused for longer than that many days (``adare vm prune`` without ``--force`` lists them).
  Running sessions and sessions whose VM is still up are never removed.

``adare dev resume [session_id]``
  Resume a previously stopped session. If no session ID is given, resumes the most recently stopped session.

  Options:
    * ``--project, -p TEXT`` - Project name or path

``adare dev list``
  List all dev mode sessions with their status, experiment, and environment. Alias: ``l``.

  Options:
    * ``--project, -p TEXT`` - Filter by project

``adare dev state``
  Show detailed session state including variables, execution statistics, and available checkpoints.

``adare dev cleanup``
  Remove stale sessions that are no longer valid (e.g., orphaned database entries).

  Options:
    * ``--project, -p TEXT`` - Filter by project

**Action and Playbook Execution**

``adare dev action``
  Execute a single action in the running VM session.

  Options:
    * ``-i, --input PATH`` - Action YAML file
    * ``-y, --yaml TEXT`` - Inline YAML string
    * ``--stdin`` - Read action YAML from stdin

``adare dev playbook``
  Execute a playbook (or selected actions from it) in the running VM session.

  Options:
    * ``-f, --file PATH`` - Playbook YAML file
    * ``-u, --url TEXT`` - Playbook URL
    * ``--stdin`` - Read playbook from stdin
    * ``--restore`` - Restore to initial checkpoint before execution
    * ``--indices TEXT`` - Select specific action indices (e.g., ``1-3,5,7-9``, ``S-5``, ``7,23-E``; S=start, E=end)

``adare dev playbook-batch <patterns...>``
  Execute multiple playbooks with automatic checkpoint restoration between each. Supports glob patterns.

  Options:
    * ``--checkpoint-name TEXT`` - Base checkpoint name (default: batch_base)
    * ``--timeout INTEGER`` - Checkpoint restore timeout in seconds (default: 120)

**Playbook Authoring**

``adare dev agent``
  Drive a VM toward a natural-language goal with the vision-LLM GUI agent
  (configured with ``adare vlm``). Attach to a session with ``-s`` or boot a
  fresh VM from an environment with ``-e``. With ``-o`` or ``--as-experiment`` the
  run is recorded as a replayable playbook and, by default, verified by replay.
  Not to be confused with ``adare agent`` (coding-agent skills).

  Options:
    * ``--goal TEXT`` / ``--goal-file PATH`` - The goal
    * ``-e, --environment NAME`` - Boot a fresh VM, drive it, tear it down (``--keep`` to leave it running)
    * ``-o, --out PATH`` / ``--as-experiment NAME`` - Record the playbook to a file / scaffold an experiment
    * ``--plan`` - Decompose the goal into verified sub-goals with checkpoint backtracking
    * ``--ground`` - Auto-start the LocateAnything grounding server for precise clicks
    * ``--step, --interactive`` - Approve each action before it runs
    * ``--video`` - Record the run to ``run.mp4``

``adare dev author``
  Author a playbook from human-written text steps (no LLM planner); LocateAnything
  grounds described clicks.

  Options:
    * ``--script-file PATH`` - Text steps, one action per line
    * ``-i, --interactive`` - Author step by step in a REPL
    * ``-o, --out PATH`` - Where to write the playbook

``adare dev author-ai``
  Let a cloud vision model author an ``actions:`` playbook for ``--goal`` from the
  current screen; ``--replay`` verifies it live and repairs failures.

``adare dev mcp``
  Serve the session VM as a GUI-automation MCP server (blocking) so an external
  MCP client can author playbooks. Session-scoped; for the whole ADARE lifecycle
  use ``adare mcp serve``.

  Options:
    * ``--host TEXT``, ``--port INTEGER`` - Bind address (default: 127.0.0.1:13110)
    * ``-o, --out-dir PATH`` - Directory for recorded playbooks

**Reset Commands** (alias: ``res``)

``adare dev reset soft``
  Soft reset: clear session variables only. Fast (less than one second).

``adare dev reset hard``
  Hard reset: full VM restore to the initial snapshot. Slower (10-30 seconds).

**Checkpoint Management** (alias: ``cp``)

``adare dev checkpoint create <name>``
  Create a named checkpoint (live VM snapshot) that captures the current VM state and session variables.

  Options:
    * ``-d, --description TEXT`` - Checkpoint description

``adare dev checkpoint restore <name>``
  Restore the VM and session state to a previously created checkpoint.

``adare dev checkpoint list``
  List all available checkpoints for the session.

``adare dev checkpoint remove <name>``
  Remove a checkpoint and its associated snapshot files.

**CV Server Management**

``adare dev cv start``
  Start or restart the CV (computer vision) server for GUI automation with optional debug logging.

  Options:
    * ``--debug`` - Enable CV debug logging
    * ``-o, --debug-output PATH`` - Directory for debug screenshots

``adare dev cv stop``
  Stop the CV server.

**Testfunction Update**

``adare dev update-testfunctions``
  Reload test functions in the running VM. Packages current test files from the host and uploads them to the VM.

All commands in this group that act on a session take ``-s, --session TEXT``
(auto-detected if only one session is running). For workflow patterns and tips,
see :doc:`/guide/dev-mode`.

Testfunction Management
========================

Testfunctions are reusable assertions that a playbook's ``tests:`` block calls by
dotnotation (``<collection>.<function>``; a bare name means ``standard.<name>``).
``adare test`` is aliased as ``adare tf`` and ``adare testfunction``.

The discovery commands (``list``, ``search``, ``info``, ``catalog``) read the
collection sources directly. They need no project and no database, include the
host-native ``visual`` collection, and show exact per-function types, defaults and
parameter docs (from the function's ``Args:`` docstring). When stdout is piped they
print tab-separated text; use ``--json`` for structured output.

``adare test search "<goal>"``
  Find the testfunction for a goal, e.g. ``"deleted file is gone"``. Ranks by name,
  summary and parameter docs with synonyms (deleted/gone/removed, registry/hive, ...).
  Each result includes a ready-to-paste ``tests:`` example. Alias: ``find``.

  Options:
    * ``--collection/--set TEXT``, ``--category TEXT``, ``--os [windows|linux|any]`` - Filters
    * ``--limit, -n INTEGER`` - Maximum results (default 8)

``adare test list``
  List every testfunction with its parameters (optional ones marked ``?``).
  Collections bundled with ADARE but not yet synced are flagged. Aliases: ``l``, ``ls``.

  Options:
    * ``--collection/--set TEXT``, ``--category TEXT``, ``--os [windows|linux|any]`` - Filters
    * ``--full`` - Structured output with every field (default: compact)

``adare test info <dotnotation>``
  Signature, parameter types/defaults/docs, the current installed version and an
  example ``tests:`` entry. Unknown names suggest close matches.

  Options:
    * ``--example`` - Print only the ``tests:`` YAML block

``adare test catalog``
  Export the catalog of the collections bundled with ADARE (machine-independent,
  ignores local collections).

  Options:
    * ``--markdown`` - Render a Markdown reference (used for the agent skill reference)

``adare test create <name>``
  Create a new testfunction collection from a template.

  Options:
    * ``--project, -p TEXT`` - Name of the project

``adare test validate <path>``
  Offline contract check of a collection directory or ``.py`` file. Warns (without
  failing) when a function or parameter lacks documentation.

``adare test dry-run <collection>.<function>``
  Execute one ``FILE_BASED``/``FILE_CONTENT`` testfunction against a local sample.

  Options:
    * ``--param, -P TEXT`` - Parameter as ``key=value`` (repeatable)
    * ``--file, -f TEXT`` - Local sample file used as the ``dst`` parameter
    * ``--path TEXT`` - Collection dir/.py to load

``adare test load <name>``
  Register a collection in the global database.

  Options:
    * ``--force, -f`` - Overwrite a testfunction used in experiments (deletes the associated runs)

``adare test sync``
  Hash-based create/update of all bundled collections (``visual`` is host-native and never synced).

``adare test versions <collection>[.<function>]``
  Version history of a collection or one function. Editing only a docstring does
  not bump a function's version. Alias: ``v``.

``adare test remove <name>``
  Remove a collection file. Alias: ``rm``.

Virtual Machine Management
==========================

ADARE knows two kinds of VM:

* **Registered VMs** are the disks environments run on. ``adare env load``
  registers them; ``adare vm list`` shows them.
* **VM instances** are what experiment runs boot from a registered VM: on QEMU
  one throwaway instance per run, on VirtualBox a reusable pool.
  ``adare vm usage`` shows them.

``info`` and ``remove`` take either kind, by name or ID, and detect which it is.

**Creating and checking VMs**

``adare vm create <os_name>``
  Create a new ADARE-ready VM (QEMU) from scratch: unattended install, GUI-automated
  install, or manual install depending on the OS profile. ``adare vm profile list``
  shows every target. See :doc:`../guide/vm-image-creation` for the full guide.

  Options (selection):
    * ``--iso PATH`` - Installer ISO (required for Windows)
    * ``--name TEXT``, ``--disk-size TEXT``, ``--ram INTEGER``, ``--cpus INTEGER`` - VM shape
    * ``--setup [bare|base|full|agent]`` - What ADARE adds to the guest (default: full)
    * ``--recipe/--no-recipe`` - Emit a declarative recipe environment instead of a baked disk
    * ``--byo-iso`` - Recipe, Windows only: consumers supply the ISO themselves
    * ``--interactive`` - Boot the VM after install for manual software installation
    * ``--record``, ``--relearn`` - GUI-automated installs: re-record the install playbook with the vision agent
    * ``--display`` - Show the installer in a window (watch only)
    * ``--arch [x86_64|aarch64]``, ``--allow-emulation`` - Cross-architecture installs

``adare vm profile list`` / ``show <name>`` / ``add <file.yml>`` / ``remove <name>``
  Manage the OS profiles ``vm create`` can install: list the built-in and custom
  ones, show one, or add/remove a custom profile. Aliases: ``l``, ``rm``.

``adare vm test <target>``
  Test ADARE compatibility of an ``.ova``/``.ovf`` file or a registered VM: prepare
  it, mount shared directories, start adarevm, take a screenshot and click.
  On a registered (QEMU) VM the agent is installed, started and connected exactly as
  in an experiment run (same wheels, shares, ``config.json`` and agent token), and the
  VM passes only when that works; the agent's own screenshot and click are reported but
  do not fail the test, since experiments drive the GUI from the host. A failed test
  keeps its run directory with adarevm's logs under ``~/.adare/state/vm-test/run/``.

  Options:
    * ``-p, --platform [linux|windows]`` - Required for OVA files; auto-derived for registered VMs
    * ``--keep-vm`` / ``--remove-vm`` - What to do with the test VM afterwards
    * ``--log-file FILE`` / ``--no-log`` - Debug log location

``adare vm doctor``
  Report which system tools VM creation needs are available (qemu, OVMF, swtpm,
  libvirt binding, ...). Never installs anything.

``adare vm watch <name>``
  Watch a running VM's live screen in the browser via VirtualSpice (needs ``adare ui start``).

  Options:
    * ``--view-only/--interactive`` - Read-only view (default) or allow input

**Registered VMs and instances**

``adare vm list``
  List registered VMs. Alias: ``l``.

``adare vm info <name-or-id>``
  Show a registered VM or a VM instance.

``adare vm usage``
  Show VM instances (running experiment runs; VirtualBox pool) and their usage.

``adare vm remove <name-or-id>``
  Remove a registered VM or a VM instance. Alias: ``rm``.

  A registered VM is the disk environments run on, so removing it also removes
  those environments, every version -- the same end state as
  ``adare env remove``. The command lists what goes (environments, stopped
  instances, runs, the disk) and asks first. It refuses:

  * while an instance of the VM is running (an experiment run or dev session uses it);
  * when an environment on it also has versions on another VM -- removing the
    environment would take that VM along; use ``adare env remove`` for that;
  * without ``--force``, when runs used its environments (as ``adare env remove``).

  Disks inside ADARE's managed storage are deleted; disks elsewhere are kept.

  Options:
    * ``-f, --force`` - Instance: remove it even if running. Registered VM: also
      delete the runs that used its environments (experiments are kept, detached)
    * ``-y, --yes`` - Skip the confirmation prompt (required when stdin is not a terminal)

``adare vm remove --stopped | --experiment <id> | --all --force | --env <ulid> --force``
  Remove instances in bulk: all stopped ones, those of an experiment, all of
  them (running too), or those of an environment's VM. Registered VMs stay.

``adare vm prune``
  Reclaim what crashed runs left behind (instances, run files, orphaned base
  disks, stale recipe caches). Dry run unless ``--force``. Also lists registered
  VMs no environment uses; those are never deleted by prune -- remove one with
  ``adare vm remove <name>``. It also reports the disk stopped dev sessions hold
  (removed with ``adare dev remove --stopped``).

  Runs refuse to start while a filesystem they write to (project ``run/``, ADARE
  state) has less than the ``ADARE_MIN_FREE_DISK_GB`` setting free (default 10; 0 disables it).

  Options:
    * ``--sockets`` - Also reap dead QMP/QGA sockets

``adare vm reset``
  Remove the instances of every VM, running or not. Registered VMs stay.

  Options:
    * ``-f, --force`` - Skip the confirmation prompt

``adare vm snapshot list`` / ``adare vm snapshot remove <instance_id> <snapshot_name>``
  List or delete a VM instance's snapshots (VirtualBox). ``list`` takes
  ``-i, --instance`` to show one instance.

Vision-LLM Configuration
========================

``adare vlm`` configures the OpenAI-compatible vision-LLM endpoint used for GUI
automation (``adare dev agent``, GUI-automated ``vm create`` installs) and by
``adare chat``. Settings are saved as named profiles; an ``ADARE_VLLM_*``
environment variable still overrides the active profile for a single run.

``adare vlm use [target]``
  Switch profile: with no argument an interactive picker; with a profile name,
  activate it; with a preset (``ollama-cloud``, ``local``), create and activate one.

  Options:
    * ``--api-key TEXT``, ``--base-url TEXT``, ``--model TEXT``, ``--name TEXT`` - Preset overrides
    * ``--no-verify`` - Skip the live endpoint/token check

``adare vlm create``
  Create a profile with a guided menu (provider, endpoint, model, coordinate space, key, name).

``adare vlm list`` / ``adare vlm show``
  List saved profiles (active one marked) / show the resolved config and where each
  value comes from. ``list`` aliases: ``l``, ``ls``.

``adare vlm save <name>``
  Snapshot the currently effective config as a profile (``--no-activate`` to keep the current one active).

``adare vlm remove <name>``
  Delete a profile. Alias: ``rm``.

``adare vlm doctor``
  Preflight the active VLM: checks the endpoint is reachable and detects which
  coordinate convention the model answers in, recommending ``ADARE_VLLM_COORD_SPACE``.

``adare vlm pull-grounding``
  Pre-download the LocateAnything grounding weights (~7.3 GB) used by
  ``adare dev agent --ground``, instead of paying the download on the first run.
  Needs ``uv sync --extra grounding``, an ``HF_TOKEN`` and the accepted NVIDIA license.

  Options:
    * ``--model TEXT`` - HF id or local path (default: ``ADARE_LOCATE_MODEL_PATH`` or ``nvidia/LocateAnything-3B``)

Local Web UI
============

``adare ui`` runs the local web UI (FastAPI + VirtualSpice), which also serves
the live VM viewer used by ``adare vm watch`` and ``adare dev start --watch``.
While it runs it records a host usage sample per minute for the *System* page,
and its terminal panel runs Claude Code or a shell on this host (see :doc:`../guide/web-ui`).

``adare ui start``
  Start the ADARE web UI (FastAPI + VirtualSpice) and open it in the browser.
  VirtualSpice runs with its own data dir (``~/.adare/virtualspice``, log
  ``adare-server.log`` there), so it coexists with the VirtualSpice app; one
  already answering on the spice port is used instead of starting another.

  Options:
    * ``--port INTEGER``, ``--host TEXT`` - Bind address
    * ``--spice-port INTEGER`` - VirtualSpice backend port
    * ``--dev`` - Development mode with auto-reload
    * ``--no-browser`` - Don't open the browser

``adare ui status``
  Show the status of the local web services (FastAPI, VirtualSpice, frontend build).

``adare ui build``
  Build the web frontend (``pnpm build`` in ``adare-web``).

``adare ui install-spice``
  Download and verify the VirtualSpice binary (``--force`` to re-download).

ADARE Web Platform
==================

``adare web`` talks to the shared ADARE Web platform: log in, download, publish
and submit experiments, testfunctions and environments.

``adare web login``
  Login to the ADARE Web platform to access shared experiments and upload results.

``adare web logout``
  Logout from the ADARE Web platform.

``adare web status``
  Show the current login status on the web platform.

**Web Download Sub-commands (adare web download)**

``adare web download experiment <ulid>``
  Download an experiment from the web platform by its ULID.

``adare web download testfunction <name>``
  Download a testfunction from the web platform.

  Options:
    * ``--version, -v INTEGER`` - Specific version to download (default: latest)

``adare web download environment <name>``
  Download an environment configuration from the web platform.

``adare web download bundle <ulid>``
  Download an experiment bundle (experiment plus all dependencies) from the web platform.
  ``adare experiment replicate`` downloads a bundle and runs it in one step.

  Options:
    * ``--project, -p TEXT`` - Name of the project

``adare web publish <ulid>``
  Publish an experiment run to the web platform for sharing with the community.

  Options:
    * ``--project, -p TEXT`` - Name of the project

**Web Check Sub-commands (adare web check)**

``adare web check experiment <ulid>``
  Check if an experiment exists on the server.

``adare web check run <ulid>``
  Check if an experiment run exists on the server.

**Web Submit Sub-commands (adare web submit)**

``adare web submit experiment <name>``
  Submit an experiment as a pull request to the shared repository. Every test
  function and environment the experiment references is checked against the
  server's published catalog first; if one is unresolvable the submission fails
  and no pull request is created. See :ref:`experiment-dependency-preflight`.

  Options:
    * ``--project, -p TEXT`` - Name of the project
    * ``--skip-dependency-check`` - Submit even if a referenced test function or
      environment is not resolvable in the server's published catalog

``adare web submit testfunction <name>``
  Submit a testfunction as a pull request to the shared repository.

  Options:
    * ``--project, -p TEXT`` - Name of the project

``adare web submit environment <name>``
  Submit an environment as a pull request to the shared repository.

  Options:
    * ``--project, -p TEXT`` - Name of the project

``adare web sync``
  Synchronize all environments and experiments with the web platform.

  Options:
    * ``--project, -p TEXT`` - Name of the project

AI Assistants
=============

``adare skills install``
  Install ADARE's workflow skills (``skills/adare-*``) for AI coding agents by
  symlinking them into the agent's skill directories. Real directories are never
  touched; symlinks that point elsewhere are only re-pointed with ``--force``.
  Alias: ``setup``.

  Options:
    * ``--client [claude|opencode|all]`` - Target agent(s) (default: all)
    * ``--scope [user|project|all]`` - ``user`` = ``~/.claude/skills`` and
      ``~/.config/opencode/skills``; ``project`` = ``.claude/skills`` and
      ``.opencode/skills`` in the current directory (default: user)
    * ``--copy`` - Copy instead of symlink
    * ``--force`` - Re-point symlinks that point elsewhere
    * ``--dry-run`` - Show what would change

``adare skills status``
  Show where the skills are installed and whether each link is current
  (``ok``, ``missing``, ``stale``, ``foreign-link``, ``conflict``).

``adare mcp serve``
  Serve the whole ADARE lifecycle (projects, environments, experiments, runs, VMs,
  dev sessions, playbook authoring) as MCP tools. Register it with Claude Code via
  ``claude mcp add adare -- adare mcp serve``.

  Options:
    * ``--transport [stdio|http]`` - stdio (default; the client launches the process) or http
    * ``--host TEXT``, ``--port INTEGER`` - HTTP bind address (default: 127.0.0.1:13112)

``adare chat``
  Control ADARE conversationally in an embedded agentic REPL, using the endpoint
  configured with ``adare vlm`` and the same tools ``adare mcp serve`` exposes.

  Options:
    * ``--model TEXT`` - Chat model (default: ``$ADARE_CHAT_MODEL``, else the vlm model)
    * ``--base-url TEXT`` - OpenAI-compatible endpoint (default: the active vlm profile)
    * ``--tool-protocol [native|json|auto]`` - Tool-call protocol (default: auto)

``adare tui``
  Open the Textual terminal UI.

Debugging Tools
===============

``adare debug`` holds low-level tools for testing GUI detection and the guest
agent directly.

``adare debug cv test-icon``
  Start a CV server, find an icon in a screenshot, print the coordinates of all
  matches and stop the server.

  Options:
    * ``--icon PATH``, ``--screenshot PATH`` - Inputs (required)
    * ``--output PATH`` - Save a marked image showing the found locations
    * ``--threshold FLOAT`` - Match threshold 0.0-1.0 (default: 0.6)
    * ``--host TEXT``, ``--port INTEGER`` - CV server address (default: localhost:13109)
    * ``--mcplog PATH`` - Save the CV server log

``adare debug cv test-text <text>``
  Same for a text string, using OCR.

``adare debug cv get-all-text``
  Print all text OCR detects in a screenshot, with coordinates and confidence.

  Options:
    * ``--screenshot PATH`` - Screenshot (required)
    * ``--format TEXT`` - ``json`` (default) or ``csv``

``adare debug ws action <file>``
  Execute the actions in a YAML file on a running adarevm over WebSocket.

  Options:
    * ``--host TEXT``, ``--port INTEGER`` - adarevm address (default: 127.0.0.1:18765)
    * ``--vm-instance TEXT`` - Look up the port from a VM instance name
    * ``--token TEXT`` - Agent token (``agent_token`` in the run's config.json)
    * ``--continue-on-error`` - Keep going after a failed action

``adare debug ws example <file>``
  Write an example action YAML file.

Icon Library
============

Inspect the Windows icon library and extract icons from a connected target. See
:doc:`../guide/icon-library` for the full guide.

``adare icons list``
  List every icon term in the registry with its resolver spec. Aliases: ``l``.

  Options:
    * ``--os-key TEXT`` - OS profile / build key for cache separation (default: windows)

``adare icons dump-all``
  Resolve every registry term on a connected target, writing the PNGs plus an
  HTML contact sheet to the per-OS icon cache directory. Aliases: ``dump``.

  Options:
    * ``--host TEXT`` - adarevm host (default: localhost)
    * ``--port INTEGER`` - adarevm WebSocket port (default: 18765)
    * ``--os-key TEXT`` - OS profile / build key for cache separation (default: windows)
    * ``--force`` - Re-extract even if a cached PNG already exists

System Management
=================

Administrative commands for maintaining the ADARE system.

Database
--------

ADARE keeps a global database (VMs, environments, test functions, project
registry) plus one database per project (experiments, runs). Schema changes are
carried by ordered migrations that are applied automatically whenever a
database is opened -- see :doc:`../architecture/database-migrations`.

``adare db status``
  Report whether the global database exists, is accessible, and whether any
  schema migrations are still pending. Pending migrations are informational:
  they are applied on next use.

``adare db migrate``
  Apply pending schema migrations to the global database and to every
  registered project database, printing each migration as it is applied.
  Re-running reports that nothing is pending. Safe to run at any time; it is
  part of ``make install`` and ``make update``.

``adare db init``
  Initialize the database system (directories + global database).

``adare db repair``
  Reinitialize the global database and apply pending migrations.

``adare db reset``
  Delete the global database (use with caution - VMs, environments and the
  test function registry are lost).

``adare db clean-install``
  Recreate the global database from scratch (DANGER: deletes all global data).

  Options:
    * ``--force``, ``-f`` - Skip the confirmation prompt

``adare db compact [--dry-run] [--all] [-p PROJECT]``
  Shrink a project database. Action results recorded before results were
  stored without images keep a base64 copy of every screenshot in
  ``action_execution.result_data`` -- on a long-lived project that is most of
  the file (tens of GB). The screenshots themselves stay on disk in each run's
  ``reporting/screenshots`` folder; ``compact`` only drops the database copy,
  then runs ``VACUUM`` so the file actually gets smaller. Run it once on a
  project that predates the change, or whenever ``ls -l .adare/`` looks too big.

  * Only image payloads are removed, and a row's images only when every one of
    them is byte-for-byte identical to the PNG its ``screenshot_path`` names
    (the base64 data is decoded and compared with the file). Relative paths are
    resolved against the run folder under the project's *current* location (a
    moved project works). Rows whose screenshot file is missing, differs, or
    that have no ``screenshot_path`` are left byte-for-byte unchanged and
    counted as kept. A removed image is replaced by the same
    ``<omitted: N chars of png data>`` marker new rows get.
  * Nothing else is ever removed: long text that is not an image (command
    output, ...) stays as it is; such rows are only counted.
  * Refuses to touch a database that may be written to while it runs; nothing
    is changed then, and the exit code is 1:

    - another process holds the write lock (it waits 2 s for it);
    - a run of the project has not ended (``RUNNING``, ``PENDING``, ``PAUSE``)
      and showed activity in the last 30 minutes: its start or creation time,
      or the modification time of its run folder or of a file in its ``logs/``
      folder. Unfinished runs without such activity were left behind by a crash;
      they are ignored and their number is reported;
    - for every database: a dev session marked running whose VM is alive (asked
      from the hypervisor, as ``adare dev cleanup`` does) or whose state changed
      in the last 30 minutes.

    The message names the run or dev session. Stop ``adare ui`` as well.
  * ``VACUUM`` writes a temporary copy of the database and, in WAL mode, passes
    all of it through the ``-wal`` file: it needs free space of twice the
    remaining data plus 10 % next to the database and in the temporary directory
    (``TMPDIR``) when that is on another volume. With less it is skipped (the
    row rewrite still stands) and the report says so. Rows are rewritten and
    committed in small batches, so an interrupted run keeps its progress and can
    simply be started again.
  * A registered project whose directory or database file is gone is reported
    as ``missing``; nothing is created on disk, and the other databases are
    still processed.

  Reports per database: rows stripped, rows kept (screenshot file missing /
  differs), rows with oversized non-image text (kept), stale runs ignored,
  bytes freed by the rewrite, size before and after (database file + ``-wal``)
  and the duration.

  Options:
    * ``--dry-run`` - Open the database read-only and report what would be
      reclaimed (row counts and bytes); write nothing. A dry run is not refused
      for activity; its message says when a real run would be.
    * ``--all`` - Every registered project database plus the global one
      (default: the project of the current directory)
    * ``-p``, ``--project`` - Project name or path
    * ``--json`` / ``--format`` - Machine-readable output::

        {"dry_run": false, "ok": true, "databases": [
          {"label": "T2F", "path": ".../.adare/project.db.sqlite3",
           "status": "compacted", "message": null,
           "rows": {"examined": 2000, "stripped": 1985,
                    "kept_missing_file": 10, "kept_mismatch": 5,
                    "non_image_kept": 3},
           "stale_runs_ignored": 0,
           "reclaimable_bytes": 341266000, "free_pages_bytes": 341000000,
           "vacuum": {"done": true, "message": null},
           "size_before": {"db": 345964544, "wal": 0},
           "size_after": {"db": 2920448, "wal": 0},
           "duration_seconds": 0.32}]}

    ``status`` is ``compacted``, ``dry-run``, ``in-use``, ``missing`` or ``error``.

``adare db check [--all] [-p PROJECT]``
  Read-only health check of a database:

  * ``PRAGMA quick_check`` - page-level integrity. Exit code 1 when it finds
    a problem (or the file is not a database): restore the database from a
    backup.
  * ``PRAGMA foreign_key_check``, counted per (table, parent table). It works
    although ADARE runs with foreign-key enforcement off.
  * Orphaned rows, counted only (exit code 0), never changed:

    - action executions with no run row (``action_execution_without_run``).
      Dev-session consoles record their actions under a console ULID that no
      run row has, and run deletions of older versions left their runs'
      executions behind; the two cannot be told apart, so these rows are kept;
    - run-file and log-file rows no run references
      (``experiment_run_files_unreferenced``, ``log_file_unreferenced``). The
      ``delete_orphan_run_rows`` migration removed those older versions left
      once; run deletion now removes them, so new ones are not expected;
    - action executions whose playbook item is gone
      (``action_execution_dangling_playbook_item``; items are replaced when an
      experiment is loaded again).

  A registered project whose directory or database file is gone is reported
  with status ``missing``; nothing is created on disk.

  Options:
    * ``--all`` - Every registered project database plus the global one
    * ``-p``, ``--project`` - Project name or path
    * ``--json`` / ``--format`` - ``{"ok": ..., "databases": [{"label", "path",
      "status", "integrity_ok", "problems", "foreign_key_violations": [{"table",
      "parent", "count"}], "orphans": {name: count}, "message"}]}``;
      ``status`` is ``checked`` or ``missing``

VM runtime
----------

``adare runtime refresh``
  Refresh the VM runtime files in the current project.

``adare runtime build``
  Build fresh VM runtime wheels (``adarelib``, ``adarevm``) for the current
  project.

Moved Commands
==============

These commands moved; the old names still work (hidden from ``--help``) and
print a pointer to the new name on stderr. They will be removed in a future release.

.. list-table::
   :header-rows: 1

   * - Old
     - New
   * - ``adare run list|info|remove``
     - ``adare runs list|info|remove|prune``
   * - ``adare agent setup|status``
     - ``adare skills install|status``
   * - ``adare web start|build|install-spice``
     - ``adare ui start|build|install-spice``
   * - ``adare web services``
     - ``adare ui status``
   * - ``adare cv ...`` / ``adare ws ...``
     - ``adare debug cv ...`` / ``adare debug ws ...``
   * - ``adare os-profile ...``
     - ``adare vm profile ...``
   * - ``adare vm gui-doctor``
     - ``adare vlm doctor``
   * - ``adare dev grounding-pull``
     - ``adare vlm pull-grounding``
   * - ``adare test show -n <collection>``
     - ``adare test list --collection <collection>``

``adare server start`` and ``adare help`` were removed: the former duplicated
``adare web start`` (now ``adare ui start``) and failed to start, the latter had no subcommands.
