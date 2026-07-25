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

The stem is derived from the profile name with trailing digits stripped
(``kubuntu2404`` → ``kubuntu``), so **all** versions of a distribution share one
goal file *and one cached* ``gui_<stem>.play.yaml`` by default. When two versions
ship different installers — Kubuntu 20.04/22.04 run ubiquity, 24.04 runs
Calamares — pin the version by setting ``template:`` to the bare stem in the
profile (the loader prepends ``gui_``), as ``kubuntu2404.yml`` does with
``template: kubuntu2404`` → ``gui_kubuntu2404.yaml`` +
``gui_kubuntu2404.play.yaml``. Without it, a Calamares recording would be
replayed against ubiquity.

The ``acceptance`` block is the single place "what success looks like" lives:
after the installed disk reboots, ADARE runs **acceptance checks** (a visual
check via the model plus structural checks — domain running, disk grew) and
fails the build (non-zero exit) if they do not pass.

**Limitations & safety.** The record run is non-deterministic and needs a
capable grounding model; step / stall / wall-clock budgets bound it. Disk
partitioning during install is destructive but sandboxed — the blast radius is
only the throwaway VM disk. Replay is deterministic; self-heal recovers from
minor drift but a heavily redesigned installer may need ``--relearn``.


Scripted GUI installation (``gui-script``) — deterministic, no model
--------------------------------------------------------------------

``install_mode: gui-script`` replays a hand-calibrated QMP playbook against the
installer's GUI. It is the *no-model* sibling of ``gui-auto``: **no vision model,
no CV server, no** ``ADARE_VLLM_*`` **configuration**, and the same playbook
produces the same disk on any host with QEMU.

.. code-block:: bash

   adare vm create ubuntu1804      # ISO auto-downloads (iso_url is baked in)
   adare vm create ubuntu2004

.. list-table:: ``gui-auto`` vs ``gui-script``
   :header-rows: 1
   :widths: 22 39 39

   * -
     - ``gui-auto``
     - ``gui-script``
   * - Targets a screen by
     - image/text matching (CV), model on miss
     - fixed pixel coordinates
   * - Needs a vision model
     - yes to record or self-heal
     - never
   * - Needs the CV server
     - yes
     - no
   * - Waits by
     - CV target appearing
     - ``wait_stable`` frame diffing
   * - Recovers from UI drift
     - yes (self-heal, re-crop)
     - no — coords must be recalibrated
   * - Use it to
     - **record** a route for a new release
     - **replay** a route that is already proven

**How the waiting works.** The primitive that makes replay robust is
``wait_stable`` (:mod:`adare.hypervisor.qemu.vm_creator.qmp_replay`): successive
``screendump`` frames are diffed *as raw bytes* until the screen stops changing
for a settle period. There is no template matching, no OCR and no model, so a
step never waits on a fixed sleep that is too short on a slow host or wastefully
long on a fast one. During the copy phase the progress bar keeps the frame
changing, so the wait only returns once the installer is genuinely idle on its
"Installation Complete" dialog. A ``min:`` floor skips the static early-boot
plymouth screens, which are otherwise perfectly stable before any UI exists.

**Two constraints, both learned by breaking them.** The creator asserts the
first and the playbooks depend on the second:

- **``-vga qxl``, never ``-vga std``.** The std adapter's tablet applies a 2x
  coordinate scaling, so absolute clicks land at double the intended offset and
  the right half of the screen is simply unreachable.
- **Click buttons with ``tap``, not the keyboard.** ubiquity does not reliably
  hold keyboard focus at live-session start, and its timezone screen traps focus
  in the city-entry field. A mouse click both focuses the window and activates
  the button.

**Playbooks.** They live beside the other templates as
``qmpinstall_<stem>.yaml`` (override in ``~/.adare/vm-templates/``) and are
resolved by the same stem lookup ``gui-auto`` uses, so ``template: ubuntu1804``
keeps per-version isolation — 18.04's and 20.04's ubiquity differ visually and
must not share a recording. Steps are ``key`` / ``type`` / ``tap`` / ``wait`` /
``wait_stable`` / ``shot``:

.. code-block:: yaml

   vm:
     ram_mb: 4096
     cpus: 4
     disk_size: "60G"
     vga: qxl
     firmware: bios
     frame:            # the frame the tap coords were calibrated at
       width: 1024
       height: 768

   install:
     - {action: wait_stable, settle: 6, timeout: 360, min: 120, shot: welcome}
     - {action: tap, coords: [763, 434, 1024, 768], note: "click 'Install Ubuntu'"}
     - {action: type, text: "adare"}
     - {action: key, keys: [tab], repeat: 2}

   reboot_from_disk: true

   verify:
     - {action: wait_stable, settle: 8, timeout: 240, min: 45, shot: login}

Every ``tap`` carries the frame its coordinates belong to, and the creator
**rejects** a playbook whose coords disagree with the declared ``frame`` or fall
outside it. A coordinate recorded at another resolution otherwise mis-clicks
silently, which is far more expensive to diagnose after a 40-minute install. A
screenshot is written per step (``<vm>_gui-script/``) and stays on by default —
it is the only useful debugging aid when a click lands wrong.

**Calibrating a new playbook.** ``scripts/gui-install/`` is the authoring tool
and shares this playbook format. Boot the installer with ``--keep-running`` and
poke at it interactively to read coordinates off the screen:

.. code-block:: bash

   cd scripts/gui-install
   ./gui_install.py playbooks/ubuntu2004-desktop.yaml \
       --iso ubuntu-20.04.6-desktop-amd64.iso --vm-dir /vms --keep-running
   ./qmp_drive.py --sock /tmp/gui-install/qmp.sock shot /tmp/now.png
   ./qmp_drive.py --sock /tmp/gui-install/qmp.sock tap 924 566 1024 768

Once the coordinates are proven, copy the playbook to
``adare/adare/hypervisor/qemu/vm_creator/templates/qmpinstall_<stem>.yaml`` and
flip the profile to ``install_mode: gui-script``.

**Limitations.** Coordinate-fragile by construction: a different guest
resolution silently mis-clicks, and a redesigned installer needs recalibration
(there is no self-heal). Use ``gui-auto`` to record a route for a release nobody
has coordinates for, and ``gui-script`` to replay one that is proven.

.. warning::

   The 18.04 / 20.04 playbooks are **x86_64 desktop** installs and have not been
   replayed by us on this Apple Silicon host — x86_64 guests cannot be built
   there (no TCG fallback). See :ref:`replicating-on-x86-64`.


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

ADARE ships profiles for Ubuntu 20.04–26.04, Kubuntu 20.04–24.04 (both
architectures), Debian, Kali, Fedora, RHEL rebuilds, openSUSE, Windows 10,
Windows 11 and Windows 11 ARM64. You can add custom profiles for other
distributions.

Listing profiles
----------------

.. code-block:: bash

   adare os-profile list

Showing profile details
-----------------------

.. code-block:: bash

   adare os-profile show ubuntu2404

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
   install_mode: auto           # 'auto', 'manual', 'gui-auto', or 'gui-script'

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

   adare os-profile add my-distro.yml

Removing a custom profile
--------------------------

.. code-block:: bash

   adare os-profile remove my-distro

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
     - ``auto`` (default, unattended answer file), ``manual`` (a human clicks
       through a QEMU window), ``gui-auto`` (a vision-LLM drives the GUI
       installer and records a playbook), or ``gui-script`` (deterministic QMP
       playbook replay -- no model, no CV server)
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
   * - ``installer``
     - No
     - Installer family, i.e. how the rendered answer file reaches the installer:
       ``subiquity`` (default), ``preseed``, ``ubiquity``, ``kickstart``,
       ``autoyast``, ``archinstall-cloudinit``, ``manual``, ``gui``. See
       *Installer families* below.
   * - ``kernel_cmdline``
     - No
     - Kernel command line passed to QEMU's ``-append`` on the direct kernel boot.
       Default ``autoinstall console={console} ---``. ``{console}`` expands to
       ``ttyAMA0`` on aarch64 / ``ttyS0`` on x86_64. With
       ``seed_transport: http`` ADARE additionally splices a ``url=`` fetch hint
       in before the ``---`` separator; the profile does not write it itself.
   * - ``seed_label``
     - No
     - Volume label of the seed ISO attached as the second drive; the installer
       auto-detects the answer file by it. ``cidata`` (default) for cloud-init /
       Subiquity, ``OEMDRV`` for debian-installer and Anaconda. Ignored by
       ``ubiquity`` (which reads no label) and by ``gui`` / ``manual``.
   * - ``seed_transport``
     - No
     - How the answer file reaches the guest. ``cdrom`` (default) attaches the
       rendered seed as the labelled second drive and lets the installer
       auto-detect it. ``http`` *additionally* serves the seed directory from the
       host on an ephemeral port for the duration of the install
       (:mod:`adare.hypervisor.qemu.vm_creator.seed_http`) and splices
       ``url=http://10.0.2.2:<port>/<answer-file>`` into ``kernel_cmdline``.
       Needed for installers with no labelled-drive auto-detect: ``ubiquity``,
       and older debian-installer releases such as Ubuntu 18.04's.

Installer families
------------------

.. list-table::
   :header-rows: 1
   :widths: 22 20 58

   * - ``installer``
     - Rendered file
     - How the installer finds it
   * - ``subiquity``
     - ``user-data`` (+ empty ``meta-data``)
     - cloud-init NoCloud auto-detects the ``cidata``-labelled seed drive;
       ``autoinstall`` on the cmdline enables it. Ubuntu **live-server** ISOs.
   * - ``archinstall-cloudinit``
     - ``user-data`` (+ empty ``meta-data``)
     - Same NoCloud mechanism.
   * - ``preseed``
     - ``preseed.cfg``
     - debian-installer auto-loads ``/preseed.cfg`` from any ``OEMDRV``-labelled
       drive. Debian / Kali **netinst** ISOs.
   * - ``ubiquity``
     - ``preseed.cfg``
     - Ubuntu / Kubuntu **desktop** ISOs. ubiquity has *no* labelled-drive
       auto-detect: casper's network-preseed script fetches the file from the
       ``url=`` on the cmdline. ADARE serves the seed directory over HTTP on an
       ephemeral host port for the duration of the install
       (:mod:`adare.hypervisor.qemu.vm_creator.seed_http`); under QEMU user-mode
       networking the guest reaches the host at ``10.0.2.2``. Declare it with
       ``seed_transport: http`` and ADARE adds the ``url=`` itself::

         installer: ubiquity
         seed_transport: http
         kernel_cmdline: >-
           automatic-ubiquity noprompt boot=casper console={console} ---

       The labelled seed drive is still attached, because that is the
       configuration the 18.04 install was validated against. It means the guest
       has a second block device, so pin ``partman-auto/disk string /dev/vda`` in
       the preseed rather than relying on there being only one disk.
   * - ``kickstart``
     - ``ks.cfg``
     - Anaconda reads it from the ``OEMDRV`` drive when given
       ``inst.ks=hd:LABEL=OEMDRV:/ks.cfg``. Fedora / RHEL-family netinst + DVD.
   * - ``autoyast``
     - ``autoinst.xml``
     - AutoYaST auto-loads it from ``OEMDRV`` with ``autoyast=default``.
   * - ``gui`` / ``manual``
     - (none)
     - No answer file is written; the installer is driven by the vision agent
       (``gui-auto``) or by a human (``manual``).

Desktop guests on aarch64
-------------------------

Desktop ISO availability on arm64 is uneven, and it is what bounds the options:

- **Ubuntu** publishes an arm64 desktop ISO from **24.04.3 onwards**
  (``ubuntu-24.04.4-desktop-arm64.iso``). Earlier LTS releases (22.04, 20.04) do
  not — those trees carry only server, ppc64el and s390x images.
- **Kubuntu** publishes ``desktop-amd64`` **exclusively**, for every release.
  There is no arm64 Kubuntu desktop ISO to install.
- **Fedora** published no aarch64 Workstation *Live* image before release 42.

The rule ADARE follows:

- **x86_64** — install the real desktop ISO where one exists (Ubuntu Desktop,
  Kubuntu) through the ``ubiquity`` family, or Calamares through ``gui-auto``
  for Kubuntu 24.04+.
- **aarch64** — install the **live-server ISO** of the matching version through
  ``subiquity`` and pull in the desktop metapackage
  (``ubuntu-desktop-minimal`` / ``kubuntu-desktop``). This is the route that
  produced the existing 24.04 ARM64 environments, and the only route available
  for Kubuntu and for Ubuntu 22.04 / 20.04 on arm64.

The two are *not* byte-identical installs, so the divergence is stated in the
profile's ``display_name`` — e.g. "Kubuntu 22.04 (KDE Plasma on Ubuntu 22.04
Server base, ARM64)" — and therefore in the environment metadata of every
experiment run against it.

.. warning::

   The **x86_64** profiles ``ubuntu2004``, ``kubuntu2004`` and ``kubuntu2204``
   ship **untested**. They cannot be built on an Apple Silicon host: the guest
   architecture is guarded for non-aarch64 guests and QEMU is invoked as
   ``qemu-system-<host arch>`` with ``accel=hvf``, and ADARE deliberately has no
   TCG fallback. A green ``adare os-profile list`` row is *not* a verification —
   treat these as recipes for replication on Intel/AMD hosts.

Paper-replication profiles
--------------------------

The profiles behind the case studies, and the ISO each one expects:

.. list-table::
   :header-rows: 1
   :widths: 26 12 62

   * - Profile
     - Installer
     - ISO to pass with ``--iso``
   * - ``ubuntu2004arm64``
     - subiquity
     - ``ubuntu-20.04.5-live-server-arm64.iso``
   * - ``ubuntu2204arm64``
     - subiquity
     - ``ubuntu-22.04.5-live-server-arm64.iso``
   * - ``ubuntu2404arm64``
     - subiquity
     - ``ubuntu-24.04.x-live-server-arm64.iso`` (a genuine
       ``ubuntu-24.04.4-desktop-arm64.iso`` also exists — 24.04 is the only
       release on this list for which an arm64 *desktop* ISO is published)
   * - ``kubuntu2004arm64``
     - subiquity
     - ``ubuntu-20.04.5-live-server-arm64.iso`` (+ ``kubuntu-desktop``)
   * - ``kubuntu2204arm64``
     - subiquity
     - ``ubuntu-22.04.5-live-server-arm64.iso`` (+ ``kubuntu-desktop``)
   * - ``kubuntu2404arm64``
     - subiquity
     - ``ubuntu-24.04.x-live-server-arm64.iso`` (+ ``kubuntu-desktop``)
   * - ``fedora41arm64``
     - kickstart
     - ``Fedora-Everything-netinst-aarch64-41-1.4.iso``
   * - ``fedora42arm64``
     - kickstart
     - ``Fedora-Everything-netinst-aarch64-42-1.1.iso``
   * - ``ubuntu1804`` (x86_64)
     - gui-script
     - auto-downloads ``ubuntu-18.04.5-desktop-amd64.iso``
   * - ``ubuntu2004`` (x86_64)
     - gui-script
     - auto-downloads ``ubuntu-20.04.6-desktop-amd64.iso``
   * - ``kubuntu2004`` / ``kubuntu2204`` (x86_64)
     - ubiquity
     - auto-downloads ``kubuntu-20.04.6`` / ``22.04.5-desktop-amd64.iso``
   * - ``kubuntu2404`` (x86_64)
     - gui (Calamares)
     - ``kubuntu-24.04.x-desktop-amd64.iso``
   * - ``fedora41`` / ``fedora42`` (x86_64)
     - kickstart
     - auto-downloads ``Fedora-Everything-netinst-x86_64-4{1,2}-1.x.iso``

Both Fedora profiles install from **Everything-netinst** rather than the
Workstation Live ISO: Fedora 41 has no aarch64 live image at all, so netinst is
the only route that keeps 41 and 42 method-identical, and directly kernel-booting
live media would additionally need a per-release ``root=live:CDLABEL=...``. Both
releases are EOL, so their metalink no longer resolves to a mirror — the profiles
pin ``inst.repo`` at ``dl.fedoraproject.org/pub/archive/...``, which also serves
stage2. The shared kickstart template's ``%post`` repoints dnf at the same
archive if the installed system's metalink fails, then installs the ADARE extras
— which also covers live media, where Anaconda ignores ``%packages`` entirely.

.. note::

   **Ubuntu 20.04 (focal) needs two extra autoinstall keys**, both in
   ``autoinstall_ubuntu_focal.yaml`` / ``autoinstall_kubuntu_focal.yaml``:

   - **No ``packages:`` block.** Focal's curtin leaves ``devpts`` unmounted inside
     ``/target``, so apt's pty logging fails with *"Can not write log (Is /dev/pts
     mounted?) - posix_openpt (19: No such device)"* and subiquity's in-target
     package step exits 100 — after which subiquity drops to a rescue shell and the
     unattended install hangs until ADARE's timeout. Setting ``apt: conf:
     'Dpkg::Use-Pty "false";'`` does **not** help: curtin writes that to
     ``/etc/apt/apt.conf.d/94curtin-config`` and deletes it again before the package
     step runs. Focal therefore installs everything from ``late-commands`` with
     ``apt-get install -y -o Dpkg::Use-Pty=false``, the one place the setting
     survives. Jammy and noble ship a curtin that mounts devpts, so they keep using
     ``packages:``.
   - ``shutdown: poweroff`` works on focal — a 20.04.**5** ISO carries subiquity
     snap rev 3704 (2022-era), not the 2020 original, because point releases refresh
     the installer. ``sizing-policy: all`` is accepted but *ignored* by it: the root
     LV still lands at half the PV (measured 28.5 GiB of 57 GiB on a 60 GB disk),
     which is ample for a desktop guest.

   Every new template also declares ``error-commands`` that dump the curtin/apt
   logs to ``/dev/console`` (captured into ``<vm>_install.log``). Without it a
   failed in-target package install reaches the host as nothing more than
   ``returned non-zero exit status 100``. Those commands deliberately do **not**
   power the guest off: ADARE infers install success from QEMU exiting, so a
   poweroff-on-error would present a half-installed disk as a finished build.
   A ``<disk>_install.log`` scan for installer failure markers runs after every
   Linux build for the same reason — QEMU exits ``0`` on SIGTERM and on a closed
   QEMU window too.

.. warning::

   **Fedora guests run with SELinux in permissive mode.** ADARE drives Linux
   guests through the QEMU guest agent, and Fedora confines that agent to the
   ``virt_qemu_ga_t`` domain — confined so tightly that it cannot stat
   ``/usr/bin/sudo``. Probing a stock enforcing install through the agent gives
   ``ls -l /usr/bin/sudo`` → *Permission denied*, ``command -v sudo`` → not found,
   ``systemctl`` → *Access denied*, so every ADARE setup step fails even though
   every package is installed. ``kickstart_fedora_workstation.yaml`` therefore
   sets ``selinux --permissive``.

   Permissive, not disabled: files are still labelled and AVCs are still audited,
   so SELinux contexts and audit entries keep showing up in forensic diffs — only
   the denials stop. It remains a deviation from a stock Fedora install and should
   be stated wherever these environments are reported. Debian/Ubuntu guests are
   unaffected (no SELinux confinement of the agent). The same one-line fix applies
   to ``kickstart_fedora_kde.yaml`` and ``kickstart_rhel_workstation.yaml``, which
   have not been changed.

**Install timeout.** One unattended install is allowed
``ADARE_VM_INSTALL_TIMEOUT_MINUTES`` minutes (default **150**) before it is
treated as hung and the half-written disk is discarded. It is a hang detector,
not a budget — a healthy install that runs long must not be killed. Measured on
an M-series host: an Ubuntu live-server autoinstall lands well inside an hour,
while a Fedora Workstation netinst needs longer (≈1900 RPMs fetched from the
archive, then their scriptlets, before ``%post`` even starts) and a
``kubuntu-desktop`` build pulls the whole Plasma set over the network. Raise it
for a slow link:

.. code-block:: bash

   ADARE_VM_INSTALL_TIMEOUT_MINUTES=240 adare vm create fedora42arm64 --iso ...

Register an environment under a name of your choosing with ``--env-name``, which
is how the paper's hyphenated environment names are produced:

.. code-block:: bash

   adare vm create fedora42arm64 \
       --iso ~/.adare/isos/Fedora-Everything-netinst-aarch64-42-1.1.iso \
       --env-name fedora-42


.. _replicating-on-x86-64:

Replicating on x86_64
---------------------

.. important::

   **The aarch64 disks are not portable to x86_64.** A qcow2 built by the
   ``*arm64`` profiles contains an ARM64 kernel and userland; there is no
   conversion. Replicating on an x86 host means *rebuilding* from the x86
   profiles, which produces a different (though method-identical) artefact.

**Host requirements.** Linux with **KVM**. ADARE selects the accelerator by host
OS: ``hvf`` on Darwin, otherwise ``kvm``
(:mod:`adare.hypervisor.qemu.vm_creator.qmp_utils`, ``config/__init__.py``).
**Windows hosts are not covered** — WHPX is never selected, so a Windows host
falls through to ``kvm`` and QEMU fails to start. Use Linux, or WSL2 with nested
virtualisation.

Each x86 profile bakes its ``iso_url`` + ``iso_sha256``, so no ``--iso`` is
needed: the ISO is downloaded into the cache and hash-checked, and a mismatch
re-downloads rather than installing a wrong image. One command per environment:

.. code-block:: bash

   # Ubuntu desktop, deterministic GUI replay (no vision model)
   adare vm create ubuntu1804 --env-name ubuntu-1804
   adare vm create ubuntu2004 --env-name ubuntu-2004

   # Kubuntu desktop via ubiquity + an HTTP-served preseed
   adare vm create kubuntu2004 --env-name kubuntu-2004
   adare vm create kubuntu2204 --env-name kubuntu-2204

   # Kubuntu 24.04 runs Calamares -> needs the vision agent (see gui-auto)
   adare vm create kubuntu2404 --iso kubuntu-24.04.3-desktop-amd64.iso \
       --env-name kubuntu-2404

   # Fedora, Everything-netinst pinned to the archive mirror
   adare vm create fedora41 --env-name fedora-41
   adare vm create fedora42 --env-name fedora-42

   # Ubuntu server-based x86 profiles (same method as the arm64 ones)
   adare vm create ubuntu2204 --env-name ubuntu-2204
   adare vm create ubuntu2404 --env-name ubuntu-2404

Then load and verify each one, **sequentially** — a concurrent build starves the
booting guest badly enough to time out the guest agent:

.. code-block:: bash

   adare env load ~/.adare/state/environments/<name>_*.yml -f
   adare env verify <name>          # installs the agent and performs a GUI click

.. warning::

   **The x86 profiles are unverified by us.** This work was done on an Apple
   Silicon host, which cannot build x86_64 guests at all (no TCG fallback), so
   every x86 profile above is shipped on the strength of its template and — for
   ``ubuntu1804`` / ``ubuntu2004`` — a playbook validated on someone else's x86
   host. Treat the first run on x86 as a bring-up, not a regression test.

   Vendor URLs for EOL images also rot: focal has already moved to
   ``old-releases``, and Kubuntu 20.04.5 has already been pruned (only ``.6``
   remains). The baked SHA-256 turns that rot into a loud failure rather than a
   silently wrong image, but a 404 still needs the URL refreshed.

The two warnings above apply to x86 exactly as they do to aarch64: **Fedora
guests run with SELinux permissive**, and **Ubuntu 20.04 (focal) needs the
``-o Dpkg::Use-Pty=false`` workaround** for its unmounted ``/dev/pts``.

.. note::

   **Images built before the interface-matching fix boot slowly and need the
   run-time network repair.** Ubuntu/Kubuntu images whose autoinstall baked a
   *named* interface (``enp0s1``) into netplan cannot configure their NIC at run
   time, because ADARE gives it a different PCI address (``enp0s31``). Symptoms,
   as measured on the eight paper-replication environments:

   - every boot pays the full **120 s** ``systemd-networkd-wait-online`` timeout,
     so ``VM is ready`` lands at 127-164 s instead of ~16 s;
   - Kubuntu / Ubuntu 22.04 / 20.04 end up with no address at all, the
     ``//10.0.2.4/qemu`` mount fails, and file transfer degrades to QGA;
   - Ubuntu 24.04 is rescued by NetworkManager one second after the timeout, so it
     passes but still pays the 120 s;
   - Fedora is unaffected (NetworkManager manages any unnamed device).

   ADARE repairs this after boot (see :ref:`guest-network-repair`), so these
   images verify green as they are. Rebuilding them picks up the
   ``match: {name: "e*"}`` seed and removes the 120 s penalty as well.


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
  ``adare os-profile show``. Independent of filename.
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

      adare os-profile add my-ubuntu.yml
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
