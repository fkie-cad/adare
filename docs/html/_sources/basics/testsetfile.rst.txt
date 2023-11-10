Testset File
*************

The testset file is a yaml file, which tells the tests to be executed after the gui automation took place.
The file is structured as follows:

.. code-block:: yaml

    name: <experiment_name>
    tests:
      - name: <test_name>
        description: <test_description>
        type: <test_function>
        params:
          <test_parameter_0>: <test_value_0>
          <test_parameter_1>: <test_value_1>
          ...
      ...

The file contains the name of the experiment (`<experiment_name>`) and a list of tests (`tests`).
Each test has a name (`<test_name>`), a description (`<test_description>`), a type (`<test_function>`) and a list of parameters (`params`).
In some cases it is required to first run a tool before executing the test, since those tool might parse the forensic artifact.
Therefore it is possible to, instead of a test place a tool block as shown below.
This tool block contains the name of the tool (`<tool_name>`) and the command to be executed (`<tool_command>`).
After the tool is executed, the tests in the `tests` list are executed.
Additionally it is worth noting, that all tests get executed in the order they are defined in the testset file.

.. code-block:: yaml

    name: <experiment_name>
    tests:
      - name: <test_name>
        description: <test_description>
        type: <test_function>
        params:
          <test_parameter_0>: <test_value_0>
          <test_parameter_1>: <test_value_1>
          ...
        - tool: <tool_name>
            command: <tool_command>
            tests:
                ...


Testfunctions
#############

Adare offers a variety of testfunctions listed below.
Additionally it is possible to write your own testfunctions as described in :ref:`advanced/testfunction:Write your own Testfunction`.
Additionally to the classic types in yaml (str, int, float, bool, list, dict) within the parameters of the testfunction additional types are used.
These types are used within yaml by setting a prefix before the value, such as `!re <str>` for a regular expression.

.. list-table::
    :widths: 15 15 70
    :header-rows: 1

    *  - Type
       - Prefix
       - Description
    *  - regex
       - !re <str>
       - arbitrary regex expression
    *  - regexALL
       - !reALL
       - regex expression '.*'
    *  - timestamp
       - !timestamp <dict>
       - timestamp with tolerance



Some examples how to use this types is shown in the yaml file below.

.. code-block:: yaml

    example_regex: !re '[a-zA-Z]*'
    example_regex_all: !reALL
    example_timestamp: !timestamp
      timestamp: 1699381083
      tolerance: 30

Below the testfunctions are listed with their parameters and a short description.


.. py:function:: is_file

    tests if a file with path destination(dst) is existing

    :param dst: path to the file to be tested
    :type dst: str


.. py:function:: is_not_file

    tests if a file with path destination(dst) is NOT existing

    :param dst: path to the file to be tested
    :type dst: str


.. py:function:: is_dir

    tests if a directory with path destination(dst) is existing

    :param dst: path to the directory to be tested
    :type dst: str


.. py:function:: is_not_dir

    tests if a directory with path destination(dst) is NOT existing

    :param dst: path to the directory to be tested
    :type dst: str


.. py:function:: dir_content

    tests if a directory has the expected files/folders

    :param dst: path to the directory to be tested
    :type dst: str
    :param expected: list of expected files/folders
    :type expected: list


.. py:function:: regex_match

    tests if file content matches a given regex expression

    :param dst: path to the file to be tested
    :type dst: str
    :param regex: regex expression to be matched
    :type regex: regex,regexALL


.. py:function:: csv_entry_exists

    tests if row in a given csv file (dst) exists, which matches the given layout provided (entry)

    :param dst: path to the csv file to be tested
    :type dst: str
    :param entry: list of strings and regex expressions to be matched
    :type entry: list[str,regex,regexALL,timestamp]


Examples
########

An example testset file to test whether the windows trash bin work as expected is provided below.

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



