************
File Sharing
************

Every experiment needs to move files between the host and the guest VM:
playbook data, agent wheels, test functions, tools, and -- after
execution -- artifacts and logs. ADARE uses a strategy pattern to select
the best file transfer mechanism for the current platform and available
tooling.

.. contents:: On this page
   :local:
   :depth: 2


The FileTransferStrategy Interface
===================================

All strategies implement the abstract base class
``adare.hypervisor.qemu.file_transfer.base.FileTransferStrategy``.
The lifecycle calls three methods in order:

1. ``setup(context)`` -- called **before VM boot**. Prepares the transfer
   mechanism: creates shared directories, copies files to a staging area,
   or writes files directly to the guest disk.

2. ``post_boot_transfer(context)`` -- called **after the VM has booted**
   and the guest agent is ready. Mounts filesystems, uploads files via
   QGA, or performs other actions that require a running guest.

3. ``retrieve_artifacts(context)`` -- called **at experiment end**. Collects
   logs, screenshots, and test artifacts from the guest.

Each strategy also declares:

- ``requires_vm_stop_for_retrieval()`` -- whether the VM must be shut down
  before artifacts can be retrieved (``True`` for Libguestfs, ``False`` for
  the others).
- ``setup_description``, ``post_boot_description``,
  ``retrieval_description`` -- human-readable labels used in progress
  output.


Strategies
==========

VirtioFS (Linux default)
------------------------

``VirtioFSStrategy`` -- the fastest option. Uses the ``virtiofsd`` daemon and
the kernel ``virtiofs`` driver to expose host directories directly inside the
guest. No file copying is needed; the guest reads and writes the host
filesystem through shared memory.

- **Setup**: creates host directories, writes ``config.json`` to the run
  directory, stores the share list in ``QEMUVMConfig`` so the libvirt XML
  builder adds ``virtiofs`` filesystem devices.
- **Post-boot**: mounts each share inside the guest
  (``mount -t virtiofs <tag> /adare/<name>`` on Linux;
  ``virtiofs.exe -t <tag> -m C:\adare\<name>`` on Windows).
- **Retrieval**: artifacts are already on the host -- the strategy only
  verifies and copies log files to the expected locations.

SMB (macOS default)
-------------------

``SMBStrategy`` -- uses QEMU's built-in SLIRP SMB support. On macOS,
``virtiofsd`` is typically unavailable, but Samba can be installed via
Homebrew. QEMU starts an embedded ``smbd`` process that serves a host
directory to the guest at ``//10.0.2.4/qemu``.

- **Setup**: builds the share list (same as VirtioFS), creates a temporary
  directory with **copies** of each share's host content (Samba 4.x blocks
  symlinks outside the share root), and sets ``smb_share_path`` on the VM
  config.
- **Post-boot**: mounts the CIFS share inside the guest
  (``mount -t cifs //10.0.2.4/qemu /adare`` on Linux; ``net use Z:`` plus
  directory junctions on Windows). If the mount fails, falls back
  automatically to the QGA strategy.
- **Retrieval**: copies read-write shares back from the temporary directory
  to the original host paths (the writeback step), then verifies artifacts.
- **Cleanup**: performs a safety writeback and removes the temporary
  directory.

Libguestfs (Linux fallback)
----------------------------

``LibguestfsStrategy`` -- manipulates the guest disk offline using the
``guestfish`` CLI. This is the fallback on Linux when ``virtiofsd`` is not
installed, or when the ``QEMU_LIBGUESTFS`` environment variable is set.

- **Setup**: stops the VM (if running), mounts the disk image with
  guestfish, copies files to the guest filesystem, and unmounts.
- **Post-boot**: no action needed -- files are already on disk.
- **Retrieval**: requires the VM to be stopped first
  (``requires_vm_stop_for_retrieval()`` returns ``True``), then extracts
  artifacts from the disk via guestfish.

QGA (final fallback)
--------------------

``QGAStrategy`` -- transfers files through QEMU Guest Agent
``guest-file-*`` operations. This is the fallback on macOS when neither
``virtiofsd`` nor Samba is available. It is the slowest strategy because
every file is serialised and sent individually over the QGA channel.

- **Setup**: builds a file manifest and disables VirtioFS config. The actual
  upload is deferred because QGA requires a running VM.
- **Post-boot**: uploads all files from the manifest via QGA guest-file
  operations.
- **Retrieval**: downloads artifacts via QGA before VM shutdown.


Strategy Selection
==================

The factory function ``get_file_transfer_strategy()`` in
``adare.hypervisor.qemu.file_transfer`` calls ``detect_file_transfer_mode()``
to choose a strategy. The decision logic:

1. If the ``QEMU_LIBGUESTFS`` environment variable is set to ``true``,
   force **libguestfs** mode.
2. If ``virtiofsd`` is on ``PATH``, use **virtiofs**.
3. On **macOS** without ``virtiofsd``:

   a. If ``smbd`` is available (and QEMU can find it at its compiled-in
      path), use **smb**.
   b. If ``guestfish`` is available and its appliance is functional, use
      **libguestfs**.
   c. Otherwise, use **qga**.

4. On **Linux** without ``virtiofsd``, use **libguestfs**.

The ``smbd`` detection is macOS-aware: QEMU hardcodes the ``smbd`` path at
compile time (typically ``/opt/local/sbin/smbd`` for MacPorts builds), so
ADARE checks whether that exact path exists and is executable. If Homebrew's
Samba is installed at a different path, ADARE logs a symlink instruction.


What Gets Shared
=================

All strategies share the same set of host-to-guest directory mappings,
built by ``build_share_list()`` in ``adare.hypervisor.qemu.file_transfer.shares``.
The standard shares are:

.. list-table::
   :header-rows: 1
   :widths: 15 30 30 10

   * - Tag
     - Host Path
     - Guest Mount
     - Mode
   * - ``run``
     - Experiment run directory (logs, artifacts, playbook)
     - ``/adare/run``
     - read-write
   * - ``vm``
     - Project VM runtime (adarevm/adarelib wheels)
     - ``/adare/vm``
     - read-only
   * - ``experiment``
     - Experiment directory
     - ``/adare/experiment``
     - read-only
   * - ``project_shared``
     - Project shared directory (tools, data)
     - ``/adare/project_shared``
     - read-only
   * - ``shared``
     - Experiment shared directory (tools, data)
     - ``/adare/shared``
     - read-only

User-defined shared directories from the experiment configuration are
appended to this list.

A ``config.json`` file is written to the run directory before boot. It tells
the ``adarevm`` agent where to find tools, data files, and where to write
its log:

.. code-block:: json

   {
     "tools_paths": [
       "/adare/project_shared/tools",
       "/adare/shared/tools"
     ],
     "data_paths": [
       "/adare/project_shared/data",
       "/adare/shared/data"
     ],
     "logfile": "/adare/run/logs/adarevm.log",
     "installation_mode": "wheel"
   }

Windows guests use the same structure with ``C:\adare\`` paths.

See :doc:`hypervisors` for how file transfer fits into the overall VM
lifecycle.
