******************
Installation Guide
******************
To install adare, make sure to install make as well as the python packaging tool `poetry <https://python-poetry.org/docs/#installing-with-the-official-installer>`_.
Afterwards clone the `repository <https://github.com/fkie-cad/Adare>`_, navigate into the directory and run ``make install``.
To check whether the tool is successfully installed and ready to use run ``adare --version``.


Requirements
************
One of the necessary tools to use adare is `VirtualBox <https://www.virtualbox.org/>`_.
Moreover, if you run adare from a Windows machine, you need to make sure that Hyper-V is disabled, since Hyper-V and the VirtualBox hypervisor interfere each other, which can cause slow and hanging machines.


Tested Configurations
*********************

The tool was tested with the following versions of Python, Vagrant, and VirtualBox:

.. list-table::
   :widths: 25 30
   :header-rows: 1

   * - program
     - versions
   * - Python
     - ``3.10.2``
   * - poetry
     - ``1.8.2``
   * - VirtualBox
     - ``6.1``, ``7.0``

Later versions of the programs should also work, but have not been tested yet.
Earlier versions especially of Python might not work, since adare uses some features that were introduced in Python 3.10.
