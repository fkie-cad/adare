******************
VM Image Creation
******************

ADARE creates QEMU/KVM virtual machines with automated OS installation. The
``adare vm create`` command handles ISO download, unattended install, disk
provisioning, and ADARE agent setup in a single step.

This guide covers when and how to create custom VM images for your research,
from quick-start commands through advanced profile customization to registering
the finished VM as an ADARE environment.


When and Why to Create Custom VMs
==================================

The pre-built ADARE images cover common configurations, but custom VMs are
needed when:

- **Specific OS versions** -- your research targets a particular build number,
  service pack, or point release not available as a pre-built image.
- **Specific software versions** -- you need a known version of an application
  (e.g., Firefox 102 ESR, Office 2019) pre-installed for consistent baselines.
- **Custom configurations** -- your experiment requires non-default OS settings,
  group policies, locale, or timezone configurations.
- **Non-supported distributions** -- you are working with a Linux distribution
  or Windows variant that ADARE does not ship a profile for.
- **Forensic baselines** -- you need a clean, minimal OS install with nothing
  extra installed so that every artifact in the diff is attributable to your
  experiment.


Quick Start
===========

Linux (fully automated)
-----------------------

.. code-block:: bash

   # Ubuntu 24.04 -- downloads ISO, installs unattended, pre-installs ADARE agent
   adare vm create ubuntu2404

   # Ubuntu 22.04 with custom name and larger disk
   adare vm create ubuntu2204 --name my-ubuntu --disk-size 100G --ram 8192

   # Bare install -- OS only, no guest tools or Python
   adare vm create ubuntu2404 --setup bare

   # Base install -- guest tools only, no Python environment
   adare vm create ubuntu2404 --setup base

Windows (user-supplied ISO)
---------------------------

.. code-block:: bash

   # Windows 11 -- requires a Windows ISO from Microsoft
   adare vm create windows11 --iso /path/to/Win11.iso

   # Windows 10
   adare vm create windows10 --iso /path/to/Win10.iso

   # Windows 11 ARM64 on Apple Silicon
   adare vm create windows11arm64 --iso /path/to/Win11_ARM64.iso

   # Or use --arch to override any profile's architecture
   adare vm create windows11 --arch aarch64 --iso /path/to/Win11_ARM64.iso

Manual ISO install
------------------

For OSes without a built-in unattended template, use a custom profile with
``install_mode: manual`` and pass your ISO:

.. code-block:: bash

   adare vm create my-custom-os --iso /path/to/installer.iso


Options
=======

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Option
     - Description
   * - ``--iso PATH``
     - Path to OS installer ISO (required for Windows and manual profiles)
   * - ``--name NAME``
     - VM name (auto-generated as ``<os>-YYYYMMDD`` if omitted)
   * - ``--disk-size SIZE``
     - Disk image size, e.g. ``60G``, ``100G`` (default from OS profile)
   * - ``--ram MB``
     - RAM in megabytes (default from OS profile)
   * - ``--cpus N``
     - CPU core count (default: half of host cores, clamped 2--8)
   * - ``--setup LEVEL``
     - Setup level: ``bare`` (OS only), ``base`` (+ guest tools), ``full`` (+ Python, default), ``agent`` (+ adarevm, deferred)
   * - ``--interactive``
     - Boot the VM after automated install for manual customization
   * - ``--force``
     - Overwrite an existing disk image with the same name
   * - ``--vm-dir DIR``
     - Directory for the disk image (default: ``~/.adare/state/vms/``)
   * - ``--arch ARCH``
     - Override CPU architecture: ``x86_64`` or ``aarch64`` (default from OS profile)
   * - ``--env-name NAME``
     - Environment file name (defaults to VM name)


Setup Levels
============

Each level is cumulative -- it includes everything from the levels below it.

.. list-table::
   :header-rows: 1
   :widths: 12 30 58

   * - Level
     - What it adds
     - Use case
   * - ``bare``
     - OS + user + basic config (autologin, UAC/sleep disabled)
     - Forensic baselines, custom provisioning
   * - ``base``
     - Guest tools (see below)
     - VMs managed externally without Python
   * - ``full`` (default)
     - Python environment (Miniforge3 + ``pyadare`` conda env)
     - Standard ADARE experiments
   * - ``agent``
     - Pre-installed ``adarevm`` guest agent (deferred)
     - Zero-overhead experiment runs

**Guest tools per platform:**

- **Linux** -- ``qemu-guest-agent``
- **Windows x86_64** -- ``virtio-win-guest-tools.exe`` (VirtIO drivers, QGA, SPICE) + firewall rule for port 18765
- **Windows ARM64 (UTM)** -- UTM guest tools + firewall rule for port 18765


Profile System
==============

ADARE ships with built-in profiles for Ubuntu 22.04, 24.04, 25.10, Windows 10,
Windows 11, and Windows 11 ARM64. You can add custom profiles for other
distributions.

Listing profiles
----------------

.. code-block:: bash

   adare manage os-profile list

Showing profile details
-----------------------

.. code-block:: bash

   adare manage os-profile show ubuntu2404

Adding a custom profile
-----------------------

Create a YAML file (e.g. ``my-distro.yml``):

.. code-block:: yaml

   name: my-distro
   display_name: My Distro 1.0
   platform: linux              # 'linux' or 'windows'
   distribution: ubuntu         # distribution family
   version: '1.0'
   architecture: x86_64         # 'x86_64' or 'aarch64'
   install_mode: auto           # 'auto' or 'manual'

   # Optional -- omit for manual installs or when using --iso
   iso_url: https://example.com/my-distro.iso
   iso_sha256: abcdef...
   iso_filename: my-distro.iso

   # Kernel paths inside ISO (required for automated Linux installs)
   kernel_path_in_iso: /casper/vmlinuz
   initrd_path_in_iso: /casper/initrd

   # Defaults
   default_disk_size: 60G
   default_ram_mb: 8192
   default_cpus: 4

   # UEFI / TPM
   requires_uefi: false
   requires_tpm: false

   # Custom Jinja2 template (see Custom Templates below)
   template: my_autoinstall.yaml

   # Extra apt packages to install
   extra_packages:
     - htop
     - vim

Then add it:

.. code-block:: bash

   adare manage os-profile add my-distro.yml

Removing a custom profile
--------------------------

.. code-block:: bash

   adare manage os-profile remove my-distro

YAML field reference
--------------------

.. list-table::
   :header-rows: 1
   :widths: 25 10 65

   * - Field
     - Required
     - Description
   * - ``name``
     - Yes
     - Unique identifier used on the command line
   * - ``platform``
     - Yes
     - ``linux`` or ``windows``
   * - ``distribution``
     - Yes
     - Distribution family (``ubuntu``, ``windows``, etc.)
   * - ``version``
     - Yes
     - Version string
   * - ``display_name``
     - No
     - Human-readable name (defaults to ``name``)
   * - ``architecture``
     - No
     - ``x86_64`` (default) or ``aarch64``
   * - ``install_mode``
     - No
     - ``auto`` (default) or ``manual``
   * - ``template``
     - No
     - Jinja2 template filename for unattended install (empty = default lookup)
   * - ``iso_url``
     - No
     - Direct download URL for the ISO
   * - ``iso_sha256``
     - No
     - Expected SHA-256 hash of the ISO
   * - ``iso_filename``
     - No
     - Cache filename for the downloaded ISO
   * - ``kernel_path_in_iso``
     - No
     - Path to vmlinuz inside ISO (Linux auto installs)
   * - ``initrd_path_in_iso``
     - No
     - Path to initrd inside ISO (Linux auto installs)
   * - ``default_disk_size``
     - No
     - Default disk size (e.g. ``60G``)
   * - ``default_ram_mb``
     - No
     - Default RAM in MB (default: 4096)
   * - ``default_cpus``
     - No
     - Default CPU count (0 = auto-detect)
   * - ``requires_uefi``
     - No
     - Whether the OS needs UEFI firmware
   * - ``requires_tpm``
     - No
     - Whether the OS needs a TPM device
   * - ``extra_packages``
     - No
     - List of additional packages to install


Custom Templates
================

ADARE uses Jinja2 templates for unattended installation configs:

- **Linux**: autoinstall YAML (Ubuntu cloud-init)
- **Windows**: Autounattend XML

Template search order
---------------------

1. User template directory: ``~/.adare/vm-templates/``
2. Built-in templates (shipped with ADARE)

A file in the user directory with the same name as a built-in template takes
precedence, allowing you to override defaults without modifying ADARE source.

Available template variables
----------------------------

**Linux (autoinstall YAML)**:

- ``hostname`` -- sanitized VM name (RFC 1123)
- ``password_hash`` -- SHA-512 crypt hash for the ``adare`` user
- ``miniforge_arch`` -- ``x86_64`` or ``aarch64`` (for Miniforge download URL)
- ``setup_level`` -- integer (0=bare, 1=base, 2=full); use ``{% if setup_level >= 1 %}`` conditionals

**Windows (Autounattend XML)**:

- ``setup_level`` -- integer (0=bare, 1=base, 2=full); use ``{% if setup_level >= 1 %}`` conditionals
- ``proc_arch`` -- ``amd64`` or ``arm64`` (for ``processorArchitecture`` attributes)
- ``driver_arch`` -- ``amd64`` or ``ARM64`` (for virtio-win driver paths)
- ``miniforge_arch`` -- ``x86_64`` or ``aarch64`` (for Miniforge download URL)

Template metadata
-----------------

Each Linux autoinstall template carries a self-describing metadata block as a
Jinja comment at the top of the file. The block declares which OS profiles the
template covers, so dropping a template into ``~/.adare/vm-templates/`` is
enough to register it -- no Python edits required.

.. code-block:: jinja

   {# adare-template
   schema: 1
   id: my-ubuntu
   description: Custom Ubuntu 24.04 with extra tooling
   maintainer: yourname
   revision: 2026-05-06
   supports:
     - ubuntu2404
     - ubuntu2404arm64
   #}
   #cloud-config
   autoinstall:
     ...

Field reference:

- ``schema`` (required, integer) -- Metadata schema version. Currently ``1``.
  Loading a template with an unknown schema raises an explicit error.
- ``id`` (required, string) -- Stable identifier surfaced in
  ``adare manage os-profile show``. Independent of filename.
- ``description`` (string) -- Human-readable summary.
- ``maintainer`` (string) -- Name or handle responsible for the template.
- ``revision`` (string) -- Free-form revision marker (date, version, etc.).
- ``supports`` (list of strings) -- OS profile names this template applies to.
  Order does not matter. Within a single template directory, two templates
  cannot claim the same OS name; across directories, user templates override
  built-ins.

Because the block is a Jinja ``{# ... #}`` comment, it is stripped at render
time and never reaches cloud-init. The line ``#cloud-config`` remains the first
line of the rendered output.

Writing a custom template
-------------------------

1. Copy an existing template from the built-in directory as a starting point:

   .. code-block:: bash

      cp $(python -c "import adare.hypervisor.qemu.vm_creator.autoinstall as a; print(a.TEMPLATES_DIR)")/autoinstall_ubuntu_lts.yaml \
         ~/.adare/vm-templates/my_autoinstall.yaml

2. Edit the template using the Jinja2 variables listed above.

3. Create a profile YAML with the ``template`` field pointing to your file:

   .. code-block:: yaml

      name: my-ubuntu
      platform: linux
      distribution: ubuntu
      version: '24.04'
      template: my_autoinstall.yaml
      kernel_path_in_iso: /casper/vmlinuz
      initrd_path_in_iso: /casper/initrd

4. Add the profile and create the VM:

   .. code-block:: bash

      adare manage os-profile add my-ubuntu.yml
      adare vm create my-ubuntu


Interactive Mode
================

The ``--interactive`` flag adds a second phase after automated installation:
the finished VM boots from its disk so you can install additional software or
configure settings that are not covered by the unattended template.

.. code-block:: bash

   adare vm create ubuntu2404 --interactive

**What happens:**

1. The automated install runs as usual (unattended, ISO + autoinstall).
2. After the install completes, QEMU boots the VM from the finished disk image.
3. A native display window opens (Cocoa on macOS, GTK on Linux).
4. You install software, tweak settings, etc.
5. When done, shut down from within the VM or press **Enter** in the terminal
   to send an ACPI shutdown.

**When to use it:**

- You need software that is not available via the unattended template
  (e.g. commercial tools, GUI applications requiring manual license activation)
- You want to verify the install before committing to experiment runs
- You need to configure settings that require a running desktop session

.. note::

   ``--interactive`` is ignored for ``install_mode: manual`` profiles since
   those already provide a full interactive QEMU session during install.


Legacy: Manual VirtualBox Setup
===============================

The following instructions apply to the older VirtualBox-based workflow.
For new VMs, the QEMU-based ``adare vm create`` command above is recommended.

General Guideline
-----------------

There are two options for creating your own ADARE-compatible VM:

1. **Start from scratch:** Create a new VM with a minimal OS installation.
2. **Modify an existing VM:** Take one of the provided ADARE VMs and customize it.

Once configured, export the VM as an ``.ova`` or ``.ovf`` file in **OVF 1.0 format**.

VirtualBox Configuration Requirements
--------------------------------------

- Disable all that can create popups (update notifications, automatic updates, error reporting, etc.)
- Disable screen lock and sleep mode

Windows Setup
-------------

User Account Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Create a user account with:

  - **Username:** ``adare``
  - **Password:** ``adare``

- Enable **autologin** so the VM boots directly into the ``adare`` user's desktop.

Additional Configuration
~~~~~~~~~~~~~~~~~~~~~~~~

1. **Disable User Account Control (UAC):**

   - Go to Control Panel > User Accounts > User Accounts > Change User Account Control settings
   - Set the slider to the bottom (Never notify)

2. **Enable Developer Mode:**

   - In Windows Settings, search for "For Developers"
   - Toggle the switch to enable Developer Mode

3. **Configure Windows Defender Firewall:**

   a. Press ``Win + R``, type ``wf.msc``, and press Enter
   b. In the left panel, right-click Windows Defender Firewall with Advanced Security > Properties
   c. For each profile tab (Domain, Private, Public), set Inbound connections to Allow
   d. Click Apply and OK

4. Perform a clean shutdown to apply all security changes.

Required Software:

- VirtualBox Guest Additions
- Python 3.9+ (added to PATH)
- uv (Python package manager)

Linux Setup
-----------

- Create user ``adare`` / ``adare`` with autologin (X11 session, not Wayland)
- Enable passwordless sudo: ``adare ALL=(ALL) NOPASSWD:ALL``
- Install Miniforge3, VirtualBox Guest Additions
- Disable auto-updates: ``sudo systemctl disable unattended-upgrades``

Installing ADARE Guest Agent
-----------------------------

The ADARE guest agent (``adarevm`` + ``adarelib``) is normally installed
automatically during experiment runs. Manual pre-installation saves 10-30
seconds per experiment. See the package wheels in the shared folder
(``/adare/app/wheels/`` on Linux, ``Z:\wheels`` on Windows with VirtualBox).


Registering as an Environment
==============================

After creating a VM, register it as an ADARE environment so experiments can
target it. Create an environment YAML file describing the VM:

.. code-block:: yaml
   :caption: my-win11-env.yml

   name: win11-custom
   vm: "~/.adare/state/vms/windows11-20260408.qcow2"
   os:
     os: "Windows"
     platform: "windows"
     distribution: "Pro"
     version: "11"
     architecture: "x64"

   description: "Windows 11 with Firefox 102 ESR for browser artifact research"
   tags: ["windows", "browser-forensics"]

For a Linux VM:

.. code-block:: yaml
   :caption: my-ubuntu-env.yml

   name: ubuntu2404-custom
   vm: "~/.adare/state/vms/ubuntu2404-20260408.qcow2"
   os:
     os: "Ubuntu"
     platform: "linux"
     distribution: "ubuntu"
     version: "24.04"
     architecture: "x64"

   description: "Ubuntu 24.04 minimal for filesystem artifact research"
   tags: ["linux", "filesystem"]

Load the environment into ADARE:

.. code-block:: bash

   adare environment load my-win11-env.yml

Verify it is available:

.. code-block:: bash

   adare environment list

The environment name (e.g., ``win11-custom``) can now be used in experiment
metadata and with the ``-e`` flag when running experiments:

.. code-block:: bash

   adare experiment run my-experiment -e win11-custom

.. tip::

   If you used the ``--env-name`` option during ``adare vm create``, an
   environment file was already generated automatically. Check with
   ``adare environment list`` before creating one manually.

See :doc:`/guide/environments` for full details on environment configuration.


See Also
========

- :doc:`/guide/environments` -- environment configuration and management
- :doc:`/getting-started/tutorial` -- basic ADARE workflow tutorial
