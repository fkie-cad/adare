****************
Walkthrough
****************

This is a walkthrough providing information how to setup ADARE to run downloaded experiments and to create new experiments.
To use ADARE you must setup a project, which is basically a directory containing data used for the experiments.
This can be simply done by navigating to the directory where you want to create the project and run the following command::

    adare proj create <project_name>

This will create a directory with the name <project_name> and within it data, such as data used for the text recognition within the experiemnts.


Within this project a user must create an environment, dedicated to contain experiments related to one specific virtual machine.
This can be done by running the following command, when providing an environment config file::

    adare env create  <environment_config_file>.yml --name <environment_name>

The environment config file is a yaml file containing information about the environment that is to be created.
It contains the vagrant box that should be used along with the operating system, telling Adare whether the box is a Windows or Linux box.
Additionally to that it is also possible to provide a list installations to be done after the box is started to install further applications needed to run the experiment.
An example of such a file is provided below.
In section :ref:`Environment Configuration File`_ you can find a detailed description of the environment config file and it possible configurations.


.. code-block:: yaml

    name: <environment_name>
    vagrantbox: <vagrant_box_name>
    os_platform: <os_platform> (Windows or Linux)
    ...



