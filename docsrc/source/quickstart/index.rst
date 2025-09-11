***********
Quick Start
***********

Welcome to ADARE! This guide will get you up and running with your first forensic experiment in just a few steps.

What You'll Learn
*****************

By the end of this guide, you'll have:

✅ Created your first ADARE project  
✅ Set up a virtual machine environment  
✅ Built a working forensic experiment  
✅ Run automated tests on forensic artifacts

Prerequisites
*************

Before starting, ensure you have:

- ADARE installed (:doc:`../installation/index`)
- A VM image file (.ova/.ovf) - see :ref:`vm-images` for options

.. _vm-images:

Getting VM Images
=================

You'll need a virtual machine image to run experiments. Options include:

- **Pre-built Images**: Download from `ADARE Web <https://adare.seclab-bonn.de/>`_
- **Create Custom VM**: Follow the :doc:`../user-guide/vm-setup` guide
- **Your Own VMs**: Export existing VMs as .ova files
- **Public Images**: Use publicly available VM images (ensure they're clean)

For this tutorial, we recommend starting with a Ubuntu 24.04 image.

Step 1: Create Your First Project
**********************************

Projects organize your forensic experiments. Create one now:

.. code-block:: bash

   # Create and enter your project directory
   adare project create forensics-tutorial
   cd forensics-tutorial

This creates a project structure:

.. code-block:: text

   forensics-tutorial/
   ├── environments/      # Environment configuration files
   ├── experiments/       # Individual experiment directories  
   ├── shared/            # Shared resources with data/ and tools/ subdirectories
   ├── testfunctions/     # Test function modules
   ├── vm/                # Virtual machine files
   └── run/               # Experiment execution results and logs (created during runs)

Step 2: Set Up a VM Environment
********************************

Environments define the virtual machines where experiments run. Create an environment configuration file `ubuntu24043.yml`:

.. code-block:: yaml

   name: ubuntu24043
   vm: "/path/to/your/ubuntu-vm.ova"  # Update this path to your VM file
   os:
     os: "Ubuntu"
     platform: "linux"
     distribution: "Noble Numbat"
     version: "24.04.3"
     language: "English"
   tags:
     - linux
     - ubuntu


.. important::
   Update the ``vm:`` path to point to your actual VM image file!

Load the environment:

.. code-block:: bash

   adare environment load ubuntu24043

Step 3: Create Your First Experiment
*************************************

Let's create a simple but realistic forensic experiment that deletes a file and analyzes the resulting artifacts:

.. code-block:: bash

   adare experiment create deletefileexample

This creates the experiment structure:

.. code-block:: text

   experiments/deletefileexample/
   ├── playbook.yml      # Automation script
   ├── metadata.yml      # Experiment metadata  
   └── img/              # Screenshots for GUI automation

Configure the experiment metadata:

.. code-block:: yaml
   :caption: experiments/deletefileexample/metadata.yml

   environments:
     - ubuntu24043

Now create the main playbook:

.. code-block:: yaml
   :caption: experiments/deletefileexample/playbook.yml

   settings:
     idle: 1.0              # Pause between actions
     timeout: 300           # Max experiment time
     screenshot:
       format: "png"
       quality: 95

   variables:
     username:
       type: string
       value: "adare"
       description: "System username"
     
     test_file:
       type: path
       value: "/home/{{username}}/Documents/evidence.txt"
       description: "File to delete for testing"
     
     trash_path:
       type: path
       value: "/home/{{username}}/.local/share/Trash"
       description: "System trash location"

   tests:
     - name: file_exists_before
       description: "Verify test file exists before deletion"
       function: file_exists
       parameter:
         dst: '{{test_file}}'

     - name: file_deleted_after
       description: "Verify file no longer exists in original location"
       function: file_does_not_exist
       parameter:
         dst: '{{test_file}}'

     - name: trash_file_exists
       description: "Verify file moved to trash"
       function: file_exists
       parameter:
         dst: '{{trash_path}}/files/evidence.txt'

     - name: trash_info_exists
       description: "Verify trash metadata created"
       function: file_exists
       parameter:
         dst: '{{trash_path}}/info/evidence.txt.trashinfo'

   actions:
     # Create test file
     - command:
         name: "Create Evidence File"
         description: "Create a file to analyze deletion behavior"
         command: "echo 'Secret evidence data' > {{test_file}}"
         shell: true

     - test: file_exists_before

     # Open file manager
     - click:
         target:
           image: "nautilus_taskbar.png"
         description: "Open file manager from taskbar"

     - idle:
         duration: 2.0
         description: "Wait for file manager to open"

     # Navigate to Documents
     - click:
         target:
           text: "Documents"
           strategy:
             SweepStrategy:
               index: 2
         description: "Click on Documents folder"

     # Select and delete file
     - click:
         target:
           text: "evidence.txt"
         description: "Select the evidence file"

     - keyboard:
         combination: ["delete"]
         description: "Delete file using Delete key"

     - save_timestamp:
         description: "Record deletion time for forensic analysis"
         variable: deletion_time

     - idle:
         duration: 2.0
         description: "Wait for deletion to complete"

     # Verify results
     - test: file_deleted_after
     - test: trash_file_exists
     - test: trash_info_exists

Step 4: Add Required Images
****************************

The experiment uses image recognition to find GUI elements. Download the required image:

.. code-block:: bash

   # Create img directory
   mkdir -p experiments/deletefileexample/img
   
   # Download nautilus taskbar image (or create your own)
   # For now, we'll skip this and use text-based targeting instead

.. tip::
   For production experiments, take screenshots of GUI elements and save them in the ``img/`` directory. ADARE uses these for reliable GUI automation.

Step 5: Run Your Experiment
****************************

Now run your forensic experiment:

.. code-block:: bash

   # For development/testing (allows playbook modifications)
   adare experiment run deletefileexample -e ubuntu24043 --test
   
   # For final execution (locks experiment from further changes)
   adare experiment run deletefileexample -e ubuntu24043

.. warning::
   **Development vs Production Runs**
   
   - Use ``--test`` flag during development to keep experimenting with playbook changes
   - Once you run **without** ``--test``, the experiment becomes locked
   - To continue development after a non-test run, copy the experiment directory first

You'll then see an dynamic console output showing progress, actions, and test results.
At the end, a summary of the experiment run will be displayed.


Step 6: View Your Results
**************************

Check the experiment results:

.. code-block:: bash

   # Show details of most recent run
   adare run info

   # List runs
   adare run list

   # View detailed results of a specific run (replace ULID with actual run ID)
   adare run info 01ARZ3NDEKTSV4RRFFQ69G5FAV


Next Steps
**********

Now that you have the basics down, explore these areas:

Learn More
==========

- **User Guide**: :doc:`../user-guide/index` - Complete daily usage guide
- **Playbook Guide**: :doc:`../user-guide/playbooks` - Complete YAML automation guide
- **CLI Reference**: :doc:`../cli-reference/index` - All available commands
- **Advanced Topics**: :doc:`../advanced/index` - Custom functions and performance
