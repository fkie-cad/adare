# Autopsy Version Changes: 4.15.0 → 4.16.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.16.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.15.0_to_4.16.0.json`

---

## Summary

**2 sheet(s)** removed | **1 row(s) added** | **1 row(s) removed** | **1 row(s) modified**

**Breaking** change. Forensic tools may require updates.

---

## Schema Changes

### Sheet Structure

| Sheet Name | Status | Notes |
|------------|--------|-------|
| Data Source Usage | **Removed** | No longer generated |
| Recycle Bin | **Removed** | No longer generated |

**Summary:** -2 removed


---

## Data Changes (Heatmap Analysis)

### Row-Level Changes (Type 1)

#### Summary

- **Added Rows:** 1
  - Details: See JSON for full row data
- **Removed Rows:** 1
  - Details: See JSON for full row data

### Cell-Level Changes (Type 2)

#### Operating System User Account

- **Modified Rows:** 1
- **Changed Columns:** User Name


---

## Forensic Impact Analysis

**Breaking Changes:** Yes
- Schema changes that break existing tools/workflows
- 2 sheet(s) removed

**Forensic Significance:**
- **High:** Changes affecting evidence integrity or completeness

**Upgrade Considerations:**
- Review test results before deploying in production
- Validate that critical artifacts are still extracted
- Update documentation and training materials as needed


---

## Test Modifications Required

**Tests to Remove:** 6

- Remove all tests for 'Data Source Usage' sheet
- Remove all tests for 'Recycle Bin' sheet


---

## References

- **Heatmap Comparison:** `output/changes_4.15.0_to_4.16.0.json`
- **Reference Excel:** `shared/data/Report_4.16.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
