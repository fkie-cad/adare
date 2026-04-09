********
Dev Mode
********

What is Dev Mode
================

Dev mode provides persistent VM sessions for iterative playbook development. Instead of running full experiments that boot a VM, execute a playbook, and shut down, dev mode keeps a VM running so you can execute playbook steps interactively, inspect results, and refine your automation in real time.

This is essential for developing and debugging playbooks. Without dev mode, every small change would require a full experiment cycle -- boot the VM, install the agent, run the playbook, and shut down. Dev mode eliminates that overhead by maintaining a long-lived session with checkpoints you can restore to when something goes wrong.

Dev mode reuses the standard experiment run infrastructure (VM lifecycle, WebSocket communication, playbook controller) but wraps it in an interactive facade that keeps the VM alive between commands.


Starting a Session
==================

Start a dev mode session with ``adare dev start``:

.. code-block:: bash

   adare dev start -e ubuntu24043

This boots the VM, installs the guest agent, connects via WebSocket, and creates a base checkpoint. The session stays running until you explicitly stop it.

Options
-------

``-e, --environment`` (required)
   Name of the environment (VM) to use.

``-p, --project``
   Project name or path. Defaults to the current directory.

``--gui-mode``
   GUI execution mode: ``auto`` (default), ``agent`` (WebSocket-based), or ``host`` (QMP for QEMU).

``--vm-memory``
   VM RAM in MB. Defaults to 4096 for Linux, 8192 for Windows.

``--vm-cpus``
   VM CPU count. Defaults to 4.

``--shared-dir``
   Mount shared directories between host and guest. Format: ``HOST_PATH:VM_PATH``. Can be specified multiple times. The host directory is created automatically if it does not exist.

``--debug-screenshots``
   Save screenshots for debugging during execution.

.. code-block:: bash

   # Start with custom VM resources
   adare dev start -e win11 --vm-memory 8192 --vm-cpus 8

   # Start with a shared directory
   adare dev start -e ubuntu24043 --shared-dir /tmp/testdata:/mnt/data

   # Start in a specific project
   adare dev start -e ubuntu24043 -p my-forensics-project

Once the session starts, you receive a session ID. If only one session is running, subsequent commands auto-detect it, so you do not need to specify ``-s <session_id>`` every time.


Executing Playbooks
===================

Run a complete playbook in the current session:

.. code-block:: bash

   adare dev playbook -f playbook.yml

The playbook is executed using the same engine as ``adare experiment run``, but within your persistent dev session. Variables carry over between executions, and the VM state is preserved.

Playbook Options
----------------

``-f, --file``
   Path to a playbook YAML file.

``-u, --url``
   Load a playbook from a URL.

``--stdin``
   Read the playbook from standard input.

``--restore``
   Restore to the initial checkpoint before execution. Useful for running a playbook from a clean state without manually resetting.

``--indices``
   Select specific action indices to execute. Supports ranges, comma-separated values, and the special tokens ``S`` (start, i.e. index 1) and ``E`` (end, i.e. the last action).

``-s, --session``
   Session ID. Auto-detected if only one session is running.

Index Selection Examples
------------------------

The ``--indices`` option lets you run subsets of a playbook:

.. code-block:: bash

   # Run only actions 1 through 5
   adare dev playbook -f playbook.yml --indices "1-5"

   # Run actions 3, 7, and 10
   adare dev playbook -f playbook.yml --indices "3,7,10"

   # Run from the start through action 5
   adare dev playbook -f playbook.yml --indices "S-5"

   # Run from action 10 to the end
   adare dev playbook -f playbook.yml --indices "10-E"

   # Run the entire playbook (equivalent to no --indices)
   adare dev playbook -f playbook.yml --indices "S-E"

   # Combine ranges and individual indices
   adare dev playbook -f playbook.yml --indices "1-3,7,15-E"

The tokens ``S`` and ``E`` are case-insensitive (``s`` and ``e`` work too). All indices are 1-based.


Executing Individual Actions
============================

Run a single action without a full playbook:

.. code-block:: bash

   # From an inline YAML string
   adare dev action -y "action: click_icon
   parameter:
     icon: firefox.png"

   # From a YAML file
   adare dev action -i action.yml

   # From standard input
   echo "action: wait
   parameter:
     seconds: 5" | adare dev action --stdin

This is useful for testing one action at a time during development. The action is executed in the current session context with access to all session variables.

Action Options
--------------

``-y, --yaml``
   Inline YAML string defining the action.

``-i, --input``
   Path to a YAML file containing the action.

``--stdin``
   Read the action definition from standard input.

``-s, --session``
   Session ID. Auto-detected if only one session is running.


Checkpoints
===========

Checkpoints are live VM snapshots that capture the full state of the virtual machine, including memory, disk, and session variables. They allow fast iteration: create a checkpoint before risky actions, and restore it when things go wrong.

Creating Checkpoints
--------------------

.. code-block:: bash

   adare dev checkpoint create before-install
   adare dev checkpoint create after-setup -d "Setup complete, ready for tests"

The ``-d, --description`` option adds a human-readable description to the checkpoint.

Listing Checkpoints
-------------------

.. code-block:: bash

   adare dev checkpoint list

Displays a table with checkpoint names, descriptions, creation timestamps, variable counts, and file sizes.

Restoring Checkpoints
---------------------

.. code-block:: bash

   adare dev checkpoint restore before-install

Restores the VM to the exact state at the time the checkpoint was created, including all variable values.

Removing Checkpoints
--------------------

.. code-block:: bash

   adare dev checkpoint remove cleanup-point

Removes the checkpoint and its associated snapshot files from disk.


Reset
=====

Reset commands restore the session to a known state. There are two types of reset:

Soft Reset
----------

.. code-block:: bash

   adare dev reset soft

Resets session variables only. The VM state is untouched. This is nearly instantaneous (less than 1 second) and is useful when you want to clear variable state without waiting for a full VM restore.

Hard Reset
----------

.. code-block:: bash

   adare dev reset hard

Performs a full VM restore to the initial base checkpoint. This resets both the VM state and all variables. Takes 10--30 seconds depending on the VM size. Use this when you need a completely clean slate.


CV Server Management
====================

The computer vision (CV) server handles GUI element detection -- finding icons, text, and UI components in screenshots. You can manage it independently during dev sessions.

Starting or Restarting
----------------------

.. code-block:: bash

   # Start/restart with default settings
   adare dev cv start

   # Enable debug logging
   adare dev cv start --debug

   # Disable debug logging
   adare dev cv start --no-debug

   # Set a custom debug output directory
   adare dev cv start --debug -o /tmp/cv-debug

Stopping
--------

.. code-block:: bash

   adare dev cv stop


Session Management
==================

Listing Sessions
----------------

.. code-block:: bash

   # List all sessions
   adare dev list

   # Filter by project
   adare dev list -p my-project

Displays a table with session IDs, experiment/environment names, status, action counts, and creation timestamps.

Showing Session State
---------------------

.. code-block:: bash

   adare dev state

Shows detailed session information including current variables, available checkpoints, execution statistics, and VM status.

Resuming Sessions
-----------------

Stopped sessions can be resumed without losing state:

.. code-block:: bash

   # Resume the most recently stopped session
   adare dev resume

   # Resume a specific session by ID
   adare dev resume 01K72QABC123

On resume, the VM is restarted and all variables and checkpoints are preserved.

Stopping Sessions
-----------------

.. code-block:: bash

   # Stop session (preserves resources for later resume)
   adare dev stop

   # Stop and remove all resources (VM, snapshots, database entries)
   adare dev stop --rm

   # Alternatively, use the remove command
   adare dev remove

Without ``--rm``, the session can be resumed later. With ``--rm``, the session and all its resources are permanently deleted.

Cleaning Up Stale Sessions
---------------------------

.. code-block:: bash

   adare dev cleanup
   adare dev cleanup -p my-project

Removes sessions that are in an inconsistent state (e.g., the VM was deleted externally).

Updating Test Functions
-----------------------

When you modify test function code on the host, push the changes to the running VM:

.. code-block:: bash

   adare dev update-testfunctions

This repackages the test files from the host and uploads them to the VM. The guest agent extracts them and uses the updated code for subsequent test executions.


Batch Execution
===============

Run multiple playbooks in sequence with automatic checkpoint restoration between each:

.. code-block:: bash

   # Run specific playbooks
   adare dev playbook-batch playbook1.yml playbook2.yml

   # Use glob patterns
   adare dev playbook-batch experiments/*/playbook.yml
   adare dev playbook-batch playbooks/test_*.yml

A base checkpoint is created before execution. After each playbook completes, the VM is restored to this checkpoint, ensuring each playbook starts from the same clean state.

Batch Options
-------------

``--checkpoint-name``
   Name for the base checkpoint. Defaults to ``batch_base``.

``--timeout``
   Checkpoint restore timeout in seconds. Defaults to 120.

``-s, --session``
   Session ID. Auto-detected if only one session is running.


Command Aliases
===============

For convenience, dev mode provides short aliases:

- ``adare dev l`` is equivalent to ``adare dev list``
- ``adare dev res`` is equivalent to ``adare dev reset``
- ``adare dev cp`` is equivalent to ``adare dev checkpoint``


Tips and Workflow Patterns
==========================

Iterative Playbook Development
------------------------------

A typical workflow for building a new playbook:

1. Start a dev session: ``adare dev start -e ubuntu24043``
2. Create a checkpoint at the clean state: ``adare dev checkpoint create clean``
3. Test individual actions: ``adare dev action -y "action: click_icon ..."``
4. When a sequence works, add it to your playbook file
5. Run the playbook to verify: ``adare dev playbook -f playbook.yml``
6. If something goes wrong, restore: ``adare dev checkpoint restore clean``
7. Refine and repeat

Incremental Checkpointing
--------------------------

Use checkpoints as save points during long playbook development:

.. code-block:: bash

   adare dev checkpoint create step1-app-installed
   # ... develop more actions ...
   adare dev checkpoint create step2-configured
   # ... something breaks ...
   adare dev checkpoint restore step2-configured

Testing Subsets of Actions
--------------------------

When debugging a specific part of a playbook, use index ranges to skip actions you know work:

.. code-block:: bash

   # Skip setup (actions 1-10), run only the problematic section
   adare dev playbook -f playbook.yml --indices "11-15"

Using Shared Directories
-------------------------

Share files between host and guest in real time:

.. code-block:: bash

   adare dev start -e ubuntu24043 --shared-dir ./test-data:/mnt/shared

Files placed in ``./test-data`` on the host appear immediately at ``/mnt/shared`` inside the VM, and vice versa. This is useful for transferring test data, collecting artifacts, or sharing scripts.

Session Auto-Detection
----------------------

When only one dev session is running, all commands auto-detect it. You only need to specify ``-s <session_id>`` when multiple sessions are active:

.. code-block:: bash

   # These work when one session is running:
   adare dev state
   adare dev playbook -f playbook.yml
   adare dev checkpoint create my-save

   # With multiple sessions, specify the target:
   adare dev state -s 01K72QABC123


.. seealso::

   :doc:`/guide/experiments`
      Experiment structure and configuration

   :doc:`/reference/actions`
      Available playbook actions

   :doc:`/reference/cli`
      Full CLI reference
