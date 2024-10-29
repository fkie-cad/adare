******************
Installation Guide
******************
To install adare, make sure to install make as well as the python packaging tool `poetry <https://python-poetry.org/docs/#installing-with-the-official-installer>`_.
Afterwards clone the `repository <https://github.com/fkie-cad/Adare>`_, navigate into the directory and run ``make install``.
To check whether the tool is successfully installed and ready to use run ``adare -v``.


Requirements
************
One of the necessary tools to use adare is `Vagrant <https://www.vagrantup.com/>`_, which manages virtual machines.
Additionally, a virtual machine hypervisor is required.
Currently, only `VirtualBox <https://www.virtualbox.org/>`_ is supported.
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
     - ``3.10``
   * - Vagrant
     - ``2.3.2``
   * - VirtualBox
     - ``6.1``, ``7.0``

