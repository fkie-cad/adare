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
- Basic understanding of forensic concepts

.. _vm-images:

Getting VM Images
=================

You'll need a virtual machine image to run experiments. Options include:

- **Pre-built Images**: Download from `ADARE Web <https://adare.seclab-bonn.de/>`_
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
   ├── programs/          # Shared tools and utilities
   ├── tessdata/          # OCR data for text recognition
   └── environments/      # VM environments (created later)

Step 2: Set Up a VM Environment
********************************

Environments define the virtual machines where experiments run. Create an environment configuration file:

.. code-block:: bash

   # Create environment config
   cat > ubuntu-env.yml << EOF
   name: ubuntu24043
   vm: "/path/to/your/ubuntu-vm.ova"  # Update this path!
   os:
     os: "Ubuntu"
     platform: "linux"
     distribution: "Noble Numbat"
     version: "24.04.3"
     language: "English"
   tags:
     - linux
     - ubuntu
   EOF

.. important::
   Update the ``vm:`` path to point to your actual VM image file!

Load the environment:

.. code-block:: bash

   adare environment load ubuntu-env.yml

Step 3: Create Your First Experiment
*************************************

Let's create a simple but realistic forensic experiment that deletes a file and analyzes the resulting artifacts:

.. code-block:: bash

   adare experiment create file-deletion-analysis

This creates the experiment structure:

.. code-block:: text

   experiments/file-deletion-analysis/
   ├── playbook.yml      # Automation script
   ├── metadata.yml      # Experiment metadata  
   └── img/              # Screenshots for GUI automation

Configure the experiment metadata:

.. code-block:: yaml
   :caption: experiments/file-deletion-analysis/metadata.yml

   environments:
     - ubuntu24043

Now create the main playbook:

.. code-block:: yaml
   :caption: experiments/file-deletion-analysis/playbook.yml

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
   mkdir -p experiments/file-deletion-analysis/img
   
   # Download nautilus taskbar image (or create your own)
   # For now, we'll skip this and use text-based targeting instead

.. tip::
   For production experiments, take screenshots of GUI elements and save them in the ``img/`` directory. ADARE uses these for reliable GUI automation.

Step 5: Run Your Experiment
****************************

Now run your forensic experiment:

.. code-block:: bash

   adare experiment run file-deletion-analysis -e ubuntu24043

You'll see output like:

.. code-block:: text

   🚀 Starting experiment: file-deletion-analysis
   📋 Environment: ubuntu24043
   ⚡ VM: Starting Ubuntu VM...
   🎬 Executing playbook actions...
   ✅ Test: file_exists_before - PASSED
   🖱️ Action: Opening file manager...
   🖱️ Action: Clicking Documents folder...  
   🖱️ Action: Selecting evidence.txt...
   ⌨️ Action: Pressing Delete key...
   ✅ Test: file_deleted_after - PASSED
   ✅ Test: trash_file_exists - PASSED  
   ✅ Test: trash_info_exists - PASSED
   
   🎉 Experiment completed successfully!
   📊 Results saved to: environments/ubuntu24043/results/file-deletion-analysis_<timestamp>/

Step 6: View Your Results
**************************

Check the experiment results:

.. code-block:: bash

   # List recent runs
   adare run list

   # View detailed results (replace ULID with actual run ID)
   adare run info 01ARZ3NDEKTSV4RRFFQ69G5FAV

The results include:

- **Test Results**: Pass/fail status for each forensic test
- **Screenshots**: Visual record of each GUI action
- **Timestamps**: Precise timing of forensic events  
- **Artifacts**: Forensic artifacts created/modified during the experiment
- **Logs**: Detailed execution logs for troubleshooting

What You've Accomplished
************************

Congratulations! You've just:

🔬 **Created a forensic experiment** that simulates realistic user behavior  
📊 **Automated artifact analysis** by testing file system changes  
🕵️ **Validated trash bin behavior** across different system configurations  
📸 **Documented the process** with automated screenshots and logs  

Next Steps
**********

Now that you have the basics down, explore these areas:

Advanced Experiments
====================

- **Registry Analysis**: Test Windows registry changes
- **Browser Forensics**: Analyze web browser artifacts  
- **Timeline Analysis**: Create detailed forensic timelines
- **Multi-VM Testing**: Test across different OS versions

Learn More
==========

- **User Guide**: :doc:`../user-guide/index` - Complete daily usage guide
- **Playbook Guide**: :doc:`../user-guide/playbooks` - Complete YAML automation guide
- **CLI Reference**: :doc:`../cli-reference/index` - All available commands
- **Advanced Topics**: :doc:`../advanced/index` - Custom functions and performance

Get Help
========

- **Troubleshooting**: :doc:`../troubleshooting/index` - Common issues and solutions
- **Community**: `ADARE Web <https://adare.seclab-bonn.de/>`_ - Share experiments and get help
- **Issues**: `GitHub Issues <https://github.com/fkie-cad/Adare/issues>`_ - Report bugs and feature requests

.. toctree::
   :hidden:
   :maxdepth: 2

   first-experiment
   concepts