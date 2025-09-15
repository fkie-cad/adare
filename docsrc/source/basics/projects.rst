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
- **shared/**: Shared resources with data/ and tools/ subdirectories
- **testfunctions/**: Test function modules
- **vm/**: Virtual machine files
- **run/**: Experiment execution results and logs

The project directory serves as the working directory for all ADARE commands.