Host Resources and Capacity
===========================

ADARE runs every experiment in its own VM, so the host's RAM, CPU and disk decide
how many runs can go at once and how long the disk lasts. ADARE measures all three
and shows them on the **System** page of the web UI (``adare ui start``, then
*System* in the sidebar) and through ``adare system``.

What is measured
----------------

Live host load
   CPU load, used and available memory, and free space on the filesystem holding
   the ADARE state (``~/.adare``). The home dashboard shows the same tiles.

Running VMs
   Every QEMU process on the host (experiment runs, dev sessions, image builds)
   with its resident memory, CPU and configured guest size. Processes that belong
   to a registered VM instance link to the instance and its run.

What each run used
   While an experiment run's VM is up, ADARE samples its QEMU process every five
   seconds and, when the run ends, records the peak resident memory, the average
   and peak CPU and the physical size of the run's disk files. Each machine of a
   multi-machine run gets its own record. ``adare system usage`` lists them.

Usage history
   While the web UI runs, it stores one host sample per minute (CPU, memory, disk,
   running VMs) and keeps 30 days. The System page charts the last 6 hours to 30
   days. Nothing is recorded while the web UI is stopped; per-run measurements do
   not depend on it.

Storage
   Physical (allocated) size of ADARE's directories: environment disks, run and
   dev-session disks, converted templates, download and build caches, installer
   ISOs and everything else, plus the size of every registered project. The
   report walks the disks and is cached for five minutes (``--refresh`` or the
   *Re-measure* button measures again).

Capacity: how many more runs fit
--------------------------------

For every current environment ADARE estimates how many more runs the host can
start right now, and which resource runs out first.

- **Free resources** are the available memory, idle cores and free disk, minus a
  reserve for the host: 10% of RAM (at least 4 GiB) and 5% of the disk (at least
  20 GiB).
- **Per-run need** comes from that environment's last ten measured runs when there
  are any: the highest peak memory and disk use, and the median CPU use. Until an
  environment has been measured, the configured size is used: 8 GiB RAM for
  Windows guests and 4 GiB otherwise (the run defaults) plus QEMU overhead, half of
  the four vCPUs busy, and 8 GiB of disk for the overlay and artifacts.
- RAM and disk are hard limits. CPU can be overcommitted, so it only limits once
  the busy cores run out.

The estimate is a starting point for planning, not a reservation: the playbook's
``settings.vm_memory`` or ``--vm-memory`` change what a single run actually gets.

Reclaiming disk space
---------------------

Run and dev-session disks in ``~/.adare/qemu/disks`` are grouped by the VM
instance that owns them. A group whose instance has no database row (a crashed
run, or an instance from before per-run overlays) is shown as *No owner*, and its
total as reclaimable. These are the files ``adare vm prune`` reclaims: run it
without options to preview, then with ``--force`` to delete. Neither the System
page nor ``adare system`` deletes anything.

Commands
--------

.. code-block:: bash

   adare system resources        # live CPU, memory, disk and running VMs
   adare system capacity         # how many more runs of each environment fit
   adare system usage -e win11   # what recent runs of an environment used
   adare system storage          # where the disk space goes
   adare --format json system capacity   # for scripts and agents

See :doc:`../reference/cli` for all options.
