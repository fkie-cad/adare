***************
Getting Started
***************


The following sections will help you get started with using ADARE.



Walkthrough: Quick Start Guide
******************************

This walkthrough provides information on how to setup ADARE to run downloaded experiments and to create new experiments.
ADARE uses YAML-based playbooks for GUI automation, making experiments easy to create and maintain without Python coding.

To use ADARE you must setup a project, which is basically a directory containing data used for the experiments.
This can be simply done by navigating to the directory where you want to create the project and run the following command::

    adare project create <project_name>

This will create a directory with the name ``<project_name>`` and within it data, such as data used for the text recognition within the experiments.
To further work within that project, you must navigate to the project directory::

    cd <project_name>

Within this project a user must create an environment, dedicated to contain configurations related to one specific virtual machine.
This can be done by running the following command, when providing an environment config file::

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
For Windows 11 with our provided VM, a YAML file would look like this:

.. code-block:: yaml

    name: win11
    vm: TODOADDREALLINKHERE
    os:
      os: "Windows 11"
      platform: "windows"
      distribution: "Home"
      version: "23H1"
      language: "English"
    tags:
      - test
      - example

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

In the following we will create a simple example experiment to delete a file from the Documents folder to the trash bin on a Windows 11 machine.
We therefore start by creating the experiment template::

    adare experiment create TrashBinDeleteFile

We start with the metadata file, which would look like this:

.. code-block:: yaml

    environments:
     - win11

We then create the tests within the testset file.
It contains a list of tests, as well as the name of the experiment.
Each test must specify a name, a description, a function and parameters.
The function specifies the test to be performed, such as checking if a file exists or checking if a file contains a specific line.
The parameters specify the file or directory to be checked, the line to be checked or the regex to be checked.
An example testset file in our example would look like this:

.. code-block:: yaml

    name: TrashBinDeleteFile
    description: 'Test experiment to delete a file and check if it is moved to the trash bin'
    tests:
      - name: testfile_created
        description: 'Verify test file does not exist before experiment'
        function: file_exists
        parameter:
          dst: 'C:/Users/vagrant/Documents/testfile.txt'
      - name: testfile_deleted
        description: 'Verify test file was deleted successfully'
        function: file_does_not_exist
        parameter:
          dst: 'C:/Users/vagrant/Documents/testfile.txt'
      - name: trashbin_check
        description: 'check if file metadata exists'
        function: csv_contains_line_matching_regex
        parameter:
          dst: 'C:/Users/vagrant/Documents/trashbin/*.csv'
          entry:
            - !re '.*'
            - '$I'
            - 'C:\Users\vagrant\Documents\testfile'
            - !re '.*'
            - !timestamp
              timestamp: '{{ TIMESTAMP.DELETIONDATE }}'
              tolerance: 30

This file contains three tests: one checking if the test file exists initially, one checking if the file was deleted successfully, and one checking if the trash bin artifact (when parsed with RBCmd to a CSV file) contains a line in a given format.
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
      username: "vagrant"
      filepath: "C:/Users/{{ username }}/Documents/testfile.txt"

    actions:
      - command:
          name: "Create Test File"
          description: "create the to deleted file"
          cmd: "echo 'This is a test file.' > {{ filepath }}"
          shell: true
      - test: testfile_created
      - click:
          target:
            image: "explorer.png"
          description: "Open File Explorer"
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
            text: "testfile"
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
      - block:
          description: "Check if file metadata exists in trash bin"
          actions:
            - command:
                name: "RBCmd"
                description: "Run RBCmd.exe to check file metadata"
                tool: RBCmd.exe
                command: 'RBCmd.exe -d C:\ --csv C:/Users/vagrant/Documents/trashbin'
            - test: trashbin_check

As you can see, the playbook uses YAML syntax and provides several types of actions:

- ``command``: Execute system commands
- ``click``: Mouse clicks using image recognition or text finding
- ``keyboard``: Keyboard input and key combinations
- ``idle``: Wait/pause actions
- ``test``: Execute tests from the testset file
- ``save_timestamp``: Save timestamps for later use in tests
- ``block``: Group actions together

The playbook can use images to find elements on the screen. To provide these images, you must place them in the ``img`` folder within the experiment directory.
For this example you can download the images from `GitHub <https://github.com/fkie-cad/adare/tree/dev/adare/appdata/examples/experiments/TrashBinDeleteFile/img>`_.
More detailed explanation as well as details on creating an experiment can be found in :ref:`gettingstarted/experiment:Create an Experiment`.

Now that we have created the experiment, we can finally run it::

    adare experiment run TrashBinDeleteFile -e win11 --fake

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