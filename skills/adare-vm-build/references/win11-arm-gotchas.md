# Windows 11 ARM64 gotchas — reference

Building/booting Win11-ARM64 QEMU VMs in ADARE (macOS host, aarch64) hits several
non-obvious traps. This is distilled from hard-won project experience — treat it as
authoritative and don't re-derive.

## 1. Legacy-Setup boot override (install won't honor the answer file)

Windows 11 **24H2/25H2** ship a redesigned "ConX" Setup front-end (`SetupPrep.exe`)
that **ignores `Autounattend.xml` on removable media** — the install stalls
interactively at the product-key screen and never partitions. The answer file is
correct; the new installer just doesn't read it.

**ADARE's fix (aarch64 only):** `create_legacy_boot_iso()`
(`hypervisor/qemu/vm_creator/iso_utils.py`) builds a small **El-Torito-bootable
override ISO** reproducing the stock boot chain but with `boot.wim` index 2 patched
with a `winpeshl.ini` that runs `setup.exe /legacy`. Attached as the first USB device
with `bootindex=0`, the firmware El-Torito-boots it → legacy Setup honors the answer
file. The untouched 7 GB Windows ISO stays attached to supply `install.wim`.

- **Required host tools** (checked by `adare vm doctor` / `prerequisites.py`): `7z`
  (read the UDF Windows ISO), `wimlib-imagex` (patch boot.wim), `xorriso` (build the
  El-Torito ISO). macOS (brew) + ARM64 Linux (apt/dnf). **`hdiutil` cannot make an
  El-Torito record** → it produced a "stuck at UEFI shell" dead end; always build
  bootable ISOs with xorriso.
- **The Windows Boot Manager needs a display/GOP.** A `-display none` headless boot
  times out at `bootmgr` even for the stock ISO. Validate boots with a real display
  backend (cocoa/gtk), not headless. (Guest-agent `guest-exec` works headless once
  the OS is up.)
- **Not covered:** x86_64 Win11 24H2/25H2 hits the same ConX issue via a different
  (floppy answer-file) flow and is not handled by this override.

## 2. TPM model on aarch64 — FIXED, don't re-apply the old workaround

**Historic bug:** `_add_tpm()` hardcoded `model='tpm-crb'` whenever `swtpm` was on
PATH. **aarch64 QEMU has no tpm-crb** (only `tpm-tis-device`), so libvirt refused to
define the domain ("does not support TPM model tpm-crb") and the run died in ~7s
(exit 255).

**Now fixed in source:** `libvirt_xml_builder.py` picks the model per architecture —
`tpm_model = 'tpm-tis' if self._is_aarch64 else 'tpm-crb'`. Install `swtpm` and let
it be found.

- **Do NOT apply the old PATH workaround** (stripping `/opt/homebrew` so `swtpm` is
  not found). It now costs you a real TPM for no reason, and the resolution fix (#3)
  *needs* a `tpm-tis` device to boot the viogpu path.

## 3. Resolution: request 1920×1080, expect an active capped mode

virtio-gpu on Win11-ARM64 caps effective resolution. The reliable, live-verified way
to force resolution **headless (no VNC, no SPICE)** is a single guest-side
`ChangeDisplaySettings(width,height)` GDI P/Invoke **in the interactive console
session (session 1)**, via `vm.run_command(..., run_as_user=True)` (schtasks `/IT`).
Result seen: 1024×768 → 1920×1080, guest desktop and host QMP scanout both active, no
reboot. Needs the `virtio-gpu-pci,edid=on,xres,yres` device (binds viogpudo) + the
`tpm-tis` aarch64 boot fix.

**Disproven — do not retry:**
- Boot-time EDID alone; `PersistentDispMode*`/`FlexResolution`/vgpusrv + reboot;
  host `-display dbus` + gdbus (MacPorts qemu has no dbus backend); SPICE-vdagent
  `requestResolution` (Windows path needs a QXL WDDM escape; ADARE guests have no
  QXL driver → `STATUS_INVALID_DEVICE_REQUEST`); VNC SetDesktopSize (forbidden).
- On the **default** path (ramfb + virtio-gpu-device MMIO) viogpu isn't even bound —
  Windows shows the Microsoft Basic Display Driver at 800×600. Only the **PCI** GPU
  with advertised EDID gives a working lever.

**Practical caveat:** setting the playbook `resolution` to the *exact cap*
(`1024x768`) makes the mode-set leave the display "not active" (black framebuffer, CV
runs blind). Setting `1920x1080` fails the mode-set *gracefully* and leaves the
display **active** at the capped 1024×768. So **over-request** (1920×1080), don't
request the cap exactly.

**Measurement gotcha:** QGA guest-exec runs as SYSTEM in session 0 — its
`Screen`/`EnumDisplaySettings` report session-0 metrics, not the console desktop.
Measure via a `schtasks /IT` task running as the interactive user, not session-0 QGA.

## 4. ~45–50% cold-boot hang

Heavy Windows images intermittently fail with "VM did not become ready in time":
successes reach QGA in ~21–37s; failures dead-wait the full timeout (guest never
connects). Leading cause: a dirty-boot Startup Repair after the hard power-off used
on Windows teardown.

**Mitigations, both now in source — no manual wrapper needed:**
- A bounded **boot-retry loop** in `hypervisor/qemu/lifecycle.py`
  (`start_and_initialize_vm`), **merged**: env knobs `ADARE_VM_BOOT_ATTEMPTS`
  (default 3) and `ADARE_VM_READY_TIMEOUT` (default 90s). Each retry force-destroys
  the domain, recreates a **fresh overlay from base** (independence → failure ≈
  0.45ⁿ), re-runs pre-boot file transfer; NVRAM preserved via
  `VIR_DOMAIN_UNDEFINE_KEEP_NVRAM` (avoids "Cannot undefine domain with nvram").
- Bake `bcdedit bootstatuspolicy ignoreallfailures` + `recoveryenabled No` into the
  image to break the dirty-boot cycle (a boot policy, not files — respects the
  no-remnants rule). In a recipe this is a `recipe.provision` step with
  **`shell: cmd`** — PowerShell parses `{default}` as a script block. Confirmed
  necessary: a freshly built base reports `recoveryenabled Yes`.

A run that reaches the GUI takes ~11–15 min.

## 5. Snapshot / reset caveat

On this aarch64/UEFI env, dev-session **live snapshots fail** — `--restore` /
checkpoint restore is not usable. The reliable clean-reset path is `adare exp run` on
a **fresh overlay** per run (each run resets to the base snapshot), which doubles as
the reproducibility harness.

## 6. The canonical ARM64 ISO

Microsoft installer media cannot lawfully be rehosted, so `windows11arm64` recipes use
the consumer-supplied (BYO) ISO form: `recipe.iso_name` + `recipe.iso_sha256` instead
of a URL. The verified file:

```
iso_name:   Win11_25H2_English_Arm64_v2.iso
iso_sha256: 638aa2c88e94385b00f4f178d071e3df0b7d9e335577a83bd533b7f2eb65adf0
source:     https://www.microsoft.com/software-download/windows11
            → "Windows 11 Arm64", English (International)
```

Put it in `~/.adare/isos/`, or pass `adare env load <env>.yml --iso <path>`.
The same values are in `appdata/os-profiles/windows11arm64.yml` as `iso_notes`, so a
consumer whose recipe omits its own notes still gets the pointer.

## 7. QGA on a built Win11-ARM64 disk — measured, works

Build-time provisioning talks to the **QEMU** guest agent (not adarevm, whose wheels
only install on the first experiment/dev-session start). Measured on the
`windows11arm64` recipe base disk, booting an overlay via
`build_post_install_qemu_cmd`:

| Measurement | Result |
| --- | --- |
| `qga_wait_ready` after boot | **2–3 s** |
| `QEMU-GA` service state | Running |
| Agent identity | `nt authority\system` |
| `virtio-serial` + `virtserialport` on plain `virt,accel=hvf` | enumerate fine — the `highmem-mmio/ecam/redists=off` properties `_run_qemu_install_phase` needs are **not** required for a booted guest |
| Exit-code fidelity (`exit 3010`) | propagates verbatim |
| Clean ACPI shutdown | 3 s cold, 31 s after use |

**SYSTEM-context paths — these bite.** The agent is SYSTEM, so:

| Variable | Value under QGA | NOT |
| --- | --- | --- |
| `$env:TEMP` | `C:\Windows\TEMP` | `C:\Users\adare\AppData\Local\Temp` |
| `$env:USERPROFILE` | `C:\Windows\system32\config\systemprofile` | `C:\Users\adare` |
| `$env:ProgramFiles` | `C:\Program Files` | (correct as-is) |

So `log_files:` entries must be **absolute** paths under `C:\Windows\Temp`, not
`%TEMP%`-derived ones — otherwise the host pulls from a path the guest never wrote.

Also confirmed present/working in the guest: `curl.exe`
(`C:\Windows\system32\curl.exe`, reaches GitHub releases over QEMU user-mode NAT),
and `bcdedit /enum {default}` / `bcdedit /set {default} ...` via cmd.

**QGA cannot reliably spawn `cmd.exe` directly.** Handing the agent
`['cmd.exe', '/c', <script>]` fails for *some* scripts with `Failed to execute
helper program (Permission denied)` — a glib spawn error raised before cmd ever
parses the text. Measured, deterministic:

| Script | Direct `cmd.exe` spawn |
| --- | --- |
| `echo hi` / `echo hi && echo there` / `echo {default}` | OK |
| `echo <1000 chars>` | OK — so it is **not** length |
| `bcdedit /enum {default} && bcdedit /enum {default}` | OK |
| `bcdedit /set A && echo second` / `echo first && bcdedit /set B` | OK |
| `bcdedit /set {default} bootstatuspolicy ignoreallfailures && bcdedit /set {default} recoveryenabled No` | **FAILS 2/2** |

Neither length, nor `&&`, nor the braces. ADARE's fix (`qga_utils._build_exec_args`)
is to never hand glib a cmd argument string at all: `shell: cmd` is spawned as
`powershell.exe -EncodedCommand …`, and PowerShell spawns cmd with the script
carried base64-encoded (so nothing is quoted at any layer). Verified 3/3 on the
previously-failing command, with exit codes 0/1/3010, quotes, `%`, `^`, and `cwd`
all preserved. **Do not "simplify" that back to a direct `cmd.exe` spawn.**

**Boot hardening: verified applied, and the values are capitalised.** After
`bcdedit /set {default} bootstatuspolicy ignoreallfailures` +
`... recoveryenabled No`, `bcdedit /enum {default} /v` shows
`bootstatuspolicy        IgnoreAllFailures` and `recoveryenabled         No`
(a fresh base shows `recoveryenabled Yes` and no bootstatuspolicy line at all). A
`verify` must therefore be case-insensitive:

```
bcdedit /enum {default} /v | findstr /r /i /c:"recoveryenabled  *No"
```

Note `/v` — the non-verbose enum output is not a reliable place to match on.

Note `$env:PROCESSOR_ARCHITECTURE` reports **AMD64** — the shipped guest agent is the
x64 build running under Prism, which is exactly what makes x64 MSIs installable. It
does not change `ProgramFiles`.

## Autopsy env drift (if building for the Autopsy experiments)

Older Autopsy GUIs drift from the 4.17 playbook: 4.10/4.11 have **no** Central
Repository first-run prompt (wait for the Welcome dialog directly), and Tools→Generate
Report misfires — click the toolbar "Generate Report" button instead. Autopsy 4.19.x
is the solr8 env and needs a firewall pre-auth for the Solr8 OpenJDK first-launch
modal.
