Create an Experiment
*********************

When an experiment is created via ``adare experiment create <experiment_name>``, the following files are created within the experiments directory of our project.

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


Testset File
#############


Action File
############

When creating an experiment, an action file skeleton is created, looking like the following:

.. code-block:: python

    from adarevm.action.experiment import Experiment, KEYMAP
    from pathlib import Path
    from typing import Callable, Awaitable
    from adarevm.testset.testset import Testset

    import logging

    log = logging.getLogger(__name__)


    class ExperimentExample(Experiment):
        description = ''

        def __init__(self, img_folder: Path, tessdata_folder: Path, testset: Testset,
                     log_func: Callable[[str], Awaitable[None]]):
            """
                initialization function which in most cases should not be changed (except there is a need to use a different display controller or computer vision backend for guibot)
            """
            super().__init__(img_folder, tessdata_folder, testset, log_func)

        def prepare(self) -> tuple[bool, str]:
            """
                this function can be used to execute some commands before the clicks happen (e.g. creating a file)
            """
            pass

        def run(self) -> tuple[bool, str]:
            """
                this function should be used to execute the gui automation steps
            """
            log.info(f'experiment {self.name} started')

            pass

            log.info(f'experiment {self.name} done')

            return True, ''


The ``Experiment`` base class provides some methods to enable gui automation as well as the execution from tests.

Gui Automation Methods
----------------------

.. py:function:: find(image_name: str, minimal_similarity: float = 0.6, similarity_steps. float = 0.1) -> list[guibot.match.Match] or None

        Finds the image in the current screen and returns a list of matches or None if no match was found.
        Therefore, creates a chain of searches starting with a 90% similarity and decreasing the similarity by 10% until the image is found.
        If the image is not found with a similarity of the minimal similarity parameter the search is aborted and None is returned.

        :param image_name: the name of the image to find
        :type image_name: str
        :param minimal_similarity: the minimal similarity to find the image with
        :type minimal_similarity: float
        :param similarity_steps: the steps to decrease the similarity by
        :type similarity_steps: float

        :return: a list of matches or None if no match was found


.. py:function:: find_text(text: str) -> list[guibot.match.Match] or None

        Finds the text in the current screen and returns a list of matches or None if no match was found.

        :param text: the text to find
        :type text: str
        :return: a list of matches or None if no match was found


.. py:function:: click(target_or_location: guibot.match.Match, modifiers: list[str] = [])

        Left Click on the given match, previously found with the find method or manually created.

        :param target_or_location: the match to click on (or an object with x and y coordinates)
        :type match: guibot.match.Match
        :param modifiers: special keys to hold during clicking (e.g. ['ctrl', 'shift'])

.. py:function:: right_click(target_or_location: guibot.match.Match, modifiers: list[str] = [])

        Right Click on the given match, previously found with the find method or manually created.

        :param target_or_location: the match to click on (or an object with x and y coordinates)
        :type match: guibot.match.Match
        :param modifiers: special keys to hold during clicking (e.g. ['ctrl', 'shift'])

.. py:function:: double_click(target_or_location: guibot.match.Match, modifiers: list[str] = [])

        Double Click on the given match, previously found with the find method or manually created.

        :param target_or_location: the match to click on (or an object with x and y coordinates)
        :type match: guibot.match.Match
        :param modifiers: special keys to hold during clicking (e.g. ['ctrl', 'shift'])

.. py:function:: drag_and_drop(source: guibot.match.Match, target: guibot.match.Match, modifiers: list[str] = [])

        Drags the source match to the target match.

        :param source: the match to drag
        :type source: guibot.match.Match
        :param target: the match to drop the source on
        :type target: guibot.match.Match
        :param modifiers: special keys to hold during dragging (e.g. ['ctrl', 'shift'])


.. py:function:: press_keys(keys: list[str] or str)

        Presses the given key or keys

        :param keys: the keys to press
        :type keys: list[str] or str


.. py:function:: idle(timeout: int)

        Idles the experiment for the given amount of time.

        :param timeout: the time to idle in seconds
        :type timeout: int


.. py:function:: exec_command(command: list, cwd: str = '')

        Executes the given command in the shell.

        :param command: the command to execute
        :type command: list
        :param cwd: the working directory to execute the command in
        :type cwd: str

Test Methods
------------

.. py:function:: run_test(name: str)

        Runs the test with the given name.

        :param name: the name of the test to run
        :type name: str

.. py:function:: run_tests(names: list[str])

        Runs a list of tests with the given names.

        :param names: the names of the tests to run
        :type name: str

.. py:function:: error(name:str, message: str)

        Logs an error message with the given name and message.

        :param name: the name of the error
        :type name: str
        :param message: the message of the error
        :type message: str


Other Methods
-------------

In some cases it might be necessary to save certain data during the action phase that may be needed later on in the preformed tests (such as timestamps).
Therefore the ``Experiment`` class offers the two methods described below.

.. py:function:: save_variable(name: str, value: str)

        Saves the given value under the given name in the variables file.

        :param name: the name to save the value under
        :type name: str
        :param value: the value to save
        :type value: str

.. py:function:: save_time(timestamp_var_name: str)

        Saves the current timestamp under the given name in the variables file.

        :param timestamp_var_name: the name to save the timestamp under
        :type timestamp_var_name: str




Metadata File
#############



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








