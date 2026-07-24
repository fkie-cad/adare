# Autopsy regression-testing VM provisioning

Builds fresh Windows 11 (ARM64) ADARE VMs with every Autopsy version used by the
regression playbooks in this directory (4.4.0 → 4.22.1, 24 versions), split across
**two** VMs at the Solr boundary.

## Why two VMs

At **Autopsy 4.18.0** the bundled Apache Solr jumped **4.10.3 → 8.6.3**. Solr 8
cannot read Solr 4 indexes, and the embedded Solr services collide on ports, so old
and new Autopsy do not cleanly coexist. We therefore isolate them:

| VM env name | Autopsy versions | Count | Solr | Version list |
|---|---|---|---|---|
| `win11-autopsy-solr4` | 4.4.0 … 4.17.0 | 16 | 4.10.3 | `versions_solr4.txt` |
| `win11-autopsy-solr8` | 4.18.0 … 4.22.1 | 8 | 8.6.3+ | `versions_solr8.txt` |

## Files

- `versions_solr4.txt`, `versions_solr8.txt` — one Autopsy version per line
  (`#` comments / blanks ignored).
- `Install-Autopsy.ps1` — in-guest provisioner: hardens the `adare` account for long
  life, then downloads + silently installs each version's official 64-bit MSI into its
  own `C:\Program Files\Autopsy-<v>` directory, and prints a pass/fail summary.

MSI URL pattern:
`https://github.com/sleuthkit/autopsy/releases/download/autopsy-<X.Y.Z>/autopsy-<X.Y.Z>-64bit.msi`

## Host setup

- **`brew install swtpm`** — Win11 requires a TPM 2.0. Without swtpm on the host the
  domain XML silently drops the `<tpm>` device (`libvirt_xml_builder.py:_add_tpm`,
  gated on `shutil.which('swtpm')`) and logs `swtpm not available`; the guest then
  boots TPM-less, which is a fragility on aarch64. Installing swtpm gives every
  Win11 build a real emulated TPM and clears that warning.

## Build runbook

> Long, partly interactive QEMU sessions. Autopsy is x64-only and runs on Win11 ARM64
> via the built-in Prism x64 emulation — **verify it works (step 2) before mass install.**

1. **Build the fresh base** (unattended install from the ARM64 ISO):
   ```
   adare vm create windows11arm64 --iso ~/Documents/ISO/Win11_25H2_English_Arm64_v2.iso
   ```
   Uses `adare/appdata/os-profiles/windows11arm64.yml` +
   `templates/autounattend_win11_arm64.xml`. Confirm it boots to the `adare` desktop
   with autologon.

2. **Gate — verify Autopsy runs under emulation.** Interactively extend the base once,
   install a single Autopsy (e.g. 4.21.0), launch it, confirm the GUI opens and a test
   case ingests. If it fails, stop and reconsider (see Risks).

3. **Build VM A (solr4)** via interactive extend:
   ```
   adare env extend windows11arm64 --name win11-autopsy-solr4 --interactive \
     --description "Windows 11 ARM64 + Autopsy 4.4.0-4.17.0 (Solr 4)" \
     --tag autopsy --tag forensics --tag solr4
   ```
   In the GUI session, transfer `Install-Autopsy.ps1` + `versions_solr4.txt` into the
   guest (mounted share / curl from ownCloud) and run:
   ```
   powershell -ExecutionPolicy Bypass -File Install-Autopsy.ps1 -VersionsFile versions_solr4.txt
   ```
   Shut down → ADARE flattens the overlay into a standalone disk + env YAML.

4. **Build VM B (solr8)** — same as step 3 with `--name win11-autopsy-solr8` and
   `versions_solr8.txt`.

5. **Register/load** both environments:
   ```
   adare environment load win11-autopsy-solr4
   adare environment load win11-autopsy-solr8
   ```

### Disk sizing
Base default is 80G. 16 installs (~1–2 GB each) + Windows (~25 GB) fits but is tight for
solr4 — bump `default_disk_size` / `--disk-size` when creating the base if needed
(qcow2 is thin-provisioned by default).

## Verification

1. VM boots and autologons as `adare`.
2. In-guest: `net accounts` shows *Maximum password age: Unlimited*;
   `Get-LocalUser adare | fl PasswordExpires` shows never.
3. `Install-Autopsy.ps1` summary reports all 16 (solr4) / 8 (solr8) installed;
   spot-check `C:\Program Files\` for `Autopsy-4.17.0` … `Autopsy-4.22.1`.
4. Launch one old + one new Autopsy per VM; version banner matches the directory.
5. `adare environment load ...` succeeds; run one matching
   `autopsy_*_webhistory` playbook to confirm the environment is wired up.

## Risks / caveats

- **x64-on-ARM64 emulation** is the biggest unknown — step 2 is a hard gate. If forensic
  accuracy under emulation is a concern for the regression results, building on an x86-64
  host is the alternative (no x86 Windows ISO exists on this machine → separate decision).
- **Very old MSIs (4.4.x, 2016-era)** bundle old JREs; the script logs per-version success
  so any failure is visible, not silent.
- **`net accounts /maxpwage:unlimited`** disables password expiry for all local accounts
  (fine for a lab VM). Win11 stays usable unactivated indefinitely (watermark only).
- **Run one Autopsy at a time within a VM** — embedded Solr binds a local port; concurrent
  instances conflict. Fine for the sequential regression playbooks.
- **Cold-boot flakiness (heavy solr4 image).** ADARE force-stops Windows guests on teardown
  (to avoid triggering updates), and a hard-killed Win11 guest intermittently boots into
  Startup Repair / "didn't shut down correctly" — the guest agent never appears and the run
  times out. Two mitigations are in place: (1) `Install-Autopsy.ps1` bakes
  `bcdedit bootstatuspolicy ignoreallfailures` + `recoveryenabled No` so a dirty boot no
  longer halts for input; (2) the QEMU lifecycle retries a hung cold boot on a fresh overlay
  with a short (~90 s) per-attempt readiness budget (`ADARE_VM_BOOT_ATTEMPTS`,
  `ADARE_VM_READY_TIMEOUT`). Measure the single-attempt success rate after (1)+swtpm to
  confirm the underlying hang is gone; the retry loop is the safety net either way.
