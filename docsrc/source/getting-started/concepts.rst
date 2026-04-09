*************
Core Concepts
*************

ADARE automates forensic experiments inside virtual machines and validates the results with test functions. Before diving into specific commands and configurations, it helps to understand the core building blocks and how they fit together.

Projects
========

A **project** is the top-level workspace that contains everything needed for a set of related forensic experiments. You create one with ``adare project create`` and work inside it for the duration of your analysis.

A project directory has a fixed layout:

.. code-block:: text

   my-project/
   ├── environments/      # Environment configuration files (YAML)
   ├── experiments/       # Individual experiment directories
   ├── shared/            # Shared resources
   │   ├── data/          # Data files available to all experiments
   │   └── tools/         # Tools and utilities shared across experiments
   ├── testfunctions/     # Custom test function modules
   ├── vm/                # Virtual machine files and images
   └── run/               # Experiment execution results and logs

Each directory has a clear purpose. Environments and experiments live in their own subdirectories. The ``shared/`` directory provides a place for data files and tools that multiple experiments need. Custom test functions go in ``testfunctions/``. The ``run/`` directory is created automatically when experiments execute and holds all output.

See :doc:`/guide/projects` for details on project structure and management.

Environments
============

An **environment** is a configured virtual machine paired with an operating system definition. It is expressed as a YAML file that points to a disk image and describes the OS inside it.

An environment definition specifies:

- The path to the VM image file (``.ova``, ``.ovf``, or other supported formats)
- The operating system platform, distribution, and version
- Any post-setup installations or configuration steps
- Tags for organization and filtering

Environments are the "where" of an experiment -- they define the system under test. The same experiment can target multiple environments to compare forensic behavior across OS versions or configurations.

See :doc:`/guide/environments` for VM configuration and setup.

Experiments
===========

An **experiment** is a self-contained unit of forensic analysis. It combines a playbook (the automation script) with metadata that describes which environments it targets and how it should be run.

Each experiment directory contains:

.. code-block:: text

   experiments/my-experiment/
   ├── playbook.yml       # Automation script (actions, tests, variables)
   ├── metadata.yml       # Experiment metadata (target environments, tags)
   ├── img/               # Screenshots for GUI element recognition
   └── shared/            # Experiment-specific shared resources

The ``metadata.yml`` file links the experiment to one or more environments. The ``img/`` directory holds reference screenshots that ADARE uses for image-based GUI targeting. The ``shared/`` directory can hold files specific to this experiment.

See :doc:`/guide/experiments` for experiment structure and metadata.

Playbooks
=========

A **playbook** is the YAML file at the heart of every experiment. It defines what ADARE should do inside the virtual machine: which actions to perform, which tests to run, and what variables to use.

A playbook has four sections:

- **settings**: Global configuration such as idle time between actions, timeouts, and screenshot format.
- **variables**: Named values (strings, paths, numbers) that can be referenced throughout the playbook using ``{{variable_name}}`` syntax. Variables support type declarations and descriptions.
- **tests**: Definitions of test functions to validate forensic artifacts. Each test references a function by name and provides parameters.
- **actions**: An ordered sequence of steps executed inside the VM. Actions include GUI interactions (click, keyboard, type), system commands, idle waits, screenshots, timestamps, and test invocations.

Actions are executed sequentially. ADARE sends each action to the guest agent inside the VM, which carries it out and reports the result back. GUI actions use image recognition or text detection to find on-screen targets.

See :doc:`/reference/actions` for the complete action reference and :doc:`/reference/testfunctions/index` for available test functions.

The Experiment Lifecycle
========================

Running an experiment follows a defined sequence from start to finish:

1. **Load**: The playbook YAML is parsed and its actions are serialized into the database as ``PlaybookItem`` records. The original YAML content is stored for variable and test resolution. A hash is computed for integrity validation.
2. **Prepare VM**: ADARE imports the VM image (if not already imported), creates a snapshot for safe rollback, and boots the virtual machine.
3. **Install Agent**: The ADARE guest agent is transferred into the VM and started. It establishes a WebSocket connection back to the host, creating a command channel.
4. **Execute Actions**: Actions are loaded from the database (not re-parsed from YAML), reconstructed into action objects, and sent one by one to the guest agent for execution. GUI interactions, system commands, and tests all flow through this channel.
5. **Collect Artifacts**: Screenshots, logs, timestamps, and test results are collected in the ``run/`` directory. Each run is identified by a unique ULID.
6. **Cleanup**: The VM is shut down and optionally rolled back to its pre-experiment snapshot, ensuring a clean state for the next run.

This database-driven approach provides a complete audit trail, integrity validation, and efficient re-execution without repeated YAML parsing.

Test Mode vs Production Mode
=============================

ADARE supports two execution modes that serve different stages of the workflow.

**Test mode** (the default) is designed for iterative development:

- Allows playbook modifications between runs without re-loading
- Creates "fake runs" that can be cleaned up with ``adare experiment clean``
- No strict integrity enforcement
- Ideal for building and debugging experiments

**Production mode** (enabled with the ``--production`` flag) is for real data collection:

- Enforces integrity checks on the playbook and its actions
- Creates tracked runs with full audit trails
- Validates that the loaded playbook has not been tampered with
- Ensures reproducibility and forensic soundness of results

The typical workflow is to develop in test mode until the experiment works correctly, then switch to production mode for actual data collection.

ADARE Web
=========

**ADARE Web** is the community platform for sharing and discovering forensic experiments. It allows researchers to:

- **Download** environments, experiments, and test functions published by others
- **Publish** your own work for the community to use and reproduce
- **Sync** project resources with the platform
- **Browse** shared results and compare findings across different setups

ADARE Web integration is built into the CLI. After logging in, you can pull down shared resources directly into your project or push your experiments for others to use.

See :doc:`/guide/sharing` for workflows around ADARE Web.
