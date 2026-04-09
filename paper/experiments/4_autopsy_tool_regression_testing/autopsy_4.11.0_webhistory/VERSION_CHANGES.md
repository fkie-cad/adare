# Autopsy Version Changes: 4.10.0 → 4.11.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.11.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.10.0_to_4.11.0.json`

---

## Summary

**2 column change(s)** | **133 row(s) added** | **2 row(s) removed** | **10 row(s) modified**

**Breaking** change. Forensic tools may require updates.

---

## Schema Changes

### Column Schema Changes

#### Recent Documents

| Column Name | Change Type | Notes |
|-------------|-------------|-------|
| Path ID | **Removed** | No longer collected |

#### Web History

| Column Name | Change Type | Notes |
|-------------|-------------|-------|
| Username | **Added** | New data field |


---

## Data Changes (Heatmap Analysis)

### Row-Level Changes (Type 1)

#### Summary

- **Removed Rows:** 2
  - Details: See JSON for full row data

#### Web History

- **Added Rows:** 123
  - See comparison JSON for complete list (123 rows)

#### Web Search

- **Added Rows:** 10
  - See comparison JSON for complete list (10 rows)

### Cell-Level Changes (Type 2)

#### Web History

- **Modified Rows:** 10
- **Changed Columns:** Referrer


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

**Tests to Update:** 2

- `test_columns_recent_documents` - Update expected column list
- `test_columns_web_history` - Update expected column list


---

## References

- **Heatmap Comparison:** `output/changes_4.10.0_to_4.11.0.json`
- **Reference Excel:** `shared/data/Report_4.11.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
