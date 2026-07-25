*******
Sharing
*******

ADARE Web Platform
==================

The ADARE web platform at `adare.seclab-bonn.de <https://adare.seclab-bonn.de>`_ is a community hub for sharing forensic experiments, environments, test functions, and results. Researchers can publish their work, download experiments created by others, and build on the community's collective forensic analysis.

The platform supports sharing of:

- **Experiments** -- playbooks and metadata for forensic analysis workflows
- **Environments** -- VM configurations (OS profiles, settings)
- **Test functions** -- reusable validation logic for forensic artifacts
- **Experiment bundles** -- complete packages with experiments and all their dependencies
- **Run results** -- published experiment execution results with forensic data

All sharing operations are performed through the ``adare web`` command group.


Authentication
==============

You must be logged in to interact with the ADARE web platform.

Logging In
----------

.. code-block:: bash

   adare web login

This starts an interactive authentication flow that connects your local ADARE installation to your account on the web platform.

Logging Out
-----------

.. code-block:: bash

   adare web logout

Checking Login Status
---------------------

.. code-block:: bash

   adare web status

Shows whether you are currently logged in and displays your username.


Downloading Resources
=====================

Download shared content from the platform into your local project. All download commands require being inside an ADARE project directory (or specifying one with ``-p``).

Downloading Experiments
-----------------------

.. code-block:: bash

   adare web download experiment <ulid>

Downloads an experiment by its ULID (unique identifier). The experiment is added to your project's ``experiments/`` directory.

.. code-block:: bash

   # Example
   adare web download experiment 01JQXYZ123ABC

Downloading Test Functions
--------------------------

.. code-block:: bash

   adare web download testfunction <name>

   # Download a specific version
   adare web download testfunction <name> -v 2

Downloads a test function by name. By default, the latest version is downloaded. Use ``-v`` to specify a particular version.

.. code-block:: bash

   # Download the latest version
   adare web download testfunction standard.file_exists

   # Download version 3 specifically
   adare web download testfunction excel.validate_columns -v 3

Downloading Environments
------------------------

.. code-block:: bash

   adare web download environment <name>

Downloads an environment configuration by name.

.. code-block:: bash

   adare web download environment ubuntu24043

Downloading Bundles
-------------------

.. code-block:: bash

   adare web download bundle <ulid>

Downloads an experiment bundle: the experiment plus all its dependencies (testfunction sets and referenced environment configurations). Only descriptor/config files are downloaded — VM disk images are fetched later, on demand, when the environment is loaded (see below).

.. code-block:: bash

   adare web download bundle 01JQXYZ123ABC

Options
^^^^^^^

``-p, --project``
   Target project name or path.


Replicating an Experiment (one command)
========================================

To download a published experiment and immediately run it — the easiest way to reproduce a result end to end:

.. code-block:: bash

   adare experiment replicate <ulid>

This downloads the bundle, loads the environment (fetching and verifying the VM disk via its ``sha256``), loads the experiment, and runs it in test mode.

.. code-block:: bash

   # Auto-selects the environment if the bundle has exactly one
   adare experiment replicate 01JQXYZ123ABC

   # Pick an environment when the bundle has more than one
   adare experiment replicate 01JQXYZ123ABC -e ubuntu24043

   # Run for real (production mode) instead of test mode
   adare experiment replicate 01JQXYZ123ABC --production

   # Only download and load, don't run
   adare experiment replicate 01JQXYZ123ABC --skip-run

Options
^^^^^^^

``-e, --environment``
   Name of the environment to use. Required if the bundle has more than one; optional (auto-selected) if it has exactly one.

``--production, --prod``
   Run in production mode with full integrity checks (default: test mode).

``--skip-run``
   Download and load only, without starting a VM.

``-p, --project``
   Target project name or path.


Running Downloaded Experiments Manually
========================================

You can also perform the download/load/run steps yourself instead of using ``adare experiment replicate``:

.. code-block:: bash

   # Download an experiment
   adare web download experiment 01JQXYZ123ABC

   # Run it (same as any local experiment)
   adare experiment run downloaded-experiment -e ubuntu24043

   # Or use it in dev mode
   adare dev start -e ubuntu24043
   adare dev playbook -f experiments/downloaded-experiment/playbook.yml

Downloaded test functions are automatically available for use in playbooks.


Syncing
=======

Synchronize your project data with the web platform:

.. code-block:: bash

   adare web sync

   # Sync a specific project
   adare web sync -p my-project

This updates the platform with your local project information, ensuring the web interface reflects your current experiments, environments, and test functions.


Publishing Results
==================

Share your experiment run results with the community:

.. code-block:: bash

   adare web publish <run_ulid>

   # With explicit project
   adare web publish 01JRXYZ456DEF -p my-project

This uploads the results of a specific experiment run, including all collected forensic data, test outcomes, and execution metadata. Published results are visible to other researchers on the platform.

The ``<run_ulid>`` is the unique identifier of the experiment run, which is displayed when you execute ``adare experiment run`` or can be found with ``adare experiment list-runs``.


Submitting to the Community
============================

Submit your experiments, test functions, or environments for inclusion in the shared community repository. Submissions are created as pull requests that are reviewed before being merged.

Submitting an Experiment
------------------------

.. code-block:: bash

   adare web submit experiment <name>

   # With explicit project
   adare web submit experiment browser-analysis -p my-project

Submitting a Test Function
--------------------------

.. code-block:: bash

   adare web submit testfunction <name>

   # Example
   adare web submit testfunction standard.file_exists -p my-project

Submitting an Environment
-------------------------

.. code-block:: bash

   adare web submit environment <name>

   # Example
   adare web submit environment ubuntu24043 -p my-project

Each submit command creates a pull request on the shared repository. You receive a PR URL upon successful submission that you can use to track the review process.


Checking Status
===============

Verify whether your experiments or runs have been published to the server.

Checking an Experiment
----------------------

.. code-block:: bash

   adare web check experiment <ulid>

Reports whether the experiment exists on the server and its publication status.

Checking a Run
--------------

.. code-block:: bash

   adare web check run <ulid>

Reports whether the experiment run exists on the server.


.. seealso::

   :doc:`/guide/experiments`
      Experiment structure and running experiments

   :doc:`/reference/cli`
      Full CLI reference

   :doc:`/getting-started/concepts`
      ADARE concepts including the web platform
