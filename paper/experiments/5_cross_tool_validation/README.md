# Case study 5.5 — Cross-Tool Validation

> "Cross-tool validation is often time-consuming because comparable results require
> running platform-specific tools in different OS. We demonstrate how ADARE reduces this
> overhead by orchestrating three LNK parsers across Windows and Linux VMs: LECmd
> (Windows), lnkinfo (Linux), and ExifTool (Linux)."
> — ADARE paper, §5.5

Three sibling experiments, one per parser, over the same three LNK samples. Each runs in
its own OS, writes its parser's native output, asserts the per-sample outcome, and pulls
the artifacts to the host, where `provisioning/normalize_lnk_outputs.py` folds all three
into Table 1.

## Experiments

| Directory | Environment | Tool | Paper's Table 1 row |
|---|---|---|---|
| `lnk_lecmd_windows11/` | `win11arm64-fresh` | LECmd 2026.5.0 (paper: 1.5.1, see below) | L1 ✓ L2 ✓ L3 ✓ — Verbosity High |
| `lnk_exiftool_ubuntu2404/` | `ubuntu-2404` | ExifTool 12.76 | L1 ✓ L2 ✓ L3 ✓ — Verbosity Low |
| `lnk_lnkinfo_ubuntu2404/` | `ubuntu-2404` | lnkinfo 20181227 | L1 ✓ L2 **✗** L3 **✗** — Verbosity Medium |

All three are CLI tool-validation playbooks built from `command` actions, the same shape as
`3_tool_validation/pecmd`. Assertions are interleaved after each invocation rather than
batched at the end, which is the State Transition Testing idiom §5.3 describes: each
sample is a transition and the tool's output is checked at that point.

## The samples

`L1` is a structurally valid Windows shell link. `L2` and `L3` carry non-standard appended
data of differing sizes. The originals are malicious VirusTotal samples and are **not
committed** — `provisioning/README.md` has their Appendix-A hashes, retrieval
instructions, and a generator for benign stand-ins that reproduces the behaviour split.

Samples live in the **project's** `shared/data/` and are referenced as
`{{ adare_project_shared_data }}/L<n>.lnk`.

## Which assertion encodes which claim

The point of this case study, in ADARE's terms, is that Table 1's cells are *expectations*
rather than reported observations. Every cell has a test behind it:

| Paper claim | Test(s) | File |
|---|---|---|
| lnkinfo parses L1 | `l1_exit_code_zero`, `l1_local_path_value`, `l1_reports_working_directory`, `l1_reports_volume_label` | `lnk_lnkinfo_ubuntu2404` |
| **lnkinfo fails on L2/L3** | `l2_exit_code_nonzero`, `l3_exit_code_nonzero` | `lnk_lnkinfo_ubuntu2404` |
| …**specifically on a strict size constraint** | `l2_rejects_on_size_constraint`, `l3_rejects_on_size_constraint` (regex over the parser's stderr) | `lnk_lnkinfo_ubuntu2404` |
| …**recovering no link fields** | `l2_no_link_fields_recovered`, `l2_no_local_path_recovered`, and the L3 pair — all `expect_to_fail: true` | `lnk_lnkinfo_ubuntu2404` |
| ExifTool tolerates the appended data | `l2_exit_code_zero`, `l2_local_path`, `l2_working_directory`, and the L3 set | `lnk_exiftool_ubuntu2404` |
| …**silently, without saying so** | `l2_appended_data_not_reported`, `l3_appended_data_not_reported` (both `expect_to_fail: true`); `l1_no_overlay_warning` is the matching control | `lnk_exiftool_ubuntu2404` |
| LECmd tolerates the appended data | `l2_local_path`, `l2_working_directory`, and the L3 set | `lnk_lecmd_windows11` |
| Verbosity ordering | measured by `provisioning/normalize_lnk_outputs.py`, not by a test | — |
| Appendix A tool versions | `*_version_matches_paper` in all three | all three |

`expect_to_fail: true` (`adarelib/adarelib/testset/type.py:Test`) is what makes the ✗ cells
assertions instead of gaps: "lnkinfo recovered no working directory for L2" is expressed as
a content check that is *expected* to fail, so a future liblnk that starts recovering
fields turns the cell red instead of passing unnoticed.

## The `*_version_matches_paper` tests fail on purpose elsewhere

Each playbook pins its tool to the version in the paper's Appendix A. On any other image
that test goes red. That is intentional and it is load-bearing here: liblnk 20240423
changed lnkinfo's behaviour on L2/L3 from a hard failure to a recoverable `Is corrupted`
flag with exit 0, so on a newer image the two ✗ cells would silently become ✓. The version
pin makes that visible rather than letting the case study measure something else under the
same name. `provisioning/README.md` has the details.

Each playbook also carries a companion `*_version_recorded` test that only checks the
version *shape*, so a run always confirms the capture itself worked.

## Verification status

**First execution against live VMs: 2026-07-27** (aarch64, QEMU/HVF on macOS). Before this
date none of the three playbooks had ever run.

| Experiment | Environment | Result | Run ID |
|---|---|---|---|
| `lnk_lnkinfo_ubuntu2404` | `ubuntu-2404` | **green — 17/17 tests, 23/23 actions** | `01KYJ83KJSVPF1F9HYA0AGG554` |
| `lnk_exiftool_ubuntu2404` | `ubuntu-2404` | **green — 21/21 tests, 30/30 actions** | `01KYJ8JTZTGE44RS2V9D2FT0Z7` |
| `lnk_lecmd_windows11` | `win11arm64-fresh` | **green — 16/16 tests, 26/26 actions** (2026-07-28) | `01KYMG9Y8EW6GME08PRFNBA81X` |

Confirmed by those two runs:

- **Table 1's parse-success columns reproduce exactly**: `lnkinfo` ✓ ✗ ✗ and ExifTool
  ✓ ✓ ✓, with the L2/L3 rejections carrying liblnk's own
  `data block size exceeds file size` wording.
- **The Appendix-A versions really are what noble ships**: `lnkinfo_version_matches_paper`
  (20181227) and `exiftool_version_matches_paper` (12.76) both pass unmodified, so the
  version pins are satisfied rather than merely tolerated.
- `provisioning/normalize_lnk_outputs.py` folds both runs into Table 1 as designed.

Two corrections the runs forced:

- **ExifTool's tolerance is SILENT.** `provisioning/README.md` predicted
  `Warning: Truncated extra data` for L2/L3. On ExifTool 12.76 there is no `Warning` key
  and stderr is empty for *all three* samples, so ExifTool's output for L2/L3 is
  indistinguishable from clean L1. `l2_reports_appended_data` / `l3_reports_appended_data`
  were therefore re-baselined into `l*_appended_data_not_reported` with
  `expect_to_fail: true`. This strengthens rather than weakens the case study: ExifTool
  cannot detect the very anomaly lnkinfo rejects on.
- **The playbooks did not install their own tools.** Neither `exiftool` nor `lnkinfo` is in
  the base image; both playbooks now `apt-get install` the pinned packages
  (`libimage-exiftool-perl`, `liblnk-utils`) before the version capture.

### What `lnk_lecmd_windows11`'s first green run took (2026-07-28)

Four things, all measured in-guest on `win11arm64-fresh` (Windows 11 Pro 26200 ARM64,
.NET Framework 4.8.09221 / Release 533509):

1. **`LECmd.exe` must be invoked by absolute path.** A bare `LECmd.exe` does not resolve,
   because `CommandAction.tool` is declarative provenance and does not put the shared tools
   directory on the Windows guest's PATH.
2. **`LECmd.exe` cannot be *executed* from the shared-tools mount at all** — the cause of
   the empty `tool_version.txt` that failed `lecmd_version_recorded` on the first run. The
   mount is a symlink to a QEMU/Samba share (`C:\adare\project_shared` →
   `\\10.0.2.4\qemu\project_shared`) and `icacls` reports read-only ACLs on the file
   (`S-1-22-1-501:(R,W)`, `S-1-22-2-20:(R)`, `Everyone:(R)` — no `(X)`), so `CreateProcess`
   returns ERROR_ACCESS_DENIED:

   ```
   EX_TYPE=System.Management.Automation.ApplicationFailedException
   EX_MSG=Program 'LECmd.exe' failed to run: Access is denied
   EX_HRESULT=0x80131501
   FQID=NativeCommandFailed
   ```

   No process is created, so there is no stdout, no stderr and no `$LASTEXITCODE` — which is
   why the failure looked like "the tool runs and prints nothing". Reading from the share is
   fine; the identical bytes copied to a local directory run and exit 0 with a 2406-byte
   banner. **Both Windows playbooks now stage their parser to a local disk first and delete
   it again at the end of the run.** The same applies to `3_tool_validation/pecmd` (PECmd
   fails identically from the share) and to any future Windows tool-validation playbook.
3. **`--jsonf` does not exist in LECmd** (it does in PECmd). LECmd answers
   `'--jsonf' was not matched. Did you mean one of the following? --json` and falls back to
   its usage screen. `--json <dir>` auto-names the file `<yyyyMMddHHmmss>_LECmd_Output.json`,
   so each invocation writes into a scratch directory and the single produced file is renamed
   to the `lecmd_L<n>.json` the normalizer expects.
4. **Both host-unverifiable assumptions hold.** `--json` writes one JSON object on one line
   (so `jsonl.line_matches` is right), and LECmd exits 0 on all three samples — Table 1's
   LECmd row ✓ ✓ ✓ reproduces, with `LocalPath`, `WorkingDirectory` and `VolumeLabel` all
   recovered for L2/L3 as claimed. Caveat recorded in the playbook: LECmd also exits 0 on a
   *usage* error, so `l*_exit_code_zero` is necessary but not sufficient.

### `lecmd_version_matches_paper` was re-baselined 1.5.1 → 2026.5.0

**LECmd 1.5.1 is no longer distributed.** ericzimmermanstools.com serves only current builds,
there is no version archive, and the tools have since moved from semantic to date-based
versioning — the obtainable binary self-reports `LECmd version 2026.5.0` (FileVersion
`2026.5.0.0`, informational version `2026.5.0+def1fc2686af4684d06a889b1315f225187ac8f7`).
Under that scheme a `1.x` release cannot be produced any more, so a pin on 1.5.1 was not a
drift detector but a permanently red test that no obtainable binary could ever satisfy.

The pin was therefore re-baselined to the version this case study was actually measured
against, with the reasoning written into the playbook next to the test. Its purpose is
unchanged — it still goes red on any other build, so a future LECmd that changes its L2/L3
tolerance cannot silently change what Table 1 means. What does **not** reproduce is the
paper's exact binary: that is now recorded here as an unreproducible detail rather than
hidden behind a green test. Table 1's *behaviour* for LECmd does reproduce on 2026.5.0.

### Verified earlier on the authoring host

The full measurement table is in `provisioning/README.md`:

- The L1/L2/L3 behaviour split for `lnkinfo` 20181227 and ExifTool 12.76, including the
  exact stderr wording the regex assertions match.
- Every `standard.*`, `json.*` and `jsonl.*` assertion in all three playbooks, run against
  real (or, for LECmd, representative) parser output, each with a negative control to
  confirm the assertion can actually fail.
- The normalizer reproducing Table 1's parse-success columns.

Since resolved by the 2026-07-28 in-guest run:

- ~~**LECmd's output format and exit-code convention.**~~ Both measured and confirmed — see
  point 4 above. `--json` is newline-delimited JSON and LECmd exits 0 on success, so neither
  `l*_exit_code_zero` nor the `jsonl.line_matches` tests needed re-baselining.

Still not verified:

- **Table 1's Verbosity column against the benign stand-ins.** It does not reproduce, for
  a documented structural reason — see `provisioning/README.md`.

## Running it

```bash
# 1. samples into the project's shared data (once)
python3 provisioning/make_lnk_samples.py --output-dir <project>/shared/data

# 2. one experiment per OS
adare experiment run lnk_exiftool_ubuntu2404 --environment ubuntu-2404 --production
adare experiment run lnk_lnkinfo_ubuntu2404  --environment ubuntu-2404 --production
adare experiment run lnk_lecmd_windows11     --environment win11arm64-fresh --production

# 3. fold the three outputs into Table 1
python3 provisioning/normalize_lnk_outputs.py --artifacts <runs_root> \
    --csv table1.csv --markdown table1.md
```

Environment prerequisites (ExifTool and liblnk-utils in the Ubuntu image, `LECmd.exe` in
the Windows environment's shared tools) are listed in `provisioning/README.md`.
