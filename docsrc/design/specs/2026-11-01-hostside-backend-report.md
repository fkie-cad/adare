# Host-side (agent-free) backend: report

Branch `hostside-driver` (uncommitted, for review). User documentation: `docsrc/source/guide/hostside-backend.rst`.
Measured on one host (Apple Silicon, macOS 26, HVF, libvirt session, 16 cores, **three to four other 4-vCPU VMs
running concurrently** from another job, so absolute timings are noisy; boot waits ranged 151-335 s).

## 1. What was found first

ADARE already had half of the picture, which shaped the design:

| existing | state |
|---|---|
| `--gui-mode host` (default for QEMU) | QMP `screendump` + `input-send-event`, USB tablet, coordinate scaling, per-event key pacing. **Complete**; the host-side backend reuses it unchanged. |
| `--test-mode host` (`GuestToHostTestExecutor`) | pulls the file a test names to a temp mirror, rewrites `dst`, runs the test function on the host. Transport = **QGA** (qemu-guest-agent in the guest). |
| `--diff-mode host` | base vs overlay through libguestfs (`virt-ls`); not installed on this macOS host. |
| `run.py` "full host mode" (`needs_agent = False`) | **Does not run**: `PlaybookController.execute_playbook` refuses `client is None`, `command`/`save_timestamp`/`pull` call `self.client`, the per-action clock probe uses QGA. |

Two latent defects in the existing host-test path were fixed because the new backend depends on them (both would
affect `--test-mode host` too):

1. `TestActionsExecutor._execute_host_mode_test` / `_execute_host_side_test` handed `TestResultProcessor` a dict of the
   wrong shape (`{'status': <StatusEnum>, 'details': ...}` instead of the agent's `{'status': 'success', 'result': {...}}`),
   so **every host-evaluated test read as UNKNOWN, i.e. failed**. Fixed by `_as_tool_result` (+ tests).
2. `TestLoader.structure_host_test` could not structure `str | int | float` parameters (`standard.file_timestamps`):
   cattrs raised "Unsupported type". A passthrough hook for scalar unions is registered.

## 2. Design

* **Backend abstraction**: `agent` (default) / `hostside`, chosen by `--backend` > `ADARE_BACKEND` > playbook
  `settings.backend`. The seam is the tool interface the host already talks to: `HostsideClient` has the method surface of
  `AdareVMClient`, so the controller, executors, CV/VLM grounding and the event/DB pipeline are unchanged. The lifecycle
  hooks (`VMLifecycleManager`: stage instead of file transfer, boot-and-wait-for-desktop instead of the QGA wait, offline
  retrieval/diff) live in `adare/backend/hostside/lifecycle.py`.
* **No guest component at all**: no adarevm, no agent install; the QGA virtio-serial channel is removed from the domain
  (`QEMUVMConfig.guest_agent_channel = False`), which keeps the guest's `qemu-guest-agent` from starting; readiness is the
  screen (framebuffer still for 12 s and not mostly black: a booting guest shows "Display output is not active.").
* **Host-side tests**: `GuestFS` (`open/read_bytes/exists/stat/listdir/glob/extract/iter_tree`). `OfflineDiskGuestFS`:
  qcow2 chain -> GPT -> **LVM** -> ext4 via dissect (re-implementing qemufile's `vmi_disk_qcow2/partitions/fs` and adding LVM,
  which these Ubuntu images need). `PatchedGuestFS` = base + staged operations = the *initial* state without an image
  copy. `LiveGuestFS` = documented extension point for the RAM-first extractor. `HostsideTestExecutor` subclasses the
  existing host-mode executor and swaps the transport (extract from a GuestFS instead of QGA; `file_permissions`,
  `file_timestamps`, `user_exists`, `log_entry_exists` answered from inodes/files).
* **State points / deferral**: a disk image cannot be read consistently while the VM runs (page cache, journal, torn qcow2
  reads), so `test:` actions are deferred and evaluated in a second pass (`second_pass.py`) after a clean ACPI shutdown,
  through the normal action pipeline (events, DB, console). Tests before the first GUI input are evaluated against the
  `initial` state point (base + staged operations), later ones against `final`.
* **Markers**: every action brackets `adare.step.start/end` into `<run>/qfm/` through `qfm.store.EventWriter`
  (host monotonic + wall time, validated). `qfm` is imported by path (`ADARE_QFM_SRC`), not installed, to leave the
  qemufile tree untouched. 94 events in the E2E run, `EventReader.validate()`: 0 invalid, no seq gaps.
* **Offline injection (class c)**: file-effect commands are planned (`commands.py`) and applied to the overlay before first
  boot: libguestfs where present (untested here, no guestfish on macOS), else e2fsprogs `debugfs -w` on a raw copy with
  only the changed 64 KiB clusters written back to the qcow2 (`qemu-io`): 10-14 s, 7 clusters, base image untouched.
* **Pre-flight**: everything else a playbook/environment runs through the agent is classified a/b/d and the run **fails
  before boot** naming the class (nothing is silently dropped).

## 3. End-to-end result

Experiment: `open-single-text-file-ubuntu-2404` (paper section 5.2, 11 tests on `recently-used.xbel`), unchanged playbook,
environment `ubuntu-2404-gis` (`examples/hostside/`; the first-login wizard and the 26.04 release-upgrade dialog would
otherwise cover the desktop; both are suppressed by environment installations, which the host-side backend stages offline).

| | agent | hostside |
|---|---|---|
| verdict | SUCCESS (11/11 tests, 21/21 actions) | SUCCESS (11/11 tests, 21/21 actions) |
| per-test results | identical (`hostside_compare.py`) | identical |
| xbel timestamp tests | within +-5 s of `open_timestamp` (guest clock) | within +-5 s (host clock; measured offset -2.1 s) |
| total (console "Duration") | 3 m 59.6 s | 4 m 21.1 s |
| VM setup | 141.4 s (QGA ready after 128.3 s) | 166.2 s (staging 10.5 s + desktop wait 154.4 s) |
| agent install + connect | 8.0 s | 0 |
| playbook stage | 78.9 s | 60.7 s (of which quiesce 6.0 s, test evaluation 1.7 s) |
| cleanup | 5.5 s (+ disk export) | 28.8 s (offline diff 28.5 s) |
| processes of ours in the guest | **qemu-ga (pid 713), adarevm (pid 2297)** among 233 tasks | **none**: 225 tasks, no qemu-ga/adarevm/python |
| `qemu-ga` lines in the guest syslog during the run | present | **0** of 2098 |
| paths added by agent software, base image -> end image | **2437** of 2918 added + 141 modified | **0** of 418 added + 41 modified |

Footprint detail of the agent run (`scripts/hostside_image_diff.py`, base qcow2 vs the `--export-disk-image` raw): 142 paths
of adarevm/adarelib (`/usr/local/bin/adarevm`, dist-packages, dist-info), 2286 paths of the Python dependencies it
installs, 9 `/tmp/adare_testfunctions_*`. The agent's **own in-guest `find` diff cannot see this**: it is taken after the
install, so it only shows the agent's *run-time* activity (106 of 678 changed paths: `/adare/run/logs/adarevm.log`, 26
adarevm/adarelib `.pyc`, 76 dependency `.pyc`, 4 temp files). The two diffs also cover different windows: the host-side one
is base to end (it includes boot and desktop login), the agent's is before/after the playbook.

The process lists come from the qemufile VMI layer (`vmi_procwalk.iter_tasks` over a QMP pause + pmemsave, `init_task` taken
from the image's `System.map`), 2.6-2.7 s pause each, no guest involvement; the same probe finds both agent processes in the
agent run (positive control).

Timings of the host-side stages (3 successful runs): staging 10-14 s, desktop wait 151-154 s (335 s once, host overloaded),
run 51-53 s, quiesce 2-6 s (clean ACPI shutdown, GNOME needs no confirmation), deferred evaluation 1.3-1.7 s, offline
diff 25-28 s (about 189k entries per image, 13 s each). The host-side backend is not faster end to end: it moves work (no
agent install, but a fuller diff) rather than removing it; what it removes is the guest footprint and the QGA dependency.

## 4. Inventory (`scripts/hostside_inventory.py`; 85 playbooks of `paper/experiments` and Tproj1, the environment files in `~/.adare/state/environments`)

| use | count | classification and handling |
|---|---|---|
| `command:` actions | 177 in 65 playbooks | **c (offline-injectable) 60**: `echo > file`, `rm -f`, `touch -a -t`, `mkdir -p`; **a (provisioning) 6**: `apt-get install ...`; **d needs a guest component 28**: polling loops, `cp`, pipes; **Windows PowerShell 83** (out of scope: Windows stays on the agent) |
| `pull:` | 35 | extracted from the quiesced image |
| `save_timestamp` | 16 | host clock + guest zone from the image |
| `test:` actions / functions | 1396 uses; `file_content` 1215, `file_based` 149, `qga_probe` 16, untagged legacy names 59 | all run host-side; the 16 `qga_probe` are `file_timestamps` (answered from the inode); `process_running`, services, registry would fail pre-flight (need live state) |
| environment installations | 31 | **a 23** (`apt`/`curl` installs: image recipe), **c 5** (wizard flag, upgrade prompt: staged), **d 3** (scripts with `sudo -u adare env ...`) |
| `snapshot_filesystem`, `pull_changed_files` | not used here | d: replaced by `--diff` (offline) |
| in-guest `find` before/after (`linux_fs_snapshot.py`) | `--diff --diff-mode guest` | replaced by the offline base-vs-overlay diff |
| guest clock probe per action | all agent runs | off (needs QGA/agent) |
| guest network repair after boot (netplan rename, QGA) | boot path | not available host-side; guests whose NIC is renamed away from the installer's name have no network |

Per-feature handling and the (a)/(b)/(c)/(d) definitions are in the guide. One behaviour to know: `touch -a -t 200001010000 file`
appears in the paper playbook *after* the file manager navigated; staged before boot it resets the atime earlier, so
`text_file_accessed` is weaker (any read, including a file manager's, restores it). A warning names such mid-run occurrences.

## 5. Open problems and limits

1. **Mid-run observation.** Tests are evaluated after the run (state points `initial`/`final`). A failure no longer stops the
   GUI run at its position. A consistent *mid-run* view needs the RAM-first `LiveGuestFS` (qemufile `vmi_file_extract`);
   Alt+SysRq+S via QMP plus a blockdev snapshot was considered and rejected (GNOME binds Alt+Print to a screenshot, which
   writes into the guest).
2. **Clean shutdown required** (dissect does not replay the ext4 journal). A guest that does not stop within 120 s is
   destroyed and the run is marked `clean: false`.
3. **Staging cost and platform.** debugfs injection works on one linear LVM or a plain partition of an ext4 root; it needs
   e2fsprogs (not on PATH on macOS). The libguestfs injector exists but is **untested** here.
4. **Readiness is heuristic** (still, non-black frame for 12 s). A late modal dialog still breaks image-based clicks (an
   update dialog did, until suppressed in the environment) - true for the agent backend too.
5. **Not covered**: Windows guests, VirtualBox, multi-machine playbooks, `goto`, horizontal scroll, per-window screenshots,
   ext4 only (NTFS needs a second GuestFS backend, qemufile has one in `vmi_disk_fs/ntfs.py`).
6. `quality_ratchet.py`: no new debt (ruff/mypy/size); `uv.lock` updated for the new optional extra (`adare[hostside]`).
7. The first run on a fresh host needs `ADARE_QFM_SRC` (or a sibling `qemufile` checkout) and, for staging on macOS, e2fsprogs.

## 6. Recommended next step

Wire `LiveGuestFS` to qemufile's `vmi_file_extract` (page cache first, disk fallback) so test points can run at their
position with provenance per read, and port the LVM volume location into qemufile's `vmi_disk_fs`. That removes the
deferral (the largest semantic difference to the agent backend) and gives the orchestrator the live process/file state
that the playbook-level tests `process_running` / `system_service_status` need.
