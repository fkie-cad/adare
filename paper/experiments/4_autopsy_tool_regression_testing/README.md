# Case study 5.4 — Autopsy Tool Regression Testing

> "we performed a regression study of Autopsy across 25 versions, focusing on the Recent
> Activity ingest module and its exported Excel report output. We used the Windows test
> image from NIST's CFReDS repository as a stable input across all runs and defined the
> expected output using the earliest available version, Autopsy 4.4.0."
> — ADARE paper, §5.4

Each `autopsy_<version>_webhistory/` directory runs the same GUI workflow against the same
disk image on one Autopsy version, exports the Excel report, and compares every sheet
against that version's reference workbook: sheet existence, column headers
(`excel.validate_columns`), and row content (`excel.compare_rows`).

## Versions shipped

24 of the paper's 25 versions have a playbook here:

| Environment | Autopsy versions | Count | Solr |
|---|---|--:|---|
| `win11-autopsy-solr4` | 4.4.0, 4.4.1, 4.5.0, 4.6.0, 4.7.0, 4.8.0, 4.9.0, 4.9.1, 4.10.0, 4.11.0, 4.12.0, 4.13.0, 4.14.0, 4.15.0, 4.16.0, 4.17.0 | 16 | 4.10.3 |
| `win11-autopsy-solr8` | 4.18.0, 4.19.0, 4.19.1, 4.19.2, 4.19.3, 4.20.0, 4.21.0, 4.22.1 | 8 | 8.6.3+ |

The split is not cosmetic: at Autopsy 4.18.0 the bundled Apache Solr jumped 4.10.3 → 8.6.3,
Solr 8 cannot read Solr 4 indexes, and the embedded services collide on ports. The two
versions therefore cannot coexist in one image. `provisioning/README.md` has the build
runbook; `provisioning/versions_solr4.txt` and `versions_solr8.txt` are the authoritative
version lists that `metadata.yml` here is generated from.

**4.22.0 has no playbook, and that is correct.** It is the "Missing Version (X)" column in
the paper's Figure 2 — the version whose release notes the paper checked for an explanation
of the observed changes, not one it ran. 24 playbooks + 4.22.0 as X = the paper's 25
columns.

## Not shipped

| Missing | Why | How to obtain |
|---|---|---|
| `2020JimmyWilson.E01` | NIST CFReDS disk image, far too large to commit. Referenced as `{{ adare_project_shared }}\data\2020JimmyWilson.E01`. | <https://cfreds.nist.gov/> — place it in the project's `shared/data/`. |
| The two VM images | Built, not committed. | `provisioning/README.md` build runbook, then `adare environment load win11-autopsy-solr4` / `-solr8`. |
| Autopsy MSIs | Downloaded during provisioning. | `provisioning/Install-Autopsy.ps1` fetches each version's official 64-bit MSI. |

Each version's reference workbook (`shared/data/Report_<version>_reference.xlsx`) **is**
committed, so the comparison oracle travels with the experiment.

## Two known issues, deliberately not fixed here

Both predate this change and both are broader than the metadata update this directory
received, so they are recorded rather than silently swept into an unrelated diff.

**1. 352 action descriptions are silently discarded.** These playbooks write the step
description as a *sibling* of the action key:

```yaml
- keyboard:
    key: enter
  description: 'Case Information: Next'   # <- dropped
```

`KeyboardAction` has a `description` field, but `_structure_action`
(`adare/adare/types/playbook.py`) only ever structures `obj['keyboard']`, so a sibling key
is ignored. The playbook parses cleanly and the description never reaches the action or the
forensic audit log. The fix is to indent each one under its action key:

```yaml
- keyboard:
    key: enter
    description: 'Case Information: Next'
```

352 occurrences across these 24 files, and none anywhere else in `paper/experiments`. Worth
doing — a GUI regression suite whose step labels vanish is harder to debug than it needs to
be — but it is a 24-file mechanical edit to the *actions*, not the metadata.

**2. 45 committed `playbook.yml.bak*` files**, left over from
`adare experiment playbook set --backup` runs. Nothing references them and they are noise in
a published artifact set.
