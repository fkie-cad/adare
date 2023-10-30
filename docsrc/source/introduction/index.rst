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

The environment config file is a yaml file containing information about the used vagrant machine.
An example of such a file is provided below.

.. code-block:: yaml

    vagrant:
        box: ubuntu/trusty64
        box_url: https://cloud-images.ubuntu.com/vagrant/trusty/current/trusty-server-cloudimg-amd64-vagrant-disk1.box
        memory: 2048
        cpus: 2
        network:
            - type: private_network
              ip:

