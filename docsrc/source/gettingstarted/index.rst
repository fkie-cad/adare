***************
Getting Started
***************


The following sections will help you get started with using ADARE.



Walkthrough: Quick Start Guide
******************************

ADARE automates GUI testing using YAML playbooks - no Python coding required.

**Step 1: Create a Project**

Navigate to your desired location and run::

    adare project create <project_name>
    cd <project_name>

This creates a project directory with required data files.

**Step 2: Create an Environment**

Create an environment config file and load it::

    adare environment load <environment_config_file>.yml

The environment config file is a YAML file containing information about the environment that is to be created.
It contains the VM image path that should be used along with the operating system information, telling ADARE whether the VM is a Windows or Linux box.
A minimal example of a file is provided below.
In the section :ref:`gettingstarted/environment:Create an Environment` you can find a detailed description of the environment config file and its possible configurations.

.. code-block:: yaml

    name: <environment_name>
    vm: <path_or_link_to_ova_or_ovf_file>
    os:
        os: <os_name> # custom e.g. 'Windows 11'
        platform: <os_platform> # 'windows' or 'linux'
        distribution: <os_distribution> # custom e.g. 'Home'
        version: <os_version> # custom e.g. '23H1'
        language: <language> # e.g. 'English'

Notably ``<path_or_link_to_ova_or_ovf_file>`` is the path to a virtual machine image file, such as an OVA or OVF file.
We provide a link to a list of downloadable virtual machines in `Adare Web <https://adare.seclab-bonn.de/>`_.
For Ubuntu 24.04 with our provided VM, a YAML file would look like this:

.. code-block:: yaml

    name: ubuntu24043
    vm: "/path/to/ubuntu-vm.ova"
    os:
      os: "Ubuntu"
      platform: "linux"
      distribution: "Noble Numbat"
      version: "24.04.3"
      language: "English"
    tags:
      - linux
      - ubuntu

Now that we have specified the environment and therefore the virtual machine to be used, we can specify what we want to do and test on this machine.
Therefore a user can create an experiment template with the following command::

    adare experiment create <experiment_name>

This will create a directory in the project's experiment directory with the following structure:

::

    <project>/
    ├── experiments/
    │   ├── ...
    │   └── <experiment_name>/
    │       ├── playbook.yaml
    │       ├── testset.yml
    │       ├── metadata.yml
    │       └── img/
    └── ...

The ``metadata.yml`` file contains information about the experiment, especially the names of the environments it can be run on.
The ``testset.yml`` file contains all tests that can be run within the experiment.
The ``playbook.yaml`` file contains the YAML-based GUI automation instructions, such as mouse clicks or keyboard inputs, as well as calls to the tests specified in the testset file.
The directory ``img`` contains images used for GUI automation.

In the following we will create a simple example experiment to delete a file from the Documents folder to the trash bin on Ubuntu.
We therefore start by creating the experiment template::

    adare experiment create ubuntu_deletefile

We start with the metadata file, which would look like this:

.. code-block:: yaml

    environments:
     - ubuntu24043

We then create the tests within the testset file.
It contains a list of tests, as well as the name of the experiment.
Each test must specify a name, a description, a function and parameters.
The function specifies the test to be performed, such as checking if a file exists or checking if a file contains a specific line.
The parameters specify the file or directory to be checked, the line to be checked or the regex to be checked.
An example testset file in our example would look like this:

.. code-block:: yaml

    name: ubuntu_deletefile
    tests:
      - name: testfile_created
        description: 'Verify test file does exist before experiment'
        function: file_exists
        parameter:
          dst: '/home/adare/Documents/testfile.txt'
      - name: testfile_deleted
        description: 'Verify test file was deleted successfully'
        function: file_does_not_exist
        parameter:
          dst: '/home/adare/Documents/testfile.txt'
      - name: trashbin_check_file
        description: 'check if file exists in trashbin'
        function: file_exists
        parameter:
          dst: '/home/adare/.local/share/Trash/files/testfile.txt'
      - name: trahsbin_check_info_file
        description: 'check if info file exists in trashbin'
        function: file_exists
        parameter:
          dst: '/home/adare/.local/share/Trash/info/testfile.txt.trashinfo'
      - name: trashbin_check_info_date
        description: 'check if deletion date in info file is correct'
        function: file_content_equals
        parameter:
          dst: '/home/adare/.local/share/Trash/info/testfile.txt.trashinfo'
          content: |
            [Trash Info]
            Path=/home/adare/Documents/testfile.txt
            DeletionDate={{ TIMESTAMP.DELETIONDATE | format('%Y-%m-%dT%H:%M:%S') | tolerance(5, -5) }}

This file contains five tests: checking if the test file exists initially, verifying the file was deleted, and confirming the file appears in Ubuntu's trash system (both the actual file and its metadata).
We can save variables within the playbook and use them in the testset file (as shown with ``{{ TIMESTAMP.DELETIONDATE }}``).

We now create the playbook file, which contains the YAML-based GUI automation steps.
The playbook uses a declarative approach where you specify actions like clicks, keyboard input, and test executions.
An example playbook file for our example would look like this:

.. code-block:: yaml

    settings:
      # Default pause between actions (seconds)
      idle: 1.0
      
      # Overall timeout for the experiment (seconds)
      timeout: 300
      
      # Default screenshot settings
      screenshot:
        format: "png"
        quality: 95

    # Variables that can be used throughout the playbook
    variables:
      username: "adare"
      filepath: "/home/{{ username }}/Documents/testfile.txt"

    actions:
      - command:
          name: "Create Test File"
          description: "create the to deleted file"
          command: "echo 'This is a test file.' > {{ filepath }}"
          shell: true
      - test: testfile_created
      - click:
          target:
            image: "nautilus_taskbar.png"
          description: "Open Ubuntu File Explorer"
      - idle:
          duration: 2.0
          description: "Wait additional time for File Explorer to open since some systems are slow"
      - click:
          target:
            text: "Documents"
            strategy:
              SweepStrategy:
                index: 2
          description: "Navigate to Documents folder"
      - click:
          target:
            text: "testfile.txt"
          description: "Select the test file to delete it with shortcut"
      - keyboard:
          combination: ["delete"]
          description: "Delete the test file using keyboard shortcut"
      - save_timestamp:
          description: "Save the timestamp of file deletion for later verification"
          variable: TIMESTAMP.DELETIONDATE
      - idle:
          duration: 1.0
          description: "Wait for file deletion to complete"
      - test: testfile_deleted
      - test: trashbin_check_file
      - test: trahsbin_check_info_file
      - test: trashbin_check_info_date

As you can see, the playbook uses YAML syntax and provides several types of actions:

- ``command``: Execute system commands
- ``click``: Mouse clicks using image recognition or text finding
- ``keyboard``: Keyboard input and key combinations
- ``idle``: Wait/pause actions
- ``test``: Execute tests from the testset file
- ``save_timestamp``: Save timestamps for later use in tests
- ``block``: Group actions together

The playbook can use images to find elements on the screen. To provide these images, you must place them in the ``img`` folder within the experiment directory.
For this example you can download the images from `GitHub <https://github.com/fkie-cad/adare/tree/dev/adare/appdata/examples/experiments/ubuntu_deletefile/img>`_.
More detailed explanation as well as details on creating an experiment can be found in :ref:`gettingstarted/experiment:Create an Experiment`.

Now that we have created the experiment, we can finally run it::

    adare experiment run ubuntu_deletefile -e ubuntu24043 --fake

This will start the virtual machine and execute the experiment on it.
While the experiment is running, the user can see the progress of the experiment in the terminal.
The ``--fake`` flag runs the experiment in a test mode for development purposes.

To later see more detailed information about the run, a user can run::

    adare show run <run_ulid>

.. toctree::
   :hidden:
   :maxdepth: 2

   environment
   experiment
   playbook_reference

.. include:: ./environment.rst
.. include:: ./experiment.rst