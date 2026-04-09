# Autopsy Version Changes: 4.8.0 → 4.9.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.9.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.8.0_to_4.9.0.json`

---

## Summary

**2 column change(s)** | **3 row(s) modified**

**Non-breaking** change. Existing forensic workflows should remain compatible.

---

## Schema Changes

### Column Schema Changes

#### Tagged Files

| Column Name | Change Type | Notes |
|-------------|-------------|-------|
| User Name | **Added** | New data field |

#### Tagged Results

| Column Name | Change Type | Notes |
|-------------|-------------|-------|
| User Name | **Added** | New data field |


---

## Data Changes (Heatmap Analysis)

### Cell-Level Changes (Type 2)

#### Web Bookmarks

- **Modified Rows:** 3
- **Changed Columns:** Domain


---

## Forensic Impact Analysis

**Breaking Changes:** No

**Forensic Significance:**
- **Medium:** Changes affecting artifact organization or access

**Upgrade Considerations:**
- Review test results before deploying in production
- Validate that critical artifacts are still extracted
- Update documentation and training materials as needed


---

## Test Modifications Required

**Tests to Update:** 2

- `test_columns_tagged_results` - Update expected column list
- `test_columns_tagged_files` - Update expected column list


---

## References

- **Heatmap Comparison:** `output/changes_4.8.0_to_4.9.0.json`
- **Reference Excel:** `shared/data/Report_4.9.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
