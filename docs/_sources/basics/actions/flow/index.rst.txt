Flow Control
============

Actions for controlling playbook execution flow - delays, conditional execution, loops, and branching.

Available Actions
-----------------

.. toctree::
   :maxdepth: 1

   idle
   wait_until
   block
   loop
   stop
   continue

Overview
--------

Flow control actions enable dynamic playbook behavior:

- **idle**: Fixed-duration delays
- **wait_until**: Wait for GUI conditions
- **block**: Group and conditionally execute actions
- **loop**: Repeat actions or iterate over lists
- **stop**: Halt execution conditionally
- **continue**: Skip to next iteration

These actions support variable conditions, boolean logic, and nested control structures for complex forensic scenarios.
