***************
Getting Started
***************

The following sections will help you get started with using ADARE.


Walkthrough: Quick Start Guide
******************************

This is a walkthrough providing information how to setup ADARE to run downloaded experiments and to create new experiments.
To use ADARE you must setup a project, which is basically a directory containing data used for the experiments.
This can be simply done by navigating to the directory where you want to create the project and run the following command::

    adare proj create <project_name>

This will create a directory with the name <project_name> and within it data, such as data used for the text recognition within the experiemnts.


Within this project a user must create an environment, dedicated to contain experiments related to one specific virtual machine.
This can be done by running the following command, when providing an environment config file::

    adare env create  <environment_config_file>.yml

The environment config file is a yaml file containing information about the environment that is to be created.
It contains the vagrant box that should be used along with the operating system, telling Adare whether the box is a Windows or Linux box.
Additionally to that it is also possible to provide a list installations to be done after the box is started to install further applications needed to run the experiment.
An example of such a file is provided below.
In section :ref:`basics/envconfig:Environment Configuration File` you can find a detailed description of the environment config file and it possible configurations.


.. code-block:: yaml

    name: <environment_name>
    vagrantbox: <vagrant_box_name>
    os_platform: <os_platform> (Windows or Linux)
    ...


As soon as the environment is created, it is possible to run experiments on it.
Therefore a user can execute the following command::

    adare exp create <experiment_name> --env <environment_name>

This will create a directory within the environments experiment directory containing two templates for the so called action as well as testset file.

The action file is a python file that contains the user action performed within the experiment, such as mouse clicks or keyboard inputs.
Additionally to that it can also contains a prepare function, which can be used to create files or directories needed for the user actions.
An simple example could be an action file containing user actions to delete a file.
The action file would then contain a sequence of commands to open the file explorer, navigate to the file and delete it.
Additionally to that the action file would also contain a prepare function to create the file to be deleted.
The action file would then look like this:

.. code-block:: python

    from pathlib import Path
    import sys

    from guiautomation.Experiment.Experiment import Experiment
    from guiautomation.run import run
    from guibot.guibot import GuiBot

    import logging
    log = logging.getLogger(__name__)


    class deletefile(Experiment):
        description = "Delete file from home folder to Trash Bin (Ubuntu)"
        guibot: GuiBot = None

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def prepare(self):
            file = "C:/Users/vagrant/Documents/testfile"
            log.info(f'create the file {file}.')
            with open(file, mode="w") as f:
                f.write("GEHEIM!")
            log.info(f'file {file} created.')

        def run(self):
            guibot = self.guibot

            log.info(f'experiment {type(self).__name__} started')

            match = self.find('files.png')
            if match:
                guibot.click(match[0])
                guibot.idle(5)
            else:
                log.error('files.png button does not exist')
                return 'failed'

            match = self.find_text('Documents')
            if match:
                guibot.click(match[0])
                guibot.idle(5)
            else:
                log.error('documents text does not exist')
                return 'failed'

            match = self.find_text('testfile')
            if match:
                guibot.click(match[0])
                guibot.idle(5)
                guibot.press_keys(guibot.dc_backend.keymap.DELETE)
                self.save_time("DELETIONDATE")
            else:
                log.error('testfile text cant be found')
                return 'failed'

            log.info(f'experiment {type(self).__name__} done')
            return self.status


    if __name__ == '__main__':
        if len(sys.argv) < 2:
            print('missing file for config path')
            exit(-1)
        run(deletefile, config_file=Path(sys.argv[1]))



The testset file is a yaml file performing tests after the user action is performed.
The testset file would then contain a test to check whether the file was deleted and a test whether the trash bin contains the deleted file.
It would then look like this:

.. code-block:: yaml

    name: deletefile
    tests:
      - name: existencefile
        description: 'check if file exists'
        type: is_not_file
        params:
          dst: 'C:/Users/vagrant/Documents/testfile'
      - tool: RBCmd.exe
        command: 'RBCmd.exe -d C:\ --csv C:/Users/vagrant/Documents/test'
        tests:
          - name: deletedfileInfo
            description: 'check if file metadata exists'
            type: csv_entry_exists
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
          - name: deletedfileData
            description: 'check if file data exists'
            type: csv_entry_exists
            params:
              dst: 'C:/Users/vagrant/Documents/test/*.csv'
              entry:
                - !reALL
                - '$R'
                - 'C:\Users\vagrant\Documents\testfile'
                - !re '.*'
                - !reALL



More detailed explanation as well as details how to create both files can be found in section :ref:`basics/actionfile:Action File` and :ref:`basics/testsetfile:Testset File` respectively.

After the action and testset file are created, the experiment can be executed by running the following command::

    adare exp run <experiment_name> --env <environment_name>

This will start the vagrant box and execute the experiment on it.
Depending on the experiment, the experiment can take a while to finish.
After the experiment is finished, the results are shown to the user.
Additionally to that the results can be viewed via the gui as described in section :ref:`gui/index:Graphical User Interface`.


