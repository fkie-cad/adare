*********************************
Host-Side (Agent-Free) Backend
*********************************

The default way ADARE drives a guest is the **agent backend**: ``adarevm``, a
WebSocket server inside the VM, executes GUI actions, shell commands, file
transfers, filesystem snapshots and test functions. The **host-side backend**
(``--backend hostside``) runs the same playbooks with *no process of ours in the
guest*: the host drives the VM through QEMU's monitor and checks it by reading
its disk. This feeds the sibling research project *qemufile* (agentless
differential forensic sandbox), whose evidence store records the run.

.. contents:: On this page
   :local:
   :depth: 2

.. note::

   Scope: QEMU Linux guests (tested: Ubuntu 24.04 arm64 on macOS/HVF). Windows
   guests and VirtualBox stay on the agent backend; ``--backend hostside``
   refuses them. The default is, and stays, ``agent``.


Quick start
===========

.. code-block:: bash

   # one-time, on the host
   uv pip install 'adare[hostside]'          # dissect.* (offline qcow2 / LVM / ext4)
   export ADARE_QFM_SRC=/path/to/qemufile/src # the qfm evidence store, imported by path (see below)
   brew install e2fsprogs                     # only for offline file injection on macOS (debugfs)

   adare experiment run open-single-text-file -e ubuntu-2404-gis --backend hostside --diff

The backend is chosen by, in order: ``--backend``, ``ADARE_BACKEND``, the playbook
``settings.backend``, then ``agent``.

``qfm`` (the qemufile evidence store) is not on PyPI. ADARE imports it **by path**,
without installing it or editing the qemufile tree: ``ADARE_QFM_SRC`` (a directory
containing the ``qfm`` package, i.e. ``<qemufile>/src``), else a ``qemufile`` checkout
next to the ADARE checkout. ``ADARE_HOSTSIDE_MARKERS=off`` disables the markers.


What runs where
===============

The host talks to the guest through one *tool interface*: ``AdareVMClient``
(``screenshot``, ``click``, ``keyboard``, ``execute_shell``, ``get_timestamp``,
``pull_file_chunked``, ``run_test`` ...). The host-side backend implements the
same interface in :class:`~adare.backend.hostside.client.HostsideClient`, so the
playbook controller, the action executors and the CV/VLM grounding are unchanged.

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Tool / feature
     - Host-side implementation
   * - screenshot, click, double/right click, drag, keyboard, scroll
     - QMP ``screendump`` and ``input-send-event`` through the existing
       ``QEMUHostGUIExecutor``. The domain has a USB tablet (absolute pointer);
       pixel coordinates are scaled to the tablet's 0-32767 range from the
       screenshot size. ``goto``, horizontal scroll and per-window screenshots
       are not available. OCR / template / VLM grounding runs on the host
       screenshots exactly as before.
   * - idle
     - ``asyncio.sleep`` on the host.
   * - ``command:`` (file effects)
     - Class (c): applied to the run overlay *before first boot* (see
       :ref:`hostside-inventory`).
   * - ``save_timestamp``
     - The host clock (the guest RTC is seeded from the host, ``<clock
       offset='utc'>``); the guest time zone is read from ``/etc/timezone`` on the
       image. The per-action guest-clock probe (``clock.jsonl``) is off: it needs
       QGA or the agent.
   * - ``test:`` actions
     - Evaluated on the host over a :class:`GuestFS` after the guest quiesced
       (:ref:`hostside-tests`).
   * - ``pull:``
     - Extracted from the quiesced image into ``artifacts/``.
   * - filesystem diff (``--diff``)
     - Base image vs overlay, both walked from the host (``fsdiff``), exported as
       ``artifacts/diff/filesystem_diffs.{json,csv,bodyfile}``. No in-guest ``find``.
   * - system info
     - ``/etc/os-release`` from the image (the agent backend asks the guest).
   * - environment installations
     - Classified like playbook commands; file effects are staged, the rest
       fails before boot.

Run flow (compared with the agent backend):

.. code-block:: text

   agent      overlay -> QGA ready -> install adarevm via QGA -> WebSocket -> actions + tests live -> QGA pull -> stop
   hostside   overlay -> stage (inject) -> boot, wait for settled desktop -> actions (markers) -> ACPI shutdown
              -> evaluate deferred tests on the image -> pull / diff / report from the image

The backend also removes the QEMU guest-agent virtio-serial port from the libvirt
domain (``QEMUVMConfig.guest_agent_channel = False``): the guest's
``qemu-guest-agent`` service needs that port, so it does not start. ADARE then
neither installs nor requires any guest component for the run.


Step markers (qemufile evidence store)
======================================

Every playbook step is written as a ``marker`` event (qemufile ``docs/SCHEMA.md``
section 5, source ``orchestrator``) into a qemufile **run directory** at
``<adare run>/qfm/`` (``spec.yaml``, ``env.json``, ``events.jsonl``). Each event
carries host monotonic (``t_mono_ns``) and wall (``t_wall``) time stamped back to
back by ``qfm.store.EventWriter``, so other sensors writing into the same run
directory (the live RAM poller, qfmonitor disk events) share the time base.

.. code-block:: json

   {"v":1,"seq":9,"t_mono_ns":226434166084416,"t_wall":"2026-11-01T18:36:41.334380Z","t_guest_ns":null,
    "source":"orchestrator","type":"marker","subject":{},
    "data":{"marker":"adare.step.start","step":"a11","action":"ClickAction",
            "context":"a11_click_double_adare.txt","detail":"target.text=adare.txt"},
    "provenance":{"sensor":"adare-hostside","reader":"unknown","paused_ms":0,
                  "consistency":"synchronous","basis":"sensor-design","note":"..."}}

Marker names: ``adare.step.start`` / ``adare.step.end`` (``step``, ``action``,
``description``, ``detail``, ``success``), ``adare.hostside.stage.*``,
``adare.hostside.inject.*``, ``adare.vm.start|ready``, ``adare.command.staged``,
``adare.test.deferred|evaluate|result``, ``adare.pull.deferred|done``,
``adare.vm.quiesce.start|end``, ``adare.fsdiff``, ``adare.vmi.pslist``.
``qfm events validate <run>/qfm`` passes on them.


.. _hostside-tests:

Host-side tests: ``GuestFS``
============================

Ground-truth test functions need ``open / read / exists / stat / listdir`` on guest
paths. ADARE already had a host test path (``--test-mode host``) whose transport is the
QEMU guest agent; the host-side backend keeps its executor and replaces the transport
with a :class:`~adare.backend.hostside.guestfs.GuestFS`:

``OfflineDiskGuestFS``
   The guest disk image: qcow2 chain (backing files resolved by ADARE) -> GPT/MBR ->
   LVM logical volume -> ext4, through ``dissect``. Valid for a **quiesced** image
   only (VM stopped, or a copy): QEMU does not lock out other readers, and reading a
   qcow2 that QEMU is writing risks torn reads. ``stat`` returns inode metadata (mode,
   uid/gid with names resolved from the image's ``/etc/passwd``, atime/mtime/ctime/crtime).
``PatchedGuestFS``
   A base ``GuestFS`` plus the staged offline operations: the guest's *initial* state
   without copying an image.
``LiveGuestFS``
   **Extension point** for a RAM-first extractor (qemufile ``vmi_file_extract`` / the Rust
   core): page cache first, disk fallback, provenance per read. It is what mid-run test
   points need; see the class docstring for the contract. Not implemented.

**State points.** A guest's page cache and journal are invisible on its disk, and the disk
cannot be read consistently while the VM runs. So ``test:`` actions are *deferred*: at its
position a test only writes an ``adare.test.deferred`` marker; the tests then run through the
normal action pipeline (events, database records, console) in a second pass after the guest
shut down cleanly. Each test is evaluated against a state point:

* ``initial`` (base image + staged operations): tests placed *before the first GUI input*
  (``click``, ``drag``, ``keyboard``, ``scroll``). These are pre-conditions of the interaction.
* ``final`` (the quiesced overlay): every later test.

Consequences: a failing test no longer interrupts the GUI run at its position (the run
has ended by then); ``continue_on_test_failure`` applies to the verification pass; a test
that must observe a *mid-run* state needs ``LiveGuestFS``. Tests that need live state
(``process_running``, ``system_service_status``, registry) fail the pre-flight before boot.

``file_permissions``, ``file_timestamps``, ``user_exists`` and ``log_entry_exists`` are answered from
inodes and files of the image (owner names resolved inside the image).


.. _hostside-inventory:

Inventory: what cannot be host-side, and how it is handled
==========================================================

``scripts/hostside_inventory.py`` scans playbooks, environments and test functions and
classifies every use. Classes:

(a) **provisioning time** - belongs in the image / recipe (packages, services, users).
(b) **GUI user action** - do it through the GUI like a real user (launching an application).
(c) **offline injection** - a file effect applied to the overlay before first boot.
(d) **needs a guest component** - anything else (processes, pipes, network, services).

.. list-table::
   :header-rows: 1
   :widths: 24 10 66

   * - Feature
     - Class
     - Handling in the host-side backend
   * - ``echo 'text' > file``, ``rm -f``, ``mkdir -p``, ``chmod NNN``, ``touch [-a|-m] -t``,
       ``chown`` of staged paths, ``&&`` chains of these, process-kill no-ops
     - c
     - Implemented: staged into the overlay before boot (libguestfs where present, else
       e2fsprogs ``debugfs``). Ownership follows the playbook user (``admin: true`` is root).
       A mid-run occurrence (after the first GUI input) is applied before boot with a warning.
   * - ``apt-get install`` / ``pip`` / ``curl``-installs, ``systemctl``, ``useradd``
     - a
     - Refused before boot with the class; move them to the image recipe
       (``adare env extend`` / recipe ``postsetupinstallations``).
   * - Launching applications (``xdg-open``, ``nautilus``, ...)
     - b
     - Refused before boot; use a ``click`` / ``keyboard`` action.
   * - Any other command (``ls``, pipes, ``cp``, scripts, PowerShell, polling loops)
     - d
     - Refused before boot (``HostsideUnsupportedError`` if it appears nested at run time).
       Needs the agent backend or a guest component.
   * - ``save_timestamp``
     - -
     - Host clock; guest time zone from the image. Precision is bounded by the guest/host
       clock offset (the guest RTC is seeded from the host).
   * - ``pull:``
     - -
     - Extracted from the image after shutdown (also after a failed test's auto-pull).
   * - ``snapshot_filesystem`` / ``pull_changed_files``
     - d
     - Not supported; use ``--diff`` (offline base-vs-overlay diff).
   * - Tests: ``file_*``, ``json.*``, ``xml.*``, ``csv.*``, ``sqlite.*``, ``excel.*``
     - -
     - Run unchanged on the host over a mirror of the files read from the image.
   * - Tests: ``process_running``, ``system_service_status``, registry, event log
     - d
     - Need live guest state; pre-flight failure. They require the RAM-first ``LiveGuestFS``.
   * - Per-action guest clock probe
     - d
     - Off (needs QGA / agent).
   * - Guest network repair after boot (netplan rename), clipboard, per-window screenshots,
       Windows icon extraction
     - d
     - Not available; the agent backend does them.

The inventory of this repository (``paper/experiments`` and the Tproj1 project, 85 playbooks)
is in ``docs`` of the branch report; the numbers are reproduced by

.. code-block:: bash

   python scripts/hostside_inventory.py --root paper/experiments --root ../projects/Tproj1/experiments \
       --env-dir ~/.adare/state/environments --markdown


Consistency and limits
======================

* **Clean shutdown required.** The image is read after an ACPI shutdown (if the desktop asks first, as
  GNOME can with a "Power Off" dialog, Enter confirms it; the Ubuntu 24.04 guest used here shut down
  by itself in about 3 s). If the guest does not stop in ``ADARE_HOSTSIDE_SHUTDOWN_TIMEOUT``
  (120 s) it is destroyed, the run is marked ``clean: false`` and results are best-effort:
  dissect does not replay the ext4 journal.
* **Readiness has no agent to ask.** The desktop counts as ready when the framebuffer has been
  still for 12 s and is not mostly black (``ADARE_VM_READY_TIMEOUT``, default 420 s).
* **Not an unmodified disk.** Class (c) injection edits the overlay; the *base* image is
  never written. Injection through ``debugfs`` costs about 10-15 s (a raw conversion of
  the disk and a cluster scan).
* **The base image may carry guest-agent leftovers.** ADARE-provisioned images contain
  ``qemu-guest-agent`` (the agent backend drives installation through it), an empty ``/adare``
  mount point and a pip configuration. ``adarevm``/``adarelib`` are *not* in the image: the agent
  backend installs them on every run (about 2400 paths, see the comparison below). The host-side
  backend starts none of these programs and removes the QGA channel, but a *zero static footprint*
  needs an image built without them.
* **Mid-run observation** (a test or diff at an arbitrary step) needs ``LiveGuestFS``.
* The existing ``--gui-mode host`` / ``--test-mode host`` options are unchanged: they remove
  the agent's *transport* but still use ``qemu-guest-agent`` (QGA) in the guest for
  commands, file transfer and installations. ``--backend hostside`` uses no QGA.
* The agent backend remains the reference for Windows guests, VirtualBox, multi-machine
  playbooks and every ``command:`` that is not a file effect.

Debugging aids: ``ADARE_HOSTSIDE_SKIP_INJECT=1`` (do not apply staged operations),
``ADARE_HOSTSIDE_PSLIST=1`` (pause the guest at the end of the run and list its processes from
RAM with the qemufile VMI layer: ``hostside/pslist.json``; needs ``ADARE_QEMUFILE`` or a checkout
next to ADARE).


Comparing the two backends
==========================

.. code-block:: bash

   # the same experiment, both backends
   adare experiment run exp -e env --diff --diff-mode guest --export-disk-image          # agent
   adare experiment run exp -e env --backend hostside --diff                             # hostside
   python scripts/hostside_compare.py <agent run dir> <hostside run dir> --markdown      # tests, diff, timings
   python scripts/hostside_image_diff.py <base.qcow2> <exported final .raw>             # base-vs-end footprint of the agent run

``hostside_compare.py`` lines up the test results of both runs, and reports how much of each
filesystem diff is the in-guest agent's own activity (``adarevm``/``adarelib`` files, the Python
packages it imports, ``/tmp/adare_*``). The agent backend's in-guest ``find`` diff covers only the
window between the two snapshots (after the agent started); the host-side diff covers base image
to final overlay, so it includes boot and desktop-login activity.


Files written per run
=====================

.. code-block:: text

   <run>/qfm/                 qemufile run directory: spec.yaml env.json events.jsonl
   <run>/hostside/hostside-report.json   plan, staged operations, timings, shutdown, pulls
   <run>/hostside/footprint.json         agent footprint read from the image
   <run>/hostside/pslist.json            (ADARE_HOSTSIDE_PSLIST) live process list
   <run>/artifacts/diff/                 offline filesystem diff (--diff)
   <run>/artifacts/<pulled files>        pull: actions
