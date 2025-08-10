.. ADARE documentation master file, created by
   sphinx-quickstart on Sun May  8 13:28:54 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. role:: boldprimary
   :class: boldprimary

Welcome to ADARE's documentation!
==================================

Welcome to the documentation of *ADARE* - the :boldprimary:`A`\ utomated :boldprimary:`D`\ esktop :boldprimary:`A`\ nalysis framework for :boldprimary:`R`\ eproducible :boldprimary:`E`\ xperiments.

ADARE is a framework designed to detect changes in forensic artifacts or forensic tools across different software and operating system versions.
By combining automated GUI actions that mimic user behavior with structured tests to validate expected artifact behavior, ADARE enables comprehensive forensic experimentation within a virtual machine environment.

Users can leverage ADARE to reproduce and validate existing experiments or create their own forensic experiments.
Additionally,  `Adare Web <https://adare.seclab-bonn.de/>`_ provides a platform for sharing experiments and results with the community.

For a step-by-step guide on using ADARE, it is recommended to start with the :ref:`gettingstarted/index:Walkthrough: Quick Start Guide` chapter, which explains how to create and run experiments.


.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Contents:

   installation/index
   gettingstarted/index
   architecture/index
   cli/index
   advanced/index