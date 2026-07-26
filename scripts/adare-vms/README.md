# adare-vms — genuine desktop → ADARE-ready provisioning

Offline, idempotent provisioning that turns a **genuine** installed desktop disk
(GNOME/KDE, native default session) into an **ADARE-ready** base image, then
zstd-recompresses it. Paired with the host/QMP path in `adare vm test`, these
produce shareable base disks verified with `adare vm test <name> --verbose --remove-vm`
→ "✅ compatible with ADARE".

## Scripts

- **`provision_adare.sh <disk.qcow2> <ubuntu|kubuntu|fedora>`** — via `virt-customize`:
  installs `qemu-guest-agent`, `cifs-utils`, `openssh-server`, `curl`, `python3-pip`;
  `uv` → `/usr/local/bin`; NOPASSWD sudo for `adare`; autologin using each distro's
  **genuine default** session (GDM3 / SDDM / GDM — **no X11 forcing**, native Wayland
  where that is the default); disables idle screen-blank + screensaver lock (GNOME dconf
  system DB, KDE kscreenlockerrc) so the framebuffer stays painted for long runs; disables
  auto-updates; writes `gnome-initial-setup-done` and `/etc/adare-ready`. Best-effort
  pre-installs **adarevm + adarelib** via pipx (host-built wheels `--copy-in`, pipx
  bootstrapped through pip so it also works where there is no apt pipx, e.g. Ubuntu 18.04).
  **Fedora**: `--selinux-relabel` and `semanage permissive -a virt_qemu_ga_t` — Fedora
  confines `qemu-guest-agent` to the `virt_qemu_ga_t` SELinux domain (denied `mkdir /`,
  `mount`, …), which otherwise blocks the virtio-fs share ADARE mounts through the agent;
  making only that one domain permissive keeps the rest of the system enforcing.

- **`recompress.sh <disk.qcow2>`** — `qemu-img convert -c -o compression_type=zstd` in place
  (virt-customize leaves clusters uncompressed), with an integrity `qemu-img check`.

- **`ready_vm.sh <disk.qcow2> <family>`** — convenience: `provision_adare.sh` then `recompress.sh`.

## Why host/QMP for the test

Real `adare experiment run` on QEMU defaults to **host-side QMP GUI automation**
(`QEMUHostGUIExecutor`: `screendump` + `input-send-event`), which is display-server
agnostic — so the guest keeps its genuine default session (native Wayland included) and
we do **not** force X11. `adare vm test` gates the QEMU verdict on that same host/QMP path
(QGA-responsive + shared folder + host/QMP screenshot + host/QMP click); the in-guest
adarevm agent checks still run but are non-fatal on QEMU.

## Env

- `ADARE_REPO` (default `/home/miq/Documents/adare/adare`) — repo root used to build the
  adarevm/adarelib wheels for the pipx pre-install. If `uv`/the repo is unavailable the
  pipx step is skipped and agent mode falls back to `uv run` from the shared source.
