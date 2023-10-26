***********************
About ADARE
***********************

What is ADARE?
****************

ADARE is a desktop forensic analysis tool.
It's main purpose is to monitor artifact changes over different os and software version in an automated way.

ADARE on one side uses virtual machines via vagrant, in which the experiment will take place.
On a high level a desktop forensic experiment is divided into three main parts:

1. gui experiment (sequence of gui actions such as mouse clicks and key presses)
2. parsing artifacts
3. analyze the parsed artifacts


The user provides a so called *experiment*, consisting of a *gui automation file* and a *parse and test file*.
Inside the *gui automation file* is specified


The experiments itself consists each of a *gui automation* and *parse & test* part.
During the *gui automation* part an user written gui experiment, such as clicking on a file and deleting it to the Trash Bin, will be executed.
Afterwards in the *parse & test* the user can provide a way

Architecture
****************
