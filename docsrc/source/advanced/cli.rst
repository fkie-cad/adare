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

``adare experiment dev <experiment>`` **[NOT IMPLEMENTED]**
  Interactive development mode with web-based interface (currently not functional).
  
  *Note: This feature is under development and not currently working.*
  
  Options:
    * ``--environment TEXT`` - Name of the environment (required)
    * ``--project TEXT`` - Name of the project
    * ``--port INTEGER`` - Port for the web interface (default: 8080)

``adare experiment example [name]``
  Create an example experiment (default: TrashBinDeleteFile) with complete playbook and test configuration.
  
  Options:
    * ``--project TEXT`` - Name of the project

``adare experiment list``
  List all experiments in the current environment.

``adare experiment info [name]``
  Show detailed information about a specific experiment.
  
  Options:
    * ``--ulid TEXT`` - Find experiment by ULID
    * ``--dotnotation TEXT`` - Find by dotnotation (project.environment.experiment)

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

``adare web download environment <name>``
  Download an environment configuration from the web platform.

``adare web publish <ulid>``
  Publish an experiment run to the web platform for sharing with the community.

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

Common Usage Patterns
*********************

Creating and Running Your First Experiment
===========================================

1. Create a project::

    adare project create my-forensics-project
    cd my-forensics-project

2. Load an environment::

    adare environment load win11-config.yml

3. Create an experiment::

    adare experiment create file-deletion-test

4. Edit the generated playbook.yaml and testset.yml files

5. Run the experiment::

    adare experiment run file-deletion-test -e win11

Interactive Development Workflow **[NOT CURRENTLY AVAILABLE]**
================================================================

*Note: Interactive development mode is currently not implemented and these commands will not work.*

For experiment development, use the standard workflow:

1. Create and edit playbooks manually using a text editor
2. Test with development mode::

    adare experiment develop file-deletion-test -e win11

3. Run the completed experiment::

    adare experiment run file-deletion-test -e win11

Working with Shared Content
===========================

1. Login to ADARE Web::

    adare web login

2. Download a shared experiment::

    adare web download experiment 01ARZ3NDEKTSV4RRFFQ69G5FAV

3. Run the downloaded experiment::

    adare experiment run TrashBinDeleteFile -e win11

VM Cleanup and Maintenance
==========================

1. List all VMs to see current usage::

    adare vm list

2. Clean up VMs for a specific environment::

    adare vm clear environment 01ARZ3NDEKTSV4RRFFQ69G5FAV --force

3. View experiment run results::

    adare run list --filter my-project.win11
    adare run info 01ARZ3NDEKTSV4RRFFQ69G5FAV