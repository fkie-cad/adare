# Autopsy Version Changes: 4.19.3 → 4.20.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.20.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.19.3_to_4.20.0.json`

---

## Summary

**3 column change(s)** | **1 row(s) added** | **3 row(s) removed** | **292 row(s) modified**

**Breaking** change. Forensic tools may require updates.

---

## Schema Changes

### Column Schema Changes

#### Operating System Information

| Column Name | Change Type | Notes |
|-------------|-------------|-------|
| Version | **Removed** | No longer collected |
| Domain | **Removed** | No longer collected |
| Organization | **Removed** | No longer collected |


---

## Data Changes (Heatmap Analysis)

### Row-Level Changes (Type 1)

#### Operating System Information

- **Added Rows:** 1
  - Details: See JSON for full row data
- **Removed Rows:** 3
  - Details: See JSON for full row data

### Cell-Level Changes (Type 2)

#### Web Bookmarks

- **Modified Rows:** 15
- **Changed Columns:** Program

#### Web Cookies

- **Modified Rows:** 124
- **Changed Columns:** Program

#### Web History

- **Modified Rows:** 136
- **Changed Columns:** Domain, Program

#### Web Search

- **Modified Rows:** 17
- **Changed Columns:** Program Name


---

## Forensic Impact Analysis

**Breaking Changes:** Yes
- Schema changes that break existing tools/workflows
- Column(s) removed from existing sheets

**Forensic Significance:**
- **High:** Changes affecting evidence integrity or completeness

**Upgrade Considerations:**
- Review test results before deploying in production
- Validate that critical artifacts are still extracted
- Update documentation and training materials as needed


---

## Test Modifications Required

**Tests to Update:** 1

- `test_columns_operating_system_information` - Update expected column list


---

## References

- **Heatmap Comparison:** `output/changes_4.19.3_to_4.20.0.json`
- **Reference Excel:** `shared/data/Report_4.20.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
