*************
CLI Reference
*************

Complete reference for the ADARE command-line interface. The CLI provides access to all framework functionality including project management, environment configuration, experiment execution, VM lifecycle management, and web platform integration.

.. contents:: Quick Navigation
   :local:
   :depth: 2

Global Options
**************

All ADARE commands support the following global options:

* ``--logfile PATH`` - Path to logfile for detailed logging
* ``--verbose`` - Verbose output (loglevel=INFO)
* ``--very-verbose`` - Very verbose output (loglevel=DEBUG)  
* ``--log-level LEVEL`` - Specific log level for logfile
* ``--version`` - Show version information
* ``--help`` - Show help message

Command Groups
**************

Project Management
==================

Projects are top-level containers that organize environments and provide shared resources.

``adare project create <name>``
  Create a new project with the specified name. Creates a directory structure with shared resources like tools and templates.
  
  Options:
    * ``--description TEXT`` - Description of the project

``adare project remove <name>``
  Remove an existing project and all its contents.

``adare project list``
  List all available projects in the system.

Environment Management  
======================

Environments define virtual machine configurations and contain experiments that run on the same VM setup.

``adare environment create <name>``
  Create a new environment within the current project.
  
  Options:
    * ``--project TEXT`` - Name of the project (if not in project directory)
    * ``--with-vm PATH`` - VM file path (OVA) to load automatically during creation

``adare environment load <environment>``
  Load an environment from a YAML configuration file.

  Options:
    * ``--project TEXT`` - Name of the project
    * ``--force`` - Force update of the environment
    * ``--no-copy`` - Keep VM file at original location instead of copying to managed storage.
      Useful for very large VMs. **Important:** The VM file must remain at its original path.
      Only works with local files (URLs are always downloaded).

``adare environment delete <ulid>``
  Delete an environment by its ULID.
  
  Options:
    * ``--force`` - Force deletion without confirmation

``adare environment example [name]``
  Create an example environment (default: win11test) with sample configuration.
  
  Options:
    * ``--project TEXT`` - Name of the project

``adare environment list``
  List all environments in the current project.

``adare environment info <dotnotation>``
  Show detailed information about a specific environment using dotnotation (project.environment).

Experiment Management
=====================

Experiments contain the actual test automation logic using YAML-based playbooks.

``adare experiment create <experiment>``
  Create a new experiment skeleton with template files (playbook.yaml, testset.yml, metadata.yml).
  
  Options:
    * ``--project TEXT`` - Name of the project

``adare experiment load <experiment>``
  Load an experiment configuration.
  
  Options:
    * ``--environment TEXT`` - Name of the environment  
    * ``--force`` - Force update of the experiment
    * ``--project TEXT`` - Name of the project

.. _test-mode-development:

``adare experiment run <experiment>``
  Execute an experiment in the specified environment. By default runs in test mode.

  Options:
    * ``--environment TEXT`` - Name of the environment (if not specified, runs on all configured environments)
    * ``--production`` - Run in production mode with strict integrity checks (default: test mode)
    * ``--debug-screenshots`` - Save screenshots to experiment run directory for debugging
    * ``--preserve-snapshot`` - Create experiment snapshot for preservation (default: only reset to base)
    * ``--project TEXT`` - Name of the project

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

``adare experiment develop <experiment>``
  Run an experiment in development/test mode for iterative development.
  
  Options:
    * ``--environment TEXT`` - Name of the environment (required)
    * ``--project TEXT`` - Name of the project

``adare experiment dev <experiment>``
  Interactive development is now done via ``adare dev start``. See :doc:`/guide/dev-mode` for usage.

``adare experiment example [name]``
  Create an example experiment (default: TrashBinDeleteFile) with complete playbook and test configuration.
  
  Options:
    * ``--project TEXT`` - Name of the project

``adare experiment list``
  List all experiments in the current environment.

  Options:
    * ``--tags TEXT, -t TEXT`` - Filter by tags (comma-separated, e.g. ``tool:Autopsy,goal:tool-test``)

``adare experiment info [name]``
  Show detailed information about a specific experiment.
  
  Options:
    * ``--ulid TEXT`` - Find experiment by ULID
    * ``--dotnotation TEXT`` - Find by dotnotation (project.environment.experiment)

Development Mode
================

Interactive development commands for building and testing playbooks with a live VM session.
Session IDs are auto-detected when only one session is running; use ``-s <session_id>`` when multiple sessions are active.

**Session Management**

``adare dev start``
  Start a new dev mode session. Boots the VM, takes a base snapshot, and prepares for interactive use.

  Options:
    * ``-e, --environment TEXT`` - Environment name (required)
    * ``--project, -p TEXT`` - Project name or path
    * ``--gui-mode [auto|agent|host]`` - GUI execution mode (default: auto)
    * ``--vm-memory INTEGER`` - VM RAM in MB (default: 4096 Linux, 8192 Windows)
    * ``--vm-cpus INTEGER`` - VM CPU count (default: 4)
    * ``--shared-dir TEXT`` - Shared directories in format ``HOST_PATH:VM_PATH`` (repeatable)
    * ``--debug-screenshots`` - Save screenshots for debugging

``adare dev stop``
  Stop a running dev mode session. Shuts down the VM but preserves all resources for later resumption.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)
    * ``--rm`` - Remove all resources (VM, snapshots, database entries) permanently

``adare dev remove``
  Remove a dev mode session and all associated resources. Alias for ``adare dev stop --rm``.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)

``adare dev resume [session_id]``
  Resume a previously stopped session. If no session ID is given, resumes the most recently stopped session.

  Options:
    * ``--project, -p TEXT`` - Project name or path

``adare dev list``
  List all dev mode sessions with their status, experiment, and environment.

  Options:
    * ``--project, -p TEXT`` - Filter by project

``adare dev state``
  Show detailed session state including variables, execution statistics, and available checkpoints.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)

``adare dev cleanup``
  Remove stale sessions that are no longer valid (e.g., orphaned database entries).

  Options:
    * ``--project, -p TEXT`` - Filter by project

**Action and Playbook Execution**

``adare dev action``
  Execute a single action in the running VM session.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)
    * ``-i, --input PATH`` - Action YAML file
    * ``-y, --yaml TEXT`` - Inline YAML string
    * ``--stdin`` - Read action YAML from stdin

``adare dev playbook``
  Execute a playbook (or selected actions from it) in the running VM session.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)
    * ``-f, --file PATH`` - Playbook YAML file
    * ``-u, --url TEXT`` - Playbook URL
    * ``--stdin`` - Read playbook from stdin
    * ``--restore`` - Restore to initial checkpoint before execution
    * ``--indices TEXT`` - Select specific action indices (e.g., ``1-3,5,7-9``, ``S-5``, ``7,23-E``; S=start, E=end)

``adare dev playbook-batch <patterns...>``
  Execute multiple playbooks with automatic checkpoint restoration between each. Supports glob patterns.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)
    * ``--checkpoint-name TEXT`` - Base checkpoint name (default: batch_base)
    * ``--timeout INTEGER`` - Checkpoint restore timeout in seconds (default: 120)

**Reset Commands**

``adare dev reset soft``
  Soft reset: clear session variables only. Fast (less than one second).

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)

``adare dev reset hard``
  Hard reset: full VM restore to the initial snapshot. Slower (10-30 seconds).

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)

**Checkpoint Management**

``adare dev checkpoint create <name>``
  Create a named checkpoint (live VM snapshot) that captures the current VM state and session variables.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)
    * ``-d, --description TEXT`` - Checkpoint description

``adare dev checkpoint restore <name>``
  Restore the VM and session state to a previously created checkpoint.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)

``adare dev checkpoint list``
  List all available checkpoints for the session.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)

``adare dev checkpoint remove <name>``
  Remove a checkpoint and its associated snapshot files.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)

**CV Server Management**

``adare dev cv start``
  Start or restart the CV (computer vision) server for GUI automation with optional debug logging.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)
    * ``--debug / --no-debug`` - Enable or disable CV debug logging (default: keep existing)
    * ``-o, --debug-output PATH`` - Directory for debug screenshots

``adare dev cv stop``
  Stop the CV server.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)

**Testfunction Update**

``adare dev update-testfunctions``
  Reload test functions in the running VM. Packages current test files from the host and uploads them to the VM.

  Options:
    * ``-s, --session TEXT`` - Session ID (auto-detected if only one running)

For workflow patterns and tips, see :doc:`/guide/dev-mode`.

Testfunction Management
========================

Testfunctions are reusable test components that can be shared across experiments.

``adare testfunction create <name>``
  Create a new testfunction with template structure.
  
  Options:
    * ``--project TEXT`` - Name of the project

``adare testfunction remove <name>``
  Remove an existing testfunction.
  
  Options:
    * ``--project TEXT`` - Name of the project

``adare testfunction load <name>``
  Load a testfunction into the current project.
  
  Options:
    * ``--project TEXT`` - Name of the project

``adare testfunction list``
  List all available testfunctions.
  
  Options:
    * ``--project TEXT`` - Name of the project

``adare testfunction show``
  Show testfunctions with optional filtering.
  
  Options:
    * ``--file-name TEXT`` - Filter by file name

``adare testfunction info <dotnotation>``
  Show detailed information about a specific testfunction using dotnotation.

Virtual Machine Management
==========================

VM commands provide lifecycle management for virtual machines used in experiments.

``adare vm list``
  List all VMs currently managed by ADARE, including their status and associated environments.

``adare vm info <vm_id>``
  Get detailed information about a specific VM, including snapshots and configuration.

``adare vm delete <vm_id>``
  Delete a specific VM from the system.
  
  Options:
    * ``--force`` - Force deletion even if VM is in use

``adare vm delete-snapshot <vm_id> <snapshot_name>``
  Delete a specific snapshot from a VM while preserving the VM itself.

**VM Cleanup Sub-commands (adare vm clear)**

``adare vm clear all``
  Clear ALL VMs from the system.
  
  Options:
    * ``--force`` - Force deletion of all VMs (required for confirmation)

``adare vm clear environment <environment_ulid>``
  Clear all VMs associated with a specific environment.
  
  Options:
    * ``--force`` - Force deletion of environment VMs (required for confirmation)

Run Management
==============

Commands for viewing and managing experiment run history and results.

``adare run list``
  List all experiment runs with filtering capabilities.
  
  Options:
    * ``--filter TEXT`` - Filter by dotnotation: [project][.environment][.experiment]

``adare run info <ulid>``
  Show detailed information about a specific experiment run, including results and logs.

Web Platform Integration
========================

Commands for integrating with the ADARE Web platform for sharing experiments and results.

``adare web login``
  Login to the ADARE Web platform to access shared experiments and upload results.

``adare web logout``
  Logout from the ADARE Web platform.

``adare web status``
  Show current login status and connection to the web platform.

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

  Options:
    * ``--include-disk-images`` - Also download disk images
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
  Submit an experiment as a pull request to the shared repository.

  Options:
    * ``--project, -p TEXT`` - Name of the project

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
    * ``--project TEXT`` - Name of the project

MCP Server Testing
==================

Commands for testing MCP (Model Control Protocol) server functionality used for GUI automation.

``adare mcp test-icon``
  Test MCP server icon finding functionality by searching for an icon in a screenshot.
  
  Automatically starts MCP server, finds icon matches, prints coordinates, and stops the server. Optionally saves a marked image showing found locations.
  
  Options:
    * ``--icon PATH`` - Path to icon image file (required)
    * ``--screenshot PATH`` - Path to screenshot image file (required)
    * ``--output PATH`` - Path to save marked image with found locations (optional)
    * ``--host TEXT`` - MCP server host (default: localhost)
    * ``--port INTEGER`` - MCP server port (default: 13109)
    * ``--threshold FLOAT`` - Match threshold 0.0-1.0 (default: 0.6)

``adare mcp test-text <text>``
  Test MCP server text finding functionality by searching for text in a screenshot.
  
  Automatically starts MCP server, finds text matches, prints coordinates, and stops the server.
  
  Arguments:
    * ``text`` - The text string to search for in the screenshot
  
  Options:
    * ``--screenshot PATH`` - Path to screenshot image file (required)
    * ``--host TEXT`` - MCP server host (default: localhost)
    * ``--port INTEGER`` - MCP server port (default: 13109)

System Management
=================

Administrative commands for maintaining the ADARE system.

``adare manage reset-db``
  Reset the ADARE database (use with caution - will delete all experiment data).

``adare manage reset-vm``
  Reset all VMs in the system (use with caution).
  
  Options:
    * ``--force`` - Force deletion of all VMs (required for confirmation)

Help Commands
=============

``adare help``
  Show help for special options and advanced usage patterns.