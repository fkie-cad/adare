# gui-install — reproducible GUI installs without an LLM

A small, dependency-light harness for installing an OS by driving its **graphical
installer** deterministically — screenshot + keyboard/mouse over QEMU's QMP
monitor — so the same **playbook** always produces the same VM on any host with
QEMU + KVM, with **no vision model in the loop**.

This is the LLM-free counterpart to ADARE's `install_mode: gui-auto`
(`adare vm create`, which *records* a playbook with a vision agent). Here you
author the steps once and they replay forever.

## Why it works without image recognition

The one primitive that makes replay robust to host speed is **`wait_stable`**:
it repeatedly grabs the framebuffer (`screendump` → PPM) and waits until the
screen stops changing for N seconds. During an install the slideshow/progress
bar keep the frame changing, so it only "settles" when the installer is idle
(next screen, or the *Installation Complete* dialog). No pixel matching, no
model — just "has the screen gone quiet yet". Frames are diffed as raw bytes, so
the only hard requirement is Python's stdlib.

## Requirements

- `qemu-system-x86_64`, `qemu-img` (KVM strongly recommended — check `adare vm doctor`)
- Python 3 + `PyYAML`
- Optional: `pnmtopng` or Pillow (nicer PNG screenshots; otherwise `.ppm` is kept)

## Usage

```bash
./gui_install.py playbooks/ubuntu2004-desktop.yaml \
    --iso /path/ubuntu-20.04.6-desktop-amd64.iso \
    --vm-dir /vms --out /tmp/run2004
```

The runner will:
1. create a fresh qcow2 (`/vms/ubuntu2004-desktop.qcow2`),
2. boot the ISO headless (QMP socket + serial log),
3. replay the `install:` steps to click through the installer,
4. reboot from the installed disk (dropping the CD) and replay `verify:` (log in),
5. power the VM off cleanly.

Screenshots are written to the `--out` dir, one per checkpoint, so you can see
exactly what happened. Useful flags: `--force` (overwrite disk), `--ram/--cpus/
--disk-size` (override the playbook), `--keep-running` (leave it booted),
`--no-verify`.

## Provided playbooks (verified)

| Playbook | ISO | Result |
|---|---|---|
| `ubuntu2004-desktop.yaml` | `ubuntu-20.04.6-desktop-amd64.iso` | GNOME desktop, user `adare` |
| `ubuntu1804-desktop.yaml` | `ubuntu-18.04.5-desktop-amd64.iso` (old-releases) | GNOME desktop, user `adare` |

Both install the **genuine desktop edition** through ubiquity (not a server ISO
with a desktop added). Login: `adare` / `adare`.

## Playbook format

```yaml
name: my-os              # disk is <vm-dir>/<name>.qcow2
description: ...
credentials: "user 'adare' / password 'adare'"
vm:
  ram_mb: 8192
  cpus: 4
  disk_size: "60G"
  vga: qxl               # qxl works well; std has a tablet-scaling quirk
  firmware: bios         # bios | uefi (uefi auto-loads OVMF)
install:                 # steps run against the ISO-booted VM
  - {action: wait_stable, settle: 6, timeout: 300, shot: welcome}
  - {action: key, keys: [ret], note: "why"}
  - ...
reboot_from_disk: true   # stop, relaunch from disk, run verify:
verify:
  - {action: wait_stable, settle: 8, timeout: 240, shot: login}
  - ...
```

### Step actions

| action | params | effect |
|---|---|---|
| `key` | `keys: [ret]`, `shift: false`, `repeat: N` | send a key chord (QEMU qcodes: `ret tab spc esc end ctrl a` …) |
| `type` | `text: "adare"` | type a literal string |
| `tap` | `coords: [x, y, w, h]` | move the abs mouse to pixel (x,y) on a w×h frame and left-click |
| `wait` | `seconds: N` | fixed sleep |
| `wait_stable` | `settle`, `timeout`, `poll`, `min` | block until the screen is quiet for `settle`s (or timeout). `min` is a floor — won't return before `min`s, so it skips static early-boot/plymouth screens |
| `shot` | `name: foo` | save a screenshot now |

Any step may add `shot: name` to snapshot **after** it, and `note:` for logging.

## Adding a new install

1. Copy a playbook and set `name`, `vm`, and `credentials`.
2. Boot the ISO once and calibrate interactively:
   ```bash
   ./gui_install.py playbooks/new.yaml --iso new.iso --vm-dir /vms \
       --keep-running --no-verify        # boots + runs whatever steps you have
   # in another shell, poke the live VM and grab frames:
   QMP_SOCK=/tmp/gui-install/qmp.sock ./qmp_drive.py shot /tmp/s.png
   QMP_SOCK=/tmp/gui-install/qmp.sock ./qmp_drive.py key tab
   ```
3. Fill in the steps, using `wait_stable` between screens and a `shot` after each
   click so you can confirm focus landed where you expect.

### Caveats worth knowing

- **Keyboard-driven, so Tab counts are installer-version-specific.** Multi-widget
  screens (updates, installation-type, "who are you") depend on the exact widget
  layout; the saved screenshots are there to verify/adjust when adapting.
- **The timezone screen is the fragile one** — its city entry can trap keyboard
  focus. The playbooks `esc` (and `End`) to break out, then Tab to Continue, and
  accept the geoip default. If it stalls, check the `timezone` screenshot.
- **Video/mouse:** `qxl` maps the installer cleanly; with `-vga std` the usb-tablet
  has a 2× coordinate-scaling quirk (right half of the screen unreachable), which
  is why the playbooks navigate by keyboard rather than mouse clicks.
