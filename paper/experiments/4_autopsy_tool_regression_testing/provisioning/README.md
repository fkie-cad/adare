# Autopsy regression-testing VM provisioning

Builds fresh Windows 11 (ARM64) ADARE VMs with every Autopsy version used by the
regression playbooks in this directory (4.4.0 → 4.22.1, 24 versions), split across
**two** VMs at the Solr boundary.

Each VM is declared by a **recipe environment** — a ~110-line YAML naming its build
inputs — instead of being shipped as a baked disk image. That replaces ~97 GB of
undocumented, unshippable disk with two text files any consumer can rebuild from a
Windows ISO they legally own.

## Why two VMs

At **Autopsy 4.18.0** the bundled Apache Solr jumped **4.10.3 → 8.6.3**. Solr 8
cannot read Solr 4 indexes, and the embedded Solr services collide on ports, so old
and new Autopsy do not cleanly coexist. We therefore isolate them:

| VM env name | Autopsy versions | Count | Solr | Version list |
|---|---|---|---|---|
| `win11-autopsy-solr4` | 4.4.0 … 4.17.0 | 16 | 4.10.3 | `versions_solr4.txt` |
| `win11-autopsy-solr8` | 4.18.0 … 4.22.1 | 8 | 8.6.3+ | `versions_solr8.txt` |

## Files

- **`win11-autopsy-solr4.yml`, `win11-autopsy-solr8.yml`** — the two recipe
  environments. Each declares the OS profile, the consumer-supplied ISO + its sha256,
  build params, and a `recipe.provision` block that downloads and installs every
  Autopsy version in its group at **build time**, once, via the QEMU guest agent.
  These are the artifacts to publish and cite.
- `versions_solr4.txt`, `versions_solr8.txt` — one Autopsy version per line.
  Superseded by the `for_each:` lists inside the two YAMLs; kept as the
  human-readable statement of which versions belong to which Solr group.
- `Install-Autopsy.ps1` — the **superseded** in-guest provisioner, kept for
  provenance: it is what the original baked disks were built with. Do not use it for
  new builds. Two things make it unsuitable as the shipped mechanism: it must be
  transferred into the guest by hand during an interactive session (so the build is
  not reproducible from text alone), and it reports failures only in a summary at the
  end, continuing past a failed version. A recipe hash must describe a disk where
  *all* versions are present, so the recipe aborts on first failure instead.

MSI URL pattern:
`https://github.com/sleuthkit/autopsy/releases/download/autopsy-<X.Y.Z>/autopsy-<X.Y.Z>-64bit.msi`

## Host setup

- **`brew install swtpm`** — Win11 requires a TPM 2.0. Without swtpm on the host the
  domain XML silently drops the `<tpm>` device (`libvirt_xml_builder.py:_add_tpm`,
  gated on `shutil.which('swtpm')`) and logs `swtpm not available`; the guest then
  boots TPM-less, which is a fragility on aarch64. Installing swtpm gives every
  Win11 build a real emulated TPM and clears that warning.

## Build runbook

> Long QEMU sessions, but fully unattended. Autopsy is x64-only and runs on Win11
> ARM64 via the built-in Prism x64 emulation — **verify it works (step 2) before the
> mass install.**

1. **Put the Windows ISO where ADARE can find it.** The recipes name the file and its
   sha256 rather than a URL, because Microsoft installer media cannot lawfully be
   rehosted:
   ```
   cp Win11_25H2_English_Arm64_v2.iso ~/.adare/isos/
   shasum -a 256 ~/.adare/isos/Win11_25H2_English_Arm64_v2.iso
   # must be 638aa2c88e94385b00f4f178d071e3df0b7d9e335577a83bd533b7f2eb65adf0
   ```
   `$ADARE_ISO_DIR` or `--iso /path/to/it` work equally well.

2. **Gate — verify Autopsy runs under emulation.** Build a one-version variant first
   by copying `win11-autopsy-solr4.yml` and cutting `for_each:` down to
   `["4.21.0"]`. Launch Autopsy in the resulting VM and confirm the GUI opens and a
   test case ingests. If it fails, stop and reconsider (see Risks).

3. **Build VM A (solr4)** — one command, no interaction:
   ```
   adare env load win11-autopsy-solr4.yml
   ```
   ADARE installs Windows once (Stage 1, ~2 h), caches that base disk, then runs the
   49 provisioning commands against a throwaway overlay of it through the QEMU guest
   agent and flattens the result (Stage 2). Every command's exit code, wall time,
   stdout and stderr land in `~/.adare/qemu/build-logs/provision-<hash>.log` — the
   provenance record to attach to the paper artifact.

4. **Build VM B (solr8)**:
   ```
   adare env load win11-autopsy-solr8.yml
   ```
   Stage 1 is declared identically, so this is a **base-cache hit**: no second Windows
   install, and only solr8's own provisioning time is paid. Look for
   `Recipe base cache hit — reusing ...` in the output.

### Retrying a failed build

Provisioning aborts on the first failed step, and no environment is registered — a
recipe hash must never describe a disk missing some of its versions. The base disk is
cached, so the retry is cheap:

```
adare env load win11-autopsy-solr4.yml --reprovision   # reuse base, redo provisioning
adare env load win11-autopsy-solr4.yml --force          # rebuild Windows too
ADARE_KEEP_FAILED_PROVISION=1 adare env load ... --reprovision   # keep the overlay
```

An interrupted Stage 1 is safe to just re-run: the base disk is published by an
atomic rename, so a killed install leaves a `.partial` file rather than an empty disk
that later builds would mistake for a cached base.

Step-level resume is deliberately not offered: a half-installed MSI is not a clean
resume point, and pretending otherwise yields disks whose contents do not match their
hash. If a single version is at fault, bisect the `for_each` list — and if it genuinely
cannot be installed, remove it, which correctly produces a new hash and a truthfully
described environment.

### Disk sizing
The recipes declare `disk_size: 160G` (vs. 80G default). 16 installs (~1–2 GB each) +
Windows (~25 GB) does fit in 80G but leaves no headroom; qcow2 is thin-provisioned, so
the larger virtual size costs nothing until used. Note the params must stay **identical
across the two recipes** or their base hashes fork and the shared Windows install is
built twice. Peak host disk during Stage 2 is roughly base + overlay + flattened
output; `env load` preflights free space before starting.

## Verification

1. VM boots and autologons as `adare`.
2. In-guest: `net accounts` shows *Maximum password age: Unlimited*;
   `Get-LocalUser adare | fl PasswordExpires` shows never.
3. The build completed at all — each install step carries a
   `verify: Test-Path "C:\Program Files\Autopsy-<v>"`, so a registered environment
   already proves all 16 (solr4) / 8 (solr8) directories exist. Spot-check
   `C:\Program Files\` anyway for `Autopsy-4.17.0` … `Autopsy-4.22.1`.
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
- **MSI URLs are deliberately not integrity-pinned.** This is a design decision, not an
  open gap: `iso_sha256` is the integrity boundary of a recipe, and provision commands are
  not extended with a `sha256:` of their own.

  The rationale: the ISO is the one input a *consumer* supplies from their own copy, so its
  digest is what makes two independent builds comparable. The MSI URLs point at
  upstream-controlled release assets. Pinning them would move the trust anchor from "the OS
  install is reproducible" to "upstream never re-cuts a tag", which is not a property this
  project can enforce — and it would make every legitimate upstream re-release look like
  tampering, requiring a recipe edit (and therefore a new recipe hash, and therefore a
  rebuild) to fix.

  The accepted consequence: a retagged GitHub release yields a different disk under the
  same recipe hash. What guards against that in practice is that the recipe records the
  exact version list, each install asserts its own target directory exists
  (`verify: Test-Path "C:\Program Files\Autopsy-<v>"`), and the per-version MSI log is
  pulled to the host on failure — so a substituted installer shows up as a changed
  artifact set, not as a silent pass. Reproducing a *specific* historical build therefore
  depends on upstream tag stability; the published disk hash is the durable record.
- **Cold-boot flakiness (heavy solr4 image).** ADARE force-stops Windows guests on teardown
  (to avoid triggering updates), and a hard-killed Win11 guest intermittently boots into
  Startup Repair / "didn't shut down correctly" — the guest agent never appears and the run
  times out. Two mitigations are in place: (1) the `boot-hardening` provision step bakes
  `bcdedit bootstatuspolicy ignoreallfailures` + `recoveryenabled No` so a dirty boot no
  longer halts for input (confirmed necessary: a fresh base reports
  `recoveryenabled Yes`); (2) the QEMU lifecycle retries a hung cold boot on a fresh overlay
  with a short (~90 s) per-attempt readiness budget (`ADARE_VM_BOOT_ATTEMPTS`,
  `ADARE_VM_READY_TIMEOUT`). Measure the single-attempt success rate after (1)+swtpm to
  confirm the underlying hang is gone; the retry loop is the safety net either way.
