Create an Experiment
*********************

When an experiment is created via ``adare experiment create <experiment_name>``, the following files are created within the experiments directory of our project.

::

    <project>/
    ├── experiments/
    │   ├── ...
    │   └── <experiment_name>/
    │       ├── playbook.yml
    │       ├── testset.yml
    │       ├── metadata.yml
    │       ├── img/
    │       └── shared/
    └── ...


Testset File
#############

The testset file is a YAML file that contains a list of tests.
So its basic structure looks like the following:

.. code-block:: yaml

    name: <experiment_name>                 // name of the experiment
    tests:                                  // list of tests
      - name: <test_name>                   // custom name for the test
        description: <test_description>     // custom description for the test
        function: <test_function>           // testfunction to be used (from testfunctionset)
        depends_on: <command_name>          // [opt.] command (defined by command name) that the test depends on
        parameters:                         // list of required parameters for the testfunction
            <param_name>: <param_value>     // parameter name and value
            ...
      - ...
    commands:                               // [opt.] list of commands
      - name: <command_name>                // custom name of the command
        description: <command_description>  // custom description for the command
        tool: <executable_name>             // name or path to the executable
        command: <command>                  // command to be executed



Playbook File
##############

The playbook.yml file defines the GUI automation steps for your experiment using simple YAML syntax. A basic playbook looks like this:

.. code-block:: yaml

    actions:
      # Run initial test
      - test:
          name: "initial_check"
          description: "Verify initial state"
      
      # Click on text in the UI
      - click:
          target:
            text: "Start"
          description: "Click the Start button"
      
      # Type some text
      - keyboard:
          keys: "Hello World"
          description: "Type text"
      
      # Use keyboard shortcuts
      - keyboard:
          combination: ["ctrl", "s"]
          description: "Save with Ctrl+S"
      
      # Run final test
      - test:
          name: "final_check"
          description: "Verify success"

Common Actions
**************

The playbook supports these basic GUI actions:

- **click**: Click on text, images, or coordinates
- **keyboard**: Type text or keyboard combinations  
- **test**: Run validation tests (defined in testset.yml)
- **idle**: Wait/pause between actions

For advanced features and complete reference, see :ref:`gettingstarted/playbook_reference:Complete Playbook Reference`.



Develop and Run an Experiment
******************************

To run an experiment the following command is used:

::

    adare experiment run <experiment_name> -e <environment_name>

Note, that this loads the experiment before running it in case it is not already loaded.
An loaded experiment should not be modified, and ADARE will reject loading an experiment, where already runs exist to ensure the integrity of the experiment.
This behavior may be annoying within the development of an experiment, where the experiment is modified and rerun multiple times to test it is working as expected.
We therefore provide the option ``--fake`` to run an experiment without loading it.
This deletes all run related information from the run from the database.

Since developing an experiment often requires to manually test steps inside the virtual machine, we provide the develop command.

::

    adare experiment develop <experiment_name> -e <environment_name>

This command open a terminal gui, that allows to run the experiment step by step.
It also allows the user to rerun the action multiple times with in between modifications of the action and testset files.








