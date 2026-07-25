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

.. note::

   The fallback to QGA is logged as a **warning** and relabels the progress
   stage. It is a large performance regression (QGA transfers file-by-file
   through the guest agent), so it should never pass unnoticed. If you see it,
   the two causes worth checking first are a guest image without
   ``cifs-utils``/``mount.cifs``, and a guest with no IPv4 route to
   ``10.0.2.4`` -- see :ref:`guest-network-repair`.

.. _guest-network-repair:

Guest network repair
--------------------

Every SMB mount depends on the guest actually having a working network, and
that cannot be taken for granted, because **ADARE gives the NIC a different PCI
address at run time than the installers use**:

- the VM creators build a raw QEMU command line with an auto-assigned NIC
  (``-device virtio-net-pci,netdev=net0``), which lands on ``pcie.0`` slot
  ``0x01``, so the guest sees ``enp0s1`` -- and that is the name the installer
  bakes into ``/etc/netplan/*.yaml``;
- experiment runs go through
  ``libvirt_xml_builder._add_network_commandline()``, which pins
  ``bus=pcie.0,addr=0x1f``, so the same NIC enumerates as ``enp0s31``.

That path is taken for *every* experiment, because ``_add_network()`` defers to
the ``qemu:commandline`` builder whenever SMB **or** port forwarding is active,
and the adarevm websocket forward is always active.

A guest whose network config names one interface therefore ends up with only
``lo``: ``systemd-networkd-wait-online`` burns its full **120 s** timeout on
every boot, nothing can reach the SLIRP SMB server, and the adarevm websocket
has no guest-side stack. NetworkManager-managed guests (Fedora) are unaffected,
and Ubuntu 24.04 is rescued by NetworkManager *after* paying the 120 s.

``hypervisor/qemu/guest_network.py`` repairs this after boot, before anything
depends on the network. It is idempotent and best-effort:

1. if any non-loopback interface already has an IPv4 address, do nothing;
2. otherwise bring every non-loopback link up and give the guest's own DHCP
   client a few seconds to claim it;
3. if nothing claims it, assign SLIRP's fixed addressing directly --
   ``10.0.2.15/24``, gateway ``10.0.2.2`` -- and point the resolver at
   ``10.0.2.3`` via ``resolvectl`` (needed because the agent bootstrap installs
   from PyPI).

Nothing is written to the guest filesystem on the normal path -- only in-memory
kernel and ``systemd-resolved`` state -- so guest disk state stays clean for
forensic purposes. Only if ``resolvectl`` is unavailable does it fall back to
writing ``/etc/resolv.conf``.

The install-time half of the fix is in the ``autoinstall_*`` templates, which now
match the interface **by pattern** (``match: {name: "e*"}``) instead of by name,
so images built from here on are immune to the PCI address. Images built before
that change still need the run-time repair, and still pay the 120 s
``wait-online`` timeout on boot -- which is why the guest-agent readiness budget
escalates per attempt (see ``lifecycle.py:_ready_timeout_for_attempt``).

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

.. warning::

   **Known limitation: QGA-via-libvirt is not a dependable bulk transport for the
   aarch64 Ubuntu/Kubuntu desktop guests.** Partway through an upload the agent
   stops answering even libvirt's 5-second ``guest-sync``
   (``Guest agent is not responding: guest agent didn't respond to synchronization
   within '5' seconds``), after which every ``guest-file-write`` trips
   ``QGA_FILE_OP_TIMEOUT``. It fails on the ~2 MB tar first, then again on the
   61,828-byte ``adarevm`` wheel that the per-file fallback retries — which is the
   ``Failed to upload adarevm-*.whl`` error seen in ``adare env verify``.

   The usual suspects have been measured out:

   - **not throughput** — the identical 61,828-byte ``guest-file-write`` completes
     in about **1 ms (45-53 MB/s)** on three of the same disks when written
     straight to the QGA unix socket rather than through libvirt;
   - **not the timeout** — the agent is unresponsive to a *5 s* sync, so a larger
     ``QGA_FILE_OP_TIMEOUT`` changes nothing;
   - **not the chunk size** — tested at both 16 KB (~22 KB base64) and 64 KB
     (~85 KB); both wedge at the same point.

   The root cause inside qemu-ga/libvirt has **not** been identified. The practical
   consequence is that guests must be kept *off* this path: make sure the image has
   ``cifs-utils``/``mount.cifs`` so the SMB strategy is used (~1 s for the same
   payload). The autoinstall templates now install it; images built before that
   change need a rebuild or an ``env extend``.


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

.. important::

   **Write experiment outputs to the run share.** Only the ``run`` share is
   read-write, and it maps directly onto the host experiment run directory, so
   anything a playbook writes there is retrieved back to the host on **every**
   backend. In a playbook, target it through the automatic variable
   ``adare_run_dir`` (``C:\adare\run`` / ``/adare/run``) -- for example, copy a
   generated report to ``{{ adare_run_dir }}\artifacts\report.xlsx``. The
   ``artifacts`` and ``logs`` subdirectories are created automatically. The
   host-to-guest **input** channels (``adare_shared_data``,
   ``adare_project_shared_data``, etc.) are the wrong destination for outputs.

.. warning::

   **The read-only modes above are not enforced uniformly across backends.**
   Read-only is honoured under **SMB** (writes to a read-only share are
   discarded on cleanup and never reach the host) but **not** under
   **virtiofs** (the guest can write through to the host path). A playbook that
   writes outputs to ``adare_shared_data`` therefore appears to "work" on Linux
   (virtiofs) yet silently loses those files on macOS (SMB). Do not rely on
   writes to any read-only share -- always write outputs to ``adare_run_dir``.

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
