***********************
About ADARE
***********************

ADARE is a desktop forensic analysis tool.
It's main purpose is to monitor artifact changes over different os and software version in an automated way.

ADARE on one side uses virtual machines via vagrant, in which the experiment will take place.
On a high level a desktop forensic experiment is divided into two main phases:

1. action phase (sequence of gui actions such as mouse clicks and key presses)
2. parsing phase (parsing of forensic artifacts)
3. analysis phase (analysis of parsed artifacts as well as the state of the virtual machine)

Users can use ADARE to reproduce already existing experiments or write their own experiments.
To view the results of an experiment run ADARE's web interface as well as CLI can be used.

It is recommended to read the :ref:`introduction/index:Walkthrough` chapter first, which shows how to use create and run experiments.
