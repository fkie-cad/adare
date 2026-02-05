********
Projects
********

Projects organize related experiments and provide shared resources.

Creating Projects
******************

.. code-block:: bash

   # Create a new project
   adare project create my-project

   # Create with description
   adare project create my-project --description "Research project"

Managing Projects
*****************

.. code-block:: bash

   # List all projects
   adare project list

   # Show project information
   adare project info

   # Remove project
   adare project remove my-project

Project Structure
*****************

Each project contains:

- **environments/**: Environment configuration files
- **experiments/**: Individual experiment directories
- **shared/**: Project-level shared resources (available to all experiments)

  - **data/**: Shared data files accessible across experiments
  - **tools/**: Shared tools and utilities for all experiments

- **testfunctions/**: Test function modules
- **vm/**: Virtual machine files
- **run/**: Experiment execution results and logs

The project directory serves as the working directory for all ADARE commands.

Shared Directories
******************

ADARE provides two levels of shared directories for organizing resources:

Project-Level Shared Directory
===============================

The project shared directory (``<project>/shared/``) contains resources accessible to ALL experiments in the project:

- **Location**: ``<project>/shared/`` on host
- **VM Mount**: ``/adare/project_shared/`` (Linux) or ``C:/adare/project_shared/`` (Windows)
- **Automatic Variables**:

  - ``{{adare_project_shared}}`` - Base project shared directory
  - ``{{adare_project_shared_tools}}`` - Project shared tools subdirectory
  - ``{{adare_project_shared_data}}`` - Project shared data subdirectory

- **Use Cases**: Common tools, datasets, configuration files used across multiple experiments

Experiment-Level Shared Directory
==================================

Each experiment has its own shared directory (``<project>/experiments/<name>/shared/``) for experiment-specific resources:

- **Location**: ``<project>/experiments/<name>/shared/`` on host
- **VM Mount**: ``/adare/shared/`` (Linux) or ``C:/adare/shared/`` (Windows)
- **Automatic Variables**:

  - ``{{adare_shared}}`` - Base experiment shared directory
  - ``{{adare_shared_tools}}`` - Experiment shared tools subdirectory
  - ``{{adare_shared_data}}`` - Experiment shared data subdirectory

- **Use Cases**: Experiment-specific input files, test data, custom scripts

Best Practices
==============

- Place common tools and datasets in the **project shared directory** to avoid duplication across experiments
- Place experiment-specific files in the **experiment shared directory** for isolation and clarity
- Both directories are optional - mounting is conditional on their existence
- Use automatic variables in playbooks (e.g., ``{{adare_project_shared_tools}}/mytool.exe``) for portable paths

For complete automatic variables list, see :doc:`actions` Variable section.