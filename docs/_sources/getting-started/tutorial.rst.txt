********
Tutorial
********

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

- ADARE installed (:doc:`/getting-started/installation`)
- A VM image file (.ova/.ovf) - see :ref:`vm-images` for options

.. _vm-images:

Getting VM Images
=================

You'll need a virtual machine image to run experiments. Options include:

- **Pre-built Images**: Download from `ADARE Web <https://adare.seclab-bonn.de/>`_
- **Create Custom VM**: Follow the VM setup guide
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

   # Development/test run (default: allows playbook modifications, creates fake runs)
   adare experiment run deletefileexample -e ubuntu24043

   # Production run (strict integrity checks, creates real runs)
   adare experiment run deletefileexample -e ubuntu24043 --production

.. note::
   **Test vs Production Modes**

   - **Default behavior** is test mode - ideal for development and iteration
   - Test mode creates "fake runs" that can be cleaned up with ``adare experiment clean``
   - Use ``--production`` flag only when ready for real data collection
   - Production runs enforce strict integrity checks to ensure reproducibility

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


What Just Happened?
*******************

The tutorial walked through the commands, but here is what ADARE did behind the scenes during the experiment run:

1. **VM Boot**: ADARE imported your VM image, created a snapshot for safe rollback, and booted the virtual machine.
2. **Agent Installation**: The ADARE guest agent was installed inside the VM via shared file transfer, providing a WebSocket connection between host and guest.
3. **Playbook Execution**: Each action in your playbook was serialized and sent to the guest agent, which executed GUI interactions via PyAutoGUI and system commands via subprocess.
4. **Test Evaluation**: Test functions ran inside the VM, comparing actual system state against your expected conditions, with results streamed back to the host.
5. **Artifact Collection**: Screenshots, logs, and test results were collected in the run directory for analysis.

Understanding this flow helps when debugging experiments or building more advanced playbooks -- each step is a point where you can inspect what happened and why.

Next Steps
**********

Now that you have the basics down, explore these areas:

Learn More
==========

- **Core Concepts**: :doc:`concepts` - Understand the ADARE mental model
- **Projects**: :doc:`/guide/projects` - Project structure and management
- **Environments**: :doc:`/guide/environments` - VM configuration and setup
- **Experiments**: :doc:`/guide/experiments` - Experiment structure and metadata
- **Actions**: :doc:`/reference/actions` - Complete playbook automation guide
- **Test Functions**: :doc:`/reference/testfunctions/index` - Forensic validation functions
- **Test-Driven Analysis**: :doc:`/guide/test-driven-analysis` - End-to-end forensic analysis workflow
- **Dev Mode**: :doc:`/guide/dev-mode` - Interactive development with checkpoints