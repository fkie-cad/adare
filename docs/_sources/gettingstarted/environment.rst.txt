Create an Environment
**********************

An environment defines the vagrant box to be used combined with metadata about the guest OS.
Additionally it can contain a list of installations to run before the experiment.
This data is specified in a YAML file we call the environment configuration file.

To load an environment into an project, we can run the ``adare environment load <environment_name>`` command.
Therefore the environment configuration file must be located in the ``environments`` directory within the project directory.

All options allowed in the environment configuration file are listed in the table below:

.. csv-table:: potential options in the environment configuration file
    :file: /_static/tables/environment_configuration_fields.csv
    :delim: |
    :widths: 30, 20, 50
    :header-rows: 1
.. note::
    Fields marked with an asterisk (*) are optional.


