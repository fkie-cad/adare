# Creating VMs — OS profiles, recipes & arch — reference

## `adare vm create <OS_NAME>`

`adare vm create --help` prints the canonical target list; `adare os-profile list`
is the live source of truth. Common targets:

- **Ubuntu (autoinstall):** ubuntu2204, ubuntu2404, ubuntu2510, ubuntu2604
- **Debian (preseed):** debian12, debian13, kali
- **Fedora/RHEL (kickstart):** fedora41–44 (+ `kde` variants), rocky9, alma9
- **openSUSE (autoyast):** opensuseleap156, opensusetumbleweed
- **GUI manual install:** mint, popos, nixos, elementary
- **Windows (unattend):** windows10, windows11, windows11arm64

| Flag | Meaning |
| --- | --- |
| `--iso PATH` | OS ISO (**required for Windows**). |
| `--name TEXT` | VM name (auto-generated if unset). |
| `--disk-size TEXT` | Default 60G Linux / 80G Windows. |
| `--ram INTEGER` / `--cpus INTEGER` | Resources. |
| `--force` | Overwrite an existing VM disk image. |
| `--vm-dir PATH` | Disk image directory (default `~/.adare/state/vms/`). |
| `--setup [bare\|base\|full\|agent]` | What to install at create time. **Default `full`** = guest tools + Miniforge3/`pyadare` (`qemu-guest-agent` on Linux). `base` = guest tools only, `bare` = OS only, `agent` is **not implemented** (rejected). `--bare` is the deprecated alias for `--setup bare`. |
| `--env-name TEXT` | Environment file name (defaults to VM name). |
| `--interactive` | Boot after install for manual software installation. |
| `--arch [x86_64\|aarch64]` | Override the profile's architecture. |
| `--recipe / --no-recipe` | Declarative recipe (build on load) vs baked disk. **Default: recipe for Windows, baked for Linux.** |
| `--record` | GUI-auto: record a fresh install playbook even if one is cached. |
| `--relearn` | GUI-auto: discard the cached playbook, re-record from scratch. |
| `--display` | GUI-auto: show the VM window while the agent drives the installer. |
| `--template TEXT` | GUI-auto: explicit goal/spec template (default `gui_<distribution>`). |

### Install mechanisms by family

- **Unattended** (Ubuntu autoinstall / Debian preseed / Fedora kickstart / openSUSE
  autoyast / Windows unattend): fully hands-off from the answer file baked into the
  profile.
- **GUI-automated** (kubuntu, and any distro without an unattended path): the vision
  agent drives the graphical installer, records a playbook the first time, then
  replays it. Needs a working VLM (`adare vm gui-doctor`). `--record`/`--relearn`
  control the cached playbook; `--display` watches it drive.
- **Manual** (`--interactive`, mint/popos/nixos/elementary): boots the VM so a human
  installs the OS/software, then ADARE captures the result.

### Recipe vs baked

- **Baked** — a standalone disk image with the OS+agent already installed. Fast to
  boot, larger to store/share. Linux default.
- **Recipe** — a declarative descriptor built on `env load`. Smaller to keep in
  version control, rebuilt from source. Windows default (Windows disks are large and
  license-sensitive).

### The ADARE agent is not installed at create time

`vm create` bakes only the OS, guest tools and (at `--setup full`) a Python stack. The
`adarevm`/`adarelib` wheels install themselves on the first experiment or dev-session
start, and whether that uses the baked conda env or the system interpreter is
auto-detected at run time. There is no conda-vs-system-python decision to ask the user
about — Windows-ARM64 simply gets plain CPython 3.11 instead of Miniforge because no
Miniforge build exists for it.

## OS profiles

```sh
adare os-profile list                 # all profiles
adare os-profile show <name>          # one profile's detail
adare os-profile add <profile.yml>    # register a custom profile
adare os-profile remove <name>        # remove a custom profile
```

A profile pins the OS's arch, install method, answer-file template, and defaults. To
target an OS ADARE doesn't ship, author a profile YAML and `os-profile add` it, then
`vm create <that-name>`.

## Verifying a fresh VM

```sh
adare vm test <name>                            # registered VM (QEMU); platform auto-derived
adare vm test <file>.ova --platform linux       # OVA import test
adare vm test <name> --keep-vm                  # leave the test VM up for inspection
```

`vm test` prepares the VM (OVA import or a QEMU overlay off the base disk), mounts
shared dirs, starts adarevm, connects over WebSocket, takes a screenshot, does a test
click, and cleans up. The guest needs *either* the baked `pyadare` conda env (the
default, `--setup full`) *or* — on a non-conda guest with no prebuilt wheels under
`/adare/vm/wheels` — `uv` installed in the guest, because `install/install.sh` does not
build wheels and the editable fallback runs `uv sync` / `uv run adarevm`. Always test
before building environments.

## Architecture note

`--arch aarch64` targets Apple-Silicon / ARM hosts. ARM64 Windows is a special case
with several non-obvious traps (legacy-Setup boot override, resolution, TPM model,
boot flakiness) — see `win11-arm-gotchas.md` before building `windows11arm64`.
