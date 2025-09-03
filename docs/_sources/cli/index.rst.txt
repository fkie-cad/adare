****************************
Command Line Interface (CLI)
****************************

The ADARE CLI provides comprehensive command-line access to all framework functionality. It supports project management, environment configuration, experiment execution, VM lifecycle management, and web platform integration.

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
====================

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

``adare experiment run <experiment>``
  Execute an experiment in the specified environment.
  
  Options:
    * ``--environment TEXT`` - Name of the environment (required)
    * ``--test`` - Run in test mode (delete results afterwards, don't block changes)
    * ``--debug-screenshots`` - Save screenshots to experiment run directory for debugging
    * ``--preserve-snapshot`` - Create experiment snapshot for preservation (default: only reset to base)
    * ``--project TEXT`` - Name of the project

``adare experiment develop <experiment>``
  Run an experiment in development/test mode for iterative development.
  
  Options:
    * ``--environment TEXT`` - Name of the environment (required)
    * ``--project TEXT`` - Name of the project

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
======================

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

System Management
=================

Administrative commands for maintaining the ADARE system.

``adare manage reset-db``
  Reset the ADARE database (use with caution - will delete all experiment data).

``adare manage reset-vm``
  Reset all VMs in the system (use with caution).
  
  Options:
    * ``--force`` - Force deletion of all VMs (required for confirmation)

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