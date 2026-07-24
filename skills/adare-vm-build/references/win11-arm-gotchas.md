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

## 2. TPM model breaks the aarch64 domain define

`libvirt_xml_builder.py:_add_tpm()` hardcodes `model='tpm-crb'` whenever `swtpm` is
on PATH. **aarch64 QEMU has no tpm-crb** (only `tpm-tis-device`), so libvirt refuses
to define the domain ("does not support TPM model tpm-crb") and the run dies in ~7s
(exit 255).

- **Workaround (no source change):** run adare with `/opt/homebrew` stripped from
  PATH so `swtpm` (only at `/opt/homebrew/bin`) isn't found — TPM is skipped and
  Win11 boots via the autounattend BypassTPMCheck hack. `qemu`/`qemu-img`/`virsh`
  remain at `/opt/local` (MacPorts).
- **Proper fix** would be to make `_add_tpm()` pick `tpm-tis` on aarch64.
- Note: the resolution fix (#3) *does* need a TPM device (`tpm-tis` aarch64) to boot
  the viogpu path — so the two interact; check current source before assuming.

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

**Mitigation (on branch `worktree-vm-boot-retry`, not yet merged to `dev` — verify
before relying on it):**
- A bounded **boot-retry loop** in `hypervisor/qemu/lifecycle.py`
  (`start_and_initialize_vm`): env knobs `ADARE_VM_BOOT_ATTEMPTS` (default 3) and
  `ADARE_VM_READY_TIMEOUT` (default 90s). Each retry force-destroys the domain,
  recreates a **fresh overlay from base** (independence → failure ≈ 0.45ⁿ), re-runs
  pre-boot file transfer; NVRAM preserved.
- Undefine with `VIR_DOMAIN_UNDEFINE_KEEP_NVRAM` (avoids "Cannot undefine domain with
  nvram" on retry).
- Provisioning bakes `bcdedit bootstatuspolicy ignoreallfailures` + `recoveryenabled
  No` to break the dirty-boot cycle (a boot policy, not files — respects the
  no-remnants rule).

Until that merges, wrap Windows runs in an undefine-stale-domain → run →
retry-on-no-artifact loop. A run that reaches the GUI takes ~11–15 min.

## 5. Snapshot / reset caveat

On this aarch64/UEFI env, dev-session **live snapshots fail** — `--restore` /
checkpoint restore is not usable. The reliable clean-reset path is `adare exp run` on
a **fresh overlay** per run (each run resets to the base snapshot), which doubles as
the reproducibility harness.

## Autopsy env drift (if building for the Autopsy experiments)

Older Autopsy GUIs drift from the 4.17 playbook: 4.10/4.11 have **no** Central
Repository first-run prompt (wait for the Welcome dialog directly), and Tools→Generate
Report misfires — click the toolbar "Generate Report" button instead. Autopsy 4.19.x
is the solr8 env and needs a firewall pre-auth for the Solr8 OpenJDK first-launch
modal.
