# Cross-tool validation — sample provisioning

Everything the three §5.5 playbooks need that is *not* a playbook: the LNK samples and
the host-side normalizer that turns three heterogeneous parser outputs into Table 1.

## The original samples are not committed

§5.5 used three malicious LNK files obtained from VirusTotal. Their SHA-256 hashes, as
recorded in the paper's Appendix A:

| Sample | SHA-256 |
|---|---|
| LNK-1 (L1) | `acbc775087da23725c3d783311d5f5083c93658de392c17994a9151447ac2b63` |
| LNK-2 (L2) | `1b75f70c226c9ada8e79c3fdd987277b0199928800c51e5a1e55ff01246701db` |
| LNK-3 (L3) | `1b598c7c35f00d2c940dfd3745bd9e5d036df781d391b8f3603a2969c666761b` |

They are deliberately absent from this repository. Redistributing malware samples is not
something a public research repository should do, and it is the same constraint the paper
argues in §6 about evidence images that cannot be shared for licensing or legal reasons.

**To reproduce with the original samples**, retrieve each hash from VirusTotal
(`https://www.virustotal.com/gui/file/<sha256>`; downloading requires a VT Intelligence
or Enterprise account, community accounts cannot download) and place the files as
`L1.lnk`, `L2.lnk`, `L3.lnk` in the ADARE **project's** `shared/data/` directory. The
playbooks reference them as `{{ adare_project_shared_data }}/L<n>.lnk` — the same
mechanism `4_autopsy_tool_regression_testing` uses for `2020JimmyWilson.E01`.

## `make_lnk_samples.py` — benign stand-ins

So the case study is runnable without the malware, this generator synthesises three
files that reproduce the one property Table 1 turns on.

```bash
python3 make_lnk_samples.py --output-dir <project>/shared/data
```

No dependencies beyond the standard library. Output is deterministic — the samples use a
fixed timestamp, so regenerating them is byte-for-byte stable:

| File | Size | SHA-256 |
|---|--:|---|
| `L1.lnk` | 447 | `bc773985c7bd18f5354b04b27f14fd7785a4159f5268027f4e37bb6ca5c3f029` |
| `L2.lnk` | 955 | `7cb250232712fc1279fde632238d3ef30f8d8691aacdcaf88690a58bf3a101c7` |
| `L3.lnk` | 4539 | `074b33c4adc79229dffae668d11cb18add022b0a5ab6a9760eb73c60558eaa82` |

Structure (MS-SHLLINK): a ShellLinkHeader, a LinkInfo with VolumeID + LocalBasePath, the
NAME_STRING / RELATIVE_PATH / WORKING_DIR strings, and one real TrackerDataBlock. No
LinkTargetIDList — it is optional per the specification and all three parsers accept its
absence, which keeps the generator free of hand-rolled shell item IDs.

**Where the appended bytes go is the whole trick.** L1 closes its ExtraData list with a
TerminalBlock. L2/L3 omit it, so their appended bytes land where liblnk expects the *next*
ExtraData block; liblnk reads their first four bytes as a block size (`b"ADAR"`
little-endian = `0x52414441`) and rejects the file. Putting the appended data *behind* a
terminal block instead makes all three parsers succeed and the case study asserts nothing
— that variant was built, measured, and discarded.

### Measured behaviour, and it matches the paper

Verified on the authoring host against real tool builds:

| Sample | `lnkinfo` 20181227 | ExifTool 12.76 |
|---|---|---|
| L1 | exit 0, full field dump | exit 0, no warning |
| L2 | **exit 1**, `liblnk_io_handle_read_data_blocks: data block size exceeds file size.` | exit 0, `Warning: Truncated extra data` |
| L3 | **exit 1**, same message | exit 0, `Warning: Truncated extra data` |

That is Table 1's `lnkinfo ✓ ✗ ✗` and `ExifTool ✓ ✓ ✓` reproduced exactly, and
"failed due to strict size constraints" is liblnk's own wording for it. Because L1 carries
a genuine TrackerDataBlock, it also proves liblnk's block parser works — so the L2/L3
rejection isolates the malformed block size rather than block handling in general.

**LECmd could not be measured** (Windows/.NET only; the authoring host is macOS). Its row
rests on the paper plus the shape of the sibling tool PECmd. See the "unverified" note at
the top of `../lnk_lecmd_windows11/playbook.yml`.

### liblnk version caveat — this matters

Ubuntu 24.04 (`noble`) ships **liblnk 20181227**, which is exactly the version the paper's
Appendix A pins, so the `ubuntu24043` environment reproduces §5.5 as written.

**liblnk 20240423 behaves differently**: it recovers from the same malformed block, prints
`Is corrupted`, dumps all the link fields anyway, and exits **0**. On that version the two
✗ cells silently become ✓. Ubuntu ships 20240423 from `questing`/`plucky` onward.

This is why `lnk_lnkinfo_ubuntu2404/playbook.yml` contains a
`lnkinfo_version_matches_paper` test pinned to `20181227`: on a newer image it fails
loudly instead of letting the case study quietly measure something else. That is the
§5.2 argument applied to §5.5's own tooling.

## `normalize_lnk_outputs.py` — Table 1, automated

§5.5 says results were "manually normalized" and §7 lists automating it as an open item.
This script closes that gap. It reads the artifacts the three playbooks pull to the host,
recognises each tool by its artifact filenames, and emits Table 1 as Markdown and CSV.

```bash
# after running the three experiments
python3 normalize_lnk_outputs.py --artifacts <run_dir> [<run_dir> ...] \
    --csv table1.csv --markdown table1.md
```

Directories are searched recursively, so pointing it at a runs root works. Parse success
is decided from evidence rather than the exit code alone — a tool counts as having parsed
a sample only if it exited zero **and** recovered the expected local path. That is
deliberate: liblnk 20240423 exits zero while recovering nothing useful from a rejected
block, and a naive exit-code reading would score it ✓ and contradict the paper.

`--strict` exits non-zero when the measured table diverges from Table 1, which makes the
normalizer usable as a regression gate. Without it, divergences are reported on stderr and
the exit code stays 0.

### Known divergence: the Verbosity column

Run against the **benign stand-ins**, the parse-success columns reproduce Table 1 exactly,
but the verbosity ranking does not. Measured link-metadata field counts were lnkinfo 20,
ExifTool 18, LECmd 16 — i.e. the reverse of the paper's High/Medium/Low for LECmd and
lnkinfo.

That is a property of the stand-ins, not of the normalizer. The stand-ins carry no
LinkTargetIDList and only one ExtraData block, and those are precisely the structures that
give LECmd its edge on real samples (`TargetIDAbsolutePath`, shell-item breakdowns, the
extra-block inventory). The Verbosity column therefore needs the original VirusTotal
samples to reproduce; the parse-success columns do not.

## Environment prerequisites

Not shipped here — these must exist in the environments before the playbooks run:

| Environment | Needs |
|---|---|
| `ubuntu24043` | `exiftool` (`libimage-exiftool-perl`, 12.76 on noble) and `lnkinfo` (`liblnk-utils`, 20181227 on noble). Both are in the Ubuntu archive. |
| `win11` | `LECmd.exe` 1.5.1 in the environment's shared tools directory, so the playbook's `tool: LECmd.exe` resolves. Download from <https://ericzimmerman.github.io/>. |

The `win11` environment name follows the paper's "Windows 11". The registered Windows
environments on the authoring host are named differently (`win11arm3`,
`win11-autopsy-solr4`, …) — adjust `lnk_lecmd_windows11/metadata.yml` to whichever Windows
environment carries LECmd, or run with an explicit `--environment`.
