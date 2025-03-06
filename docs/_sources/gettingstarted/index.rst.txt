***************
Getting Started
***************


The following sections will help you get started with using ADARE.



Walkthrough: Quick Start Guide
******************************

This is a walkthrough providing information how to setup ADARE to run downloaded experiments and to create new experiments.
To use ADARE you must setup a project, which is basically a directory containing data used for the experiments.
This can be simply done by navigating to the directory where you want to create the project and run the following command::

    adare project create <project_name>

This will create a directory with the name ``<project_name>`` and within it data, such as data used for the text recognition within the experiemnts.
To further work within that project, you must navigate to the project directory::

    cd <project_name>

Within this project a user must create an environment, dedicated to contain configurations related to one specific vagrant box (virtual machine).
This can be done by running the following command, when providing an environment config file::

    adare environment load  <environment_config_file>.yml

The environment config file is a yaml file containing information about the environment that is to be created.
It contains the vagrant box that should be used along with the operating system, telling ADARE whether the box is a Windows or Linux box.
An minimal example of a file is provided below.
In the section :ref:`gettingstarted/environment:Create an Environment` you can find a detailed description of the environment config file and it possible configurations.


.. code-block:: yaml

    name: <environment_name>
    vagrantbox: <vagrant_box_name>
    os:
        os: <os_name> (custom e.g. 'Windows')
        platform: <os_platform> ('windows' or 'linux')
        distribution: <os_distribution> (custom e.g. 'Windows 10')
        version: <os_version> (custom e.g. '11H2.0.2403')


Notably ``<vagrant_box_name>`` can be the name of local vagrant box or the name of a box from the vagrant cloud, which has format ``<username>/<box_name>``.
To list your local vagrant boxes you can run ``vagrant box list``.
We provide a list of vagrant boxes that can be used with ADARE under our `Vagrant Cloud Account <https://portal.cloud.hashicorp.com/vagrant/discover/mikue>`_.
For Windows 11 with our provided box a yaml file would look like this:

.. code-block:: yaml

    name: testenvironment
    vagrantbox: mikue/adare_win11
    description: "Windows 11 Test Environment"
    os:
      os: Windows
      platform: windows
      distribution: Windows 11
      version: 11H2.0.2403
    tags:
      - windows11
      - test


Now that we have specified the environment and therefore the virtual machine to be used, we can specify what we want to do and test on this machine.
Therefore a user can create an experiment template with the following command::

    adare experiment create <experiment_name>

This will create a directory project's experiment directory of the following structure

::

    <project>/
    ├── experiments/
    │   ├── ...
    │   └── <experiment_name>/
    │       ├── action.py
    │       ├── testset.yml
    │       ├── metadata.yml
    │       └── img/
    └── ...

The metadata.yml file contains information about the experiment, especially the names of the environments it can be run on.
The testset.yml file contains all tests, that can be run within the experiment.
The action.py file contains the user action performed within the experiment, such as mouse clicks or keyboard inputs, as well as the calls to the tests specified in the testset file.
The directory ``img`` contains images used within the gui automation.

In the following we will create an simple example experiment to delete a file from the home folder to the trash bin on an Windows 11 machine.
We therefore start by creating the experiment template::

    adare experiment create TrashBinDeleteFile

We start with the metadata file, which would look like this:

.. code-block:: yaml
    environments:
      - testenvironment
    tags:
      - example
      - trashbin

We then create the tests within the testset file.
It contains a list of tests, as well as the name of the experiment and optionally commands to be run to parse artifacts.
Each test must specify a name, a description, a type and parameters.
The type specifies the test to be performed, such as checking if a file exists or checking if a file contains a specific line.
The parameters specify the file or directory to be checked, the line to be checked or the regex to be checked.
An example testset file in our example would look like this:

.. code-block:: yaml

    name: TrashBinDeleteFile
    tests:
      - name: existencefile
        description: 'check if file exists'
        type: file_does_not_exist
        params:
          dst: 'C:/Users/vagrant/Documents/testfile'
      - name: deletedfileInfo
        description: 'check if file metadata exists'
        type: csv_contains_line_matching_regex
        depends_on:
          - RBCmd
        params:
          dst: 'C:/Users/vagrant/Documents/test/*.csv'
          entry:
            - !re '.*'
            - '$I'
            - 'C:\Users\vagrant\Documents\testfile'
            - !re '.*'
            - !timestamp
              timestamp: '{{ TIMESTAMP.DELETIONDATE }}'
              tolerance: 30
    commands:
      - name: RBCmd
        description: 'Run RBCmd.exe'
        tool: RBCmd.exe
        command: 'RBCmd.exe -d C:\ --csv C:/Users/vagrant/Documents/test'

This file contains two tests, one checking if the file exists and one checking if the trash bin artifact after parsed with RBCmd to an csv file contains a line in a given format.
We can even save a variable within the action file and used it in the testset file (as here done with ``{{ TIMESTAMP.DELETIONDATE }}``).


We now create the action file, which contains the user action performed within the experiment.
First we need possibly some steps to prepare the experiment, such as in our case creating a file that we want to delete.
This can be done in the prepare function.
Then we need to specify the gui actions, key presses, calls to tests from the testset and saving of variables.
An example action file in our example would look like this:

.. code-block:: python

    from adarevm.action.experiment import Experiment, KEYMAP
    from pathlib import Path
    from typing import Callable, Awaitable
    from adarevm.testset.testset import Testset

    import logging
    log = logging.getLogger(__name__)


    class TrashBinDeleteFile(Experiment):
        description = 'delete file and check trash bin'

        def __init__(self, img_folder: Path, tessdata_folder: Path, testset: Testset, log_func: Callable[[str], Awaitable[None]]):
            """
                initialization function which in most cases should not be changed (except there is a need to use a different display controller or computer vision backend for guibot)
            """
            super().__init__(img_folder, tessdata_folder, testset, log_func)

        def prepare(self) -> tuple[bool, str]:
            """
                this function can be used to execute some commands before the clicks happen (e.g. creating a file)
            """
            # create file C:/Users/vagrant/Documents/testfile
            with open('C:/Users/vagrant/Documents/testfile', 'w') as f:
                f.write('test')
            return True, ''

        def run(self) -> tuple[bool, str]:
            """
                this function should be used to execute the gui automation steps
            """
            log.info(f'experiment {self.name} started')

            # place the code to execute some stuff here
            match = self.find('files.png')
            if match:
                self.click(match[0])
                self.idle(2)
            else:
                error_name = 'find failed'
                error_msg = 'could not find files.png'
                self.error(error_name, error_msg)
                return False, f'{error_name}: {error_msg}'

            match = self.find('documents.png')
            if match:
                self.click(match[0])
                self.idle(2)
            else:
                error_name = 'find failed'
                error_msg = 'could not find documents.png'
                self.error(error_name, error_msg)
                return False, f'{error_name}: {error_msg}'

            match = self.find('testfile.png')
            if match:
                self.click(match[0])
                self.idle(2)
            else:
                error_name = 'find failed'
                error_msg = 'could not find testfile.png'
                self.error(error_name, error_msg)
                return False, ''

            self.press_keys([KEYMAP.DELETE])
            self.save_time('DELETIONDATE')

            self.run_test('existencefile')
            self.run_test('deletedfileInfo')

            log.info(f'experiment {self.name} done')

            return True, ''


As you have noticed, the action file can use images to find elements on the screen.
To provide these images, you must place them in the img folder within the experiment directory.
For this example you can download the images from `GitHub <https://github.com/fkie-cad/adare/tree/dev/adare/appdata/examples/experiments/TrashBinDeleteFile/img>`_.
More detailed explanation as well as details on creating an experiment can be found in :ref:`gettingstarted/experiment:Create an Experiment`.

Now that we have created the experiment, we can finally run it::

    adare experiment run <experiment_name> -e <environment_name> --fake

This will start the vagrant box and execute the experiment on it.
While the experiment is running, the user can see the progress of the experiment in the terminal.
Since during development we might want to

To later see more detailed information about the run a user can run::

    adare show run <run_ulid>

.. include:: ./environment.rst
.. include:: ./experiment.rst