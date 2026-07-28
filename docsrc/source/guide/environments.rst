************
Environments
************

Environments define virtual machine configurations for running experiments.

Environment Configuration
**************************

Environments are defined using YAML files. The environment's **name** always comes
from the filename stem, never from a field inside the file.

Every environment declares exactly one **VM source**, and which one it is decides
which other fields apply:

.. list-table::
   :header-rows: 1
   :widths: 18 22 60

   * - ``vm_type``
     - Source field
     - Meaning
   * - ``path``
     - ``vm``
     - A local disk image. Reference-only: not publishable.
   * - ``url``
     - ``vm`` + ``vm_sha256``
     - A baked disk hosted at an ``http(s)`` URL, verified after download.
   * - ``recipe``
     - ``recipe:``
     - Built on load from declared inputs. See :ref:`recipe-environments`.
   * - ``auto``
     - ``vm``
     - Default; infers ``path`` or ``url`` from the value.

Baked disk, local (``vm_type: path``)
=====================================

.. code-block:: yaml

   vm: /Users/me/.adare/state/vms/win11.qcow2
   vm_type: path
   vm_sha256: "abc123..."          # optional here; verified on load when present
   os:
     os: "Windows 11"
     platform: "windows"           # or "linux"
     distribution: "Pro"
     version: "11"
     language: "English"
     architecture: "x86_64"        # or aarch64
   hypervisor: qemu
   tags: ["windows", "forensics"]
   description: "Windows 11 forensics environment"

Baked disk, published (``vm_type: url``)
========================================

.. code-block:: yaml

   vm: https://cloud.example.org/s/TOKEN/download
   vm_type: url
   vm_sha256: "abc123..."          # REQUIRED for a URL source
   vm_format: qcow2                # REQUIRED when the URL has no disk extension
   os: {os: "Ubuntu 24.04", platform: linux, distribution: ubuntu}
   hypervisor: qemu

Produced by ``adare env publish-prepare <name> --vm-url <url>``, which hashes the
local disk and rewrites the descriptor.

Recipe (``vm_type: recipe``)
============================

.. code-block:: yaml

   vm_type: recipe
   hypervisor: qemu
   recipe:
     profile: windows11arm64       # resolves via the OS profile catalog
     iso_name: Win11_25H2_English_Arm64_v2.iso   # or `iso:` (path / http(s) URL)
     iso_sha256: "638aa2c8..."     # REQUIRED; the integrity boundary
     iso_notes: "Download from microsoft.com/software-download/windows11"
     template: autounattend_win11_arm64.xml
     params: {setup_level: 2, disk_size: 160G, ram_mb: 8192, cpus: 4}
     provision:                    # build-time steps, run once (see below)
       - {name: my-tool, command: "msiexec /i C:\\tmp\\t.msi /qn", allow_exit_codes: [0, 3010]}
   os: {os: "Windows 11 (ARM64)", platform: windows, distribution: Home,
        version: '11', language: English, architecture: aarch64}

In recipe mode the ``os:`` block is optional -- it is derived from the profile when
omitted. Full details, including build-time provisioning and consumer-supplied
ISOs, are in :ref:`recipe-environments`.

Required Fields
===============

- **A VM source**: one of ``vm``, ``recipe``, or legacy ``vagrantbox``.
- **os.platform**: ``windows`` or ``linux`` (optional for a recipe, which derives
  it from the profile).
- **vm_sha256**: required when ``vm`` is a URL.
- **recipe.iso_sha256**: required for every recipe.

Optional Fields
===============

- **vm_type**: ``auto`` (default), ``path``, ``url``, or ``recipe``.
- **vm_format**: disk format hint (``qcow2``/``ova``/``vmdk``/``vdi``/``img``/``raw``);
  required for a URL with no recognizable disk extension.
- **postsetupinstallations**: commands run inside **every experiment run**. Not the
  place to install software under test -- see ``recipe.provision`` in
  :ref:`build-time-provisioning` for why.
- **tags**: labels for organization
- **description**: environment purpose
- **hypervisor** / **hypervisor_config**: hypervisor selection and per-hypervisor
  settings (e.g. ``boot_mode: bios``)
- **vagrantbox**: legacy Vagrant box (backward compatibility)

Managing Environments
*********************

.. code-block:: bash

   # Load environment from config file (for a recipe, this BUILDS the disk)
   adare environment load config.yml

   # Recipe with a consumer-supplied ISO: point ADARE at the file (or its directory)
   adare env load config.yml --iso ~/Downloads/Win11_25H2_English_Arm64_v2.iso

   # Retry only the build-time provisioning stage, reusing the cached OS install
   adare env load config.yml --reprovision

   # List environments
   adare environment list

   # Delete environment
   adare environment delete my-environment

Checking that an environment can actually boot
**********************************************

``adare environment list`` shows a **disk** column and ``adare env info`` a
**disk** row, both reporting the backing disk of the environment's registered VM:

* ``ok`` / ``present`` -- the disk file exists
* ``MISSING`` -- the environment is registered but its disk is gone, so any run
  against it will fail during VM setup
* ``-`` -- nothing local to check (for example a URL-baked environment)

This is deliberately separate from the *file path* column, which is the
environment's YAML descriptor under ``~/.adare/state/environments/``. That
descriptor keeps existing after its qcow2 has been pruned, so an environment
whose disk is gone otherwise looks completely healthy in every listing and only
fails once a run reaches VM setup. Check the ``disk`` column, not the file path,
before concluding that an environment is usable.

An environment reported as ``MISSING`` can be removed with ``adare env remove``.
Remove its name from any experiment that lists it first (``adare experiment
remove-env``): without ``--force``, ``env remove`` refuses to orphan an
experiment, and with ``--force`` it deletes the orphaned experiments too.

VM Storage Options
******************

By default, when you load an environment with a VM, ADARE copies the VM file (OVA) to managed
storage at ``~/.adare/state/vms/``. This ensures the VM is protected and always available for
experiments.

However, for very large VM files (e.g., >50GB), you may want to avoid duplicating the file to
save disk space.

Using ``--no-copy`` Flag
========================

The ``--no-copy`` flag tells ADARE to reference the VM at its original location instead of
copying it:

.. code-block:: bash

   adare environment load my-environment.yml --no-copy

.. important::

   When using ``--no-copy``, the original VM file **must remain at its current location**.
   Do not move or delete it, or your experiments will fail!

**When to use ``--no-copy``:**

* You have very large VM files (50GB+) and limited disk space
* You want to keep VMs on external storage or network drives
* You are certain the VM file location won't change

**What happens if you move the file:**

If the VM file is moved or deleted after loading with ``--no-copy``, you'll see an error when
trying to run experiments:

.. code-block:: text

   External VM file not found: /path/to/original/vm.ova
   This VM was loaded with --no-copy and the original file is missing.

**Note:** The ``--no-copy`` flag only works with local file paths. If your environment specifies
a URL for the VM, the file will always be downloaded to managed storage.

The environment configuration determines what VM is used and any setup commands that run before experiments execute.