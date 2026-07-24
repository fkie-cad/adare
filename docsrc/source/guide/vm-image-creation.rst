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

The VM boots the live ISO in a window and waits for you to click through the
graphical installer. (Manual mode drives QEMU directly and writes no seed file.)


GUI-automated installation (record once, replay deterministically)
------------------------------------------------------------------

Some distributions ship the **Calamares** GUI installer — most notably
**Kubuntu 24.04+**, plus Mint, Pop!_OS and elementary — which has *no*
answer-file mechanism (no Subiquity/preseed/kickstart/AutoYaST). Instead of
clicking through it by hand, ``install_mode: gui-auto`` drives the installer's
screen directly:

.. code-block:: bash

   adare vm create kubuntu2404 --iso kubuntu-24.04-desktop-amd64.iso

**How it works — record once, then replay.**

- **First run (record, needs a vLLM endpoint).** A vision-LLM agent runs a
  ``perceive → decide → act`` loop: it screenshots the installer, the model
  decides the next action (click / type / key / scroll / wait / done), and the
  action is executed over QEMU's host-side QMP engine (no guest agent). As it
  acts it **records a reusable ADARE playbook** — per click it saves an image
  crop (an ``image:`` target the CV engine can re-find) plus the model's
  natural-language description. Output: the installed ``qcow2``, a baked
  environment YAML, the generated ``gui_<distro>.play.yaml`` (+ crop images),
  and a screenshot-illustrated ``install_report.md``.
- **Later runs (replay, no LLM).** The generated playbook replays through
  ADARE's ordinary CV/OCR engine (:class:`ActionExecutor` +
  ``MCPTargetResolver``) — deterministic and LLM-free. If a step's target no
  longer matches (e.g. a new point release moved a button), replay falls back
  to the vision model to re-locate it, clicks it, and re-crops the target so
  the playbook stays current (**self-heal**).

The generated ``.play.yaml`` is a first-class ADARE playbook: hand-editable,
shareable, and usable in experiments. A validated playbook can be shipped in
the package templates so most users never trigger a record run.

**When to use which route.** Prefer ``gui-auto`` when you want a *faithful*
native Calamares install automated end-to-end. Alternatives: build an Ubuntu
Server autoinstall + ``kubuntu-desktop`` (robust, but not a native Calamares
install), or install once by hand and capture a disk image (faithful, but
semi-manual and needs BYO hosting).

**vLLM setup (record / self-heal only).** Serve a *grounding-capable* vision
model (Qwen2-VL / UI-TARS / Molmo-class) over an OpenAI-compatible endpoint and
point ADARE at it:

.. code-block:: bash

   export ADARE_VLLM_BASE_URL=http://localhost:8000/v1
   export ADARE_VLLM_MODEL=Qwen/Qwen2-VL-7B-Instruct
   # If your model returns 0..1000 normalized coordinates instead of pixels:
   export ADARE_VLLM_COORD_SPACE=normalized_1000

Pure replay needs **no** endpoint. Budgets bound the record run
(``ADARE_GUI_AGENT_MAX_STEPS``, ``ADARE_GUI_AGENT_STALL_LIMIT``,
``ADARE_GUI_AGENT_WALL_CLOCK_SECONDS``).

**Using Ollama Cloud.** The client is a plain OpenAI-compatible caller, so an
Ollama Cloud model works with no code change — point it at the cloud endpoint
and use a grounding model:

.. code-block:: bash

   export ADARE_VLLM_BASE_URL=https://ollama.com/v1
   export ADARE_VLLM_API_KEY=<key from ollama.com/settings/keys>
   export ADARE_VLLM_MODEL=gemma4:31b
   export ADARE_VLLM_COORD_SPACE=normalized_1000   # coord convention varies by model

Ollama Cloud retired the ``qwen3-vl`` GUI/computer-use line in 2026-06;
``gemma4:31b`` is the current cloud vision model. It is a *general* multimodal
model (not coordinate-tuned), so keep ``--ground`` on — LocateAnything localizes
each click from the model's textual target description. Verify everything up
front with the preflight, which pings the endpoint and auto-detects the
coordinate convention:

.. code-block:: bash

   adare vm gui-doctor

**Driving an existing environment / authoring experiments.** The same agent can
drive an *already-installed* environment to author reusable automation. Bring the
environment up once, then hand the agent a goal (add ``--out`` to record a
playbook):

.. code-block:: bash

   adare dev start -e <environment>          # boots the VM + CV server, keeps them alive
   adare dev agent --goal "open the Files app and navigate to Documents" \
       --out experiments/files.play.yaml     # drives the VM; records a playbook

The recorded ``.play.yaml`` is an ordinary ADARE playbook. Replay it
deterministically (no LLM) via ``adare dev playbook <session> -f files.play.yaml``
or the normal engine with ``adare experiment run <exp> -e <env> --gui-mode host``.
A raw drive (no ``--out``) needs only the VLM; recording a playbook whose steps
use image/text targets also relies on the CV server (already up in a dev session).

**Optional: precise icon grounding (LocateAnything).** By default each recorded
click stores a fixed ~220×90 crop around the model's click point. If you run the
standalone LocateAnything grounding sidecar and point the agent at it, each click
is grounded to the element's true bounding box and the recorded image target is
the tight icon crop instead — better centred on the element (the recorded
playbook still replays deterministically via the CV matcher, no model needed):

.. code-block:: bash

   # sidecar wraps the locate-anything-cli binary; no VLM deps enter the adare package
   LA_CLI_BIN=/path/to/locate-anything-cli LA_MODEL=/path/to/model.gguf \
       python3 scripts/locate_anything_sidecar.py --port 13111
   export ADARE_LOCATE_URL=http://127.0.0.1:13111   # enables grounding for `dev agent`

A tight crop is more precise but less distinctive to the CV matcher: a small,
generic glyph (e.g. a bare document icon) can collide with near-duplicate UI
(a full trash bin). Grounding is best-effort — a miss falls back to the fixed
crop, so a run never breaks when the sidecar is down.

**Goal / acceptance spec.** The record-run *input* is a high-level goal, not a
per-screen script, in ``gui_<distro>.yaml`` (bundled, or overridden in
``~/.adare/vm-templates/``):

.. code-block:: yaml

   goal: >
     Install Kubuntu to the whole disk (erase it). Create user adare /
     password adare. Accept sensible defaults and reboot when finished.
   hints:
     - "Choose 'Erase disk' — not 'Install alongside'."
   acceptance:
     min_disk_bytes: 5000000000
     visual:
       - "a Kubuntu/KDE SDDM login or desktop for user adare is shown"

The ``acceptance`` block is the single place "what success looks like" lives:
after the installed disk reboots, ADARE runs **acceptance checks** (a visual
check via the model plus structural checks — domain running, disk grew) and
fails the build (non-zero exit) if they do not pass.

**Limitations & safety.** The record run is non-deterministic and needs a
capable grounding model; step / stall / wall-clock budgets bound it. Disk
partitioning during install is destructive but sandboxed — the blast radius is
only the throwaway VM disk. Replay is deterministic; self-heal recovers from
minor drift but a heavily redesigned installer may need ``--relearn``.


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
     - Setup level: ``bare`` (OS only), ``base`` (+ guest tools), ``full`` (+ Python, default), ``agent`` (not implemented -- rejected)
   * - ``--bare``
     - Deprecated alias for ``--setup bare``
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
   * - ``--recipe`` / ``--no-recipe``
     - Emit a declarative *recipe* environment (built on load) instead of a baked disk. Default: recipe for Windows, baked for Linux. See :ref:`recipe-environments`.
   * - ``--record``
     - GUI-auto only: record a fresh playbook with the vision agent even if a cached one exists.
   * - ``--relearn``
     - GUI-auto only: discard the cached playbook and re-record from scratch.
   * - ``--display``
     - GUI-auto only: show the VM window while the agent drives the installer (and leave it up on failure for inspection).
   * - ``--template NAME``
     - GUI-auto only: explicit goal/spec template name (default: ``gui_<distribution>``).


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
     - **Not implemented** -- the CLI rejects ``--setup agent``
     - Documented placeholder only

**What ``full`` actually bakes:**

- **Linux and Windows x86_64** -- Miniforge3 plus a ``pyadare`` conda environment
- **Windows ARM64** -- plain CPython 3.11 (no conda; there is no Miniforge build for
  Windows on ARM64), which is by design
- **``gui-auto`` and ``manual`` installs** -- no Python environment at all; the level
  therefore has little effect for those profiles

**Guest tools per platform:**

- **Linux** -- ``qemu-guest-agent``
- **Windows x86_64** -- ``virtio-win-guest-tools.exe`` (VirtIO drivers, QGA, SPICE) + firewall rule for port 18765
- **Windows ARM64 (UTM)** -- UTM guest tools + firewall rule for port 18765

**Conda vs. system Python is never a create-time choice.** The guest's Python stack is
auto-detected at run time (a baked conda env is used if present, otherwise the system
interpreter, with a create-the-env recovery path). Likewise the ``adarevm``/``adarelib``
wheels are *not* installed during ``vm create`` -- they install themselves on the first
experiment or dev-session start.


.. _recipe-environments:

Recipe Environments
===================

An ADARE environment can be defined in one of two ways:

- **Baked disk** (Linux default) -- ``adare vm create`` builds a ``qcow2`` disk
  now and the environment references that frozen artifact. Integrity is anchored
  on the disk's SHA256 (``Vm.hash``). This is the historical model and is
  unchanged.
- **Recipe** (Windows default) -- the environment is defined *declaratively* by
  its build inputs: an OS profile, a user-supplied ISO plus its expected
  ``iso_sha256``, an optional unattended-install template, and build params. The
  disk is built **on load** and cached. Integrity is anchored on the *inputs*
  ("same inputs -> forensically equivalent system"), because OS installs are
  never bit-reproducible.

Why recipes for Windows
-----------------------

Windows evaluation editions and activation expire. A baked Windows disk cannot
be refreshed without becoming a different artifact. With a recipe you simply
drop in a fresh ISO and rebuild -- the environment definition (profile + params)
is unchanged, only the ISO and its ``iso_sha256`` move forward. Because the ISO
is part of the integrity identity, a new ISO is always a **new environment**,
never a silent in-place refresh, so historical results stay reproducible.

Recipe environment file
-----------------------

``adare vm create windows11 --iso /path/to/Win11.iso`` emits a recipe
environment instead of building immediately:

.. code-block:: yaml

   vm_type: recipe
   hypervisor: qemu
   recipe:
     profile: windows11          # resolves via the OS profile catalog
     iso: /path/to/Win11.iso     # user-supplied installer ISO
     iso_sha256: "abc123..."     # expected SHA256 of the ISO (hard-checked)
     params:
       setup_level: 2            # 0=bare, 1=base, 2=full
       disk_size: 80G
       ram_mb: 16384
   # Post-install steps reuse the existing environment field; they are folded
   # into the recipe integrity hash and applied at experiment time as usual:
   # postsetupinstallations:
   #   - {name: my-tool, command: "...", description: "..."}

Build lifecycle
---------------

On ``adare environment load`` the recipe flow:

1. Verifies the ISO exists and ``hash(iso) == iso_sha256`` -- **hard-fails** on
   mismatch.
2. Computes the *recipe hash* from ``iso_sha256`` + the install template + the
   params/profile/post-install identity.
3. If a VM with that recipe hash already exists (and its cached disk is
   present), reuses it -- **no rebuild** (build once, cache).
4. Otherwise builds the disk with the normal creator machinery and registers it
   with ``build_source='recipe'`` plus the recipe hash, ISO hash, and profile
   name for provenance.

Because the built disk is still hashed into ``Vm.hash``, it remains
tamper-checked exactly like a baked disk. A recipe environment gains one
recovery advantage a baked disk lacks: if the cached disk goes missing, integrity
verification rebuilds it from the recipe instead of hard-failing.

Choosing the mode
-----------------

Use ``--recipe`` / ``--no-recipe`` to override the platform default:

.. code-block:: bash

   # Linux, opt into a recipe environment (needs an ISO)
   adare vm create ubuntu2404 --iso /path/to/ubuntu.iso --recipe

   # Windows, force a baked disk instead of a recipe
   adare vm create windows11 --iso /path/to/Win11.iso --no-recipe


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
   install_mode: auto           # 'auto', 'manual', or 'gui-auto'

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
     - ``auto`` (default), ``manual``, or ``gui-auto`` (vision-LLM-driven GUI automation)
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
