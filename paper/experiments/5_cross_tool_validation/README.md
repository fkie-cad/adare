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
| `lnk_lecmd_windows11/` | `win11` | LECmd 1.5.1 | L1 ✓ L2 ✓ L3 ✓ — Verbosity High |
| `lnk_exiftool_ubuntu2404/` | `ubuntu24043` | ExifTool 12.76 | L1 ✓ L2 ✓ L3 ✓ — Verbosity Low |
| `lnk_lnkinfo_ubuntu2404/` | `ubuntu24043` | lnkinfo 20181227 | L1 ✓ L2 **✗** L3 **✗** — Verbosity Medium |

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
| …**and says so rather than failing** | `l2_reports_appended_data`, `l3_reports_appended_data`; `l1_no_overlay_warning` is the negative control | `lnk_exiftool_ubuntu2404` |
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

## What is verified and what is not

Verified on the authoring host against real tool builds — the full measurement table is in
`provisioning/README.md`:

- The L1/L2/L3 behaviour split for `lnkinfo` 20181227 and ExifTool 12.76, including the
  exact stderr wording the regex assertions match.
- Every `standard.*`, `json.*` and `jsonl.*` assertion in all three playbooks, run against
  real (or, for LECmd, representative) parser output, each with a negative control to
  confirm the assertion can actually fail.
- The normalizer reproducing Table 1's parse-success columns.

Not verified, and flagged in the playbook itself:

- **LECmd's output format and exit-code convention.** It is a Windows/.NET tool and the
  authoring host is macOS. The playbook assumes `--json` writes newline-delimited JSON
  (as its sibling PECmd does, per `3_tool_validation/pecmd/playbook.yml`) and that LECmd
  exits 0 on success. If either differs, `l*_exit_code_zero` and the `jsonl.line_matches`
  tests are the ones to re-baseline; the pulled artifacts make that a one-minute check.
- **Table 1's Verbosity column against the benign stand-ins.** It does not reproduce, for
  a documented structural reason — see `provisioning/README.md`.

## Running it

```bash
# 1. samples into the project's shared data (once)
python3 provisioning/make_lnk_samples.py --output-dir <project>/shared/data

# 2. one experiment per OS
adare experiment run lnk_exiftool_ubuntu2404 --environment ubuntu24043
adare experiment run lnk_lnkinfo_ubuntu2404  --environment ubuntu24043
adare experiment run lnk_lecmd_windows11     --environment win11

# 3. fold the three outputs into Table 1
python3 provisioning/normalize_lnk_outputs.py --artifacts <runs_root> \
    --csv table1.csv --markdown table1.md
```

Environment prerequisites (ExifTool and liblnk-utils in the Ubuntu image, `LECmd.exe` in
the Windows environment's shared tools) are listed in `provisioning/README.md`.
