---
name: adare-vm-build
description: "Create or verify a new base VM, environment, or disk image, and diagnose VM tooling. Trigger when the user wants to build a VM from an OS/ISO, extend an env with more software, verify or publish an environment for sharing, prune/snapshot/inspect VM images, manage OS profiles, or run VM/GUI preflight doctors. Not this → running an experiment on an existing environment (adare-experiment); interactively driving a running VM (adare-devvm)."
---

# ADARE VM & environment building

This skill builds the substrate experiments run on: **base VMs** (an OS installed
from scratch), **environments** (a VM + declarative post-setup software), and
**published disk images** (URL + sha256 for sharing). It also covers the preflight
doctors and image housekeeping.

Pure `adare` CLI + Bash. Auto-loads as a skill in **Claude Code**; portable to any
agent with a shell (on **OpenCode** see `docs/mcp-clients.md` for skill setup).
Building a VM is long-running and host-tool-heavy — always start with the doctors. Keep SKILL.md's
path in view; the deep flag/recipe detail and the hard-won Windows-ARM64
troubleshooting live in `references/*.md`.

## Prerequisites

- **`adare vm doctor`** — checks the host build tools (qemu-system/qemu-img, OVMF
  firmware, swtpm, libvirt Python binding, and on Apple Silicon the wimlib/7z/xorriso
  trio for the Win11-ARM64 legacy-boot workaround). Detect-and-report only; run it
  first and fix any gaps before creating a VM.
- **`adare vm gui-doctor`** — only if you'll GUI-automate the install (`vm create`
  for a manual-install distro, or `env extend --interactive`): confirms the VLM
  endpoint is reachable and detects its coordinate convention.

## 1. Preflight

```sh
adare vm doctor                        # host QEMU/OVMF/swtpm/wimlib availability
adare vm gui-doctor                    # VLM preflight (only for GUI-automated installs)
adare os-profile list                  # available OS targets
adare os-profile show <name>           # one profile's detail
adare os-profile add <profile.yml>     # register a custom OS profile
```

## 2. Create a base VM

```sh
adare vm create <os>                                  # e.g. ubuntu2404, debian12, windows11arm64
adare vm create <os> --iso /path/to/os.iso            # ISO required for Windows
adare vm create <os> --interactive                    # boot after install for manual software setup
adare vm create <os> --recipe                         # declarative recipe (build on load), not a baked disk
adare vm test <vm-or-ova> [--platform linux|windows]  # verify ADARE compatibility
```

`adare vm create --help` lists all OS targets (Ubuntu/Debian/Fedora/openSUSE via
autoinstall/preseed/kickstart/autoyast; GUI-manual for mint/popos/nixos; Windows via
unattend). Defaults: **recipe** for Windows, **baked** for Linux; `--arch
[x86_64|aarch64]` overrides the profile arch. GUI-automated installs add `--record`/
`--relearn`/`--display`/`--template`. Full matrix in `references/create-recipes.md`.
**Windows-ARM64 has real traps — read `references/win11-arm-gotchas.md` first.**

Always `adare vm test <name>` a fresh VM before building environments on it.

## 3. Build an environment

An environment layers post-setup software on a base disk.

```sh
adare env create <name> [--with-vm /path/to.ova]                 # new env, optionally load a VM
adare env extend <source> -n <new> --install "name:command" …    # declarative: superset, shares base disk
adare env extend <source> -n <new> --interactive [--console]     # GUI install by hand, then flatten
adare env verify <name>                                          # run the built-in verify_vm experiment
```

- **Declarative `extend`** (default) adds installs on top of the source's; the new
  env is a strict superset sharing the same underlying disk — **no new VM created**.
- **`--interactive`** (QEMU only) boots a throwaway overlay in a GUI window so you
  install by hand; on shutdown you choose to store (flatten into a new standalone
  disk + register a new base VM/env) or discard. `--console` also records typed
  shell commands as reproducible installs.
- **`env verify`** runs the shipped `verify_vm` experiment against the env — do this
  before relying on or publishing it. Details in `references/env-extend-publish.md`.

## 4. Publish an environment for sharing

```sh
adare env publish-prepare <name> --vm-url <https-url> [--vm-format qcow2] [--verify-url]
```

Rewrites the env descriptor from a local disk to a hosted **URL + required sha256**
(any host, incl. owncloud/Nextcloud share links). Consumers re-verify the hash after
download. `--verify-url` downloads the URL and confirms the bytes hash-match the
local disk (catches a wrong/HTML share link). Publish = **YAML + external disk URL +
required sha256** — the sha256 is mandatory, enforced at multiple layers.

## 5. Manage images

```sh
adare vm list                          # all VMs (aliases: l)
adare vm info <vm-id>                   # detail for one VM
adare vm usage                         # instance usage statistics
adare vm snapshot list                 # snapshots (snapshot remove <…> to delete one)
adare vm prune [--force] [--sockets]   # reclaim orphaned base disks (dry-run by default)
adare vm remove --id <ulid> | --stopped | --all --force | --env <ulid> --force
adare vm reset --force                 # reset ALL VMs (destructive)
```

`vm prune` is the GC for orphaned `<name>-base.qcow2`/`-nvram.fd` debris (dry-run
until `--force`). `vm remove`/`vm reset` are destructive — see
`references/diagnostics.md`.

## 6. Windows icons

```sh
adare icons list [--os-key <key>]                         # every registry term + resolver spec
adare icons dump-all --host <adarevm-host> [--os-key …]   # resolve every term on a connected target
```

Inspects/extracts the Windows icon library used for CV grounding on Windows guests.

## Guardrails

- **Run the doctors first.** `vm create` depends on host tools; `vm doctor` tells you
  what's missing before a long build fails midway.
- **Forensic integrity / minimal guest.** Install only what the environment needs;
  never leave logs, markers, or verification scripts inside the VM — get information
  from the host side instead (no-VM-remnants rule).
- **Publish requires sha256.** `env publish-prepare` writes a mandatory `vm_sha256`;
  don't hand out a descriptor without it. Use `--verify-url` when the disk is hosted.
- **Destructive housekeeping** (`vm remove --all --force`, `vm reset --force`, `vm
  prune --force`) can wipe VMs/disks — confirm scope first; `prune` and `remove` have
  dry-run/preview behavior, use it.
- **One live VM at a time** still applies to any `--interactive`/GUI-automated build
  step (it boots a real VM); don't overlap with a `dev` session or `exp run`.
