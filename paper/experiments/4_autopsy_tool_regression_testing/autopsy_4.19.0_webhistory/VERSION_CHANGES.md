# Autopsy Version Changes: 4.18.0 → 4.19.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.19.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.18.0_to_4.19.0.json`

---

## Summary

**1 sheet(s)** removed | **1 column change(s)** | **3 row(s) added** | **126 row(s) modified**

**Breaking** change. Forensic tools may require updates.

---

## Schema Changes

### Sheet Structure

| Sheet Name | Status | Notes |
|------------|--------|-------|
| Operating System User Account | **Removed** | No longer generated |

**Summary:** -1 removed

### Column Schema Changes

#### Web Cookies

| Column Name | Change Type | Notes |
|-------------|-------------|-------|
| Date Accessed | **Added** | New data field |


---

## Data Changes (Heatmap Analysis)

### Row-Level Changes (Type 1)

#### Web Categories

- **Added Rows:** 3
  - Details: See JSON for full row data

### Cell-Level Changes (Type 2)

#### Operating System Information

- **Modified Rows:** 2
- **Changed Columns:** Install Date

#### Web Cookies

- **Modified Rows:** 124
- **Changed Columns:** Date Created, Date/Time


---

## Forensic Impact Analysis

**Breaking Changes:** Yes
- Schema changes that break existing tools/workflows
- 1 sheet(s) removed

**Forensic Significance:**
- **High:** Changes affecting evidence integrity or completeness

**Upgrade Considerations:**
- Review test results before deploying in production
- Validate that critical artifacts are still extracted
- Update documentation and training materials as needed


---

## Test Modifications Required

**Tests to Update:** 1

- `test_columns_web_cookies` - Update expected column list

**Tests to Remove:** 3

- Remove all tests for 'Operating System User Account' sheet


---

## References

- **Heatmap Comparison:** `output/changes_4.18.0_to_4.19.0.json`
- **Reference Excel:** `shared/data/Report_4.19.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
