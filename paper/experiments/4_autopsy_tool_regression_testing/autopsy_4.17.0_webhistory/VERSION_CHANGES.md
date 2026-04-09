# Autopsy Version Changes: 4.16.0 → 4.17.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.17.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.16.0_to_4.17.0.json`

---

## Summary

**3 new sheet(s)** added

**Non-breaking** change. Existing forensic workflows should remain compatible.

---

## Schema Changes

### Sheet Structure

| Sheet Name | Status | Notes |
|------------|--------|-------|
| Data Source Usage | **Added** | New artifact type |
| Recycle Bin | **Added** | New artifact type |
| Run Programs | **Added** | New artifact type |

**Summary:** +3 new


---

## Data Changes (Heatmap Analysis)

**No data changes detected.** Row counts and cell values remain unchanged.


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

**New Tests Needed:** 9

- `test_sheet_data_source_usage_exists` - Sheet existence
- `test_columns_data_source_usage` - Column validation
- `test_content_data_source_usage` - Content comparison
- `test_sheet_recycle_bin_exists` - Sheet existence
- `test_columns_recycle_bin` - Column validation
- `test_content_recycle_bin` - Content comparison
- `test_sheet_run_programs_exists` - Sheet existence
- `test_columns_run_programs` - Column validation
- `test_content_run_programs` - Content comparison


---

## References

- **Heatmap Comparison:** `output/changes_4.16.0_to_4.17.0.json`
- **Reference Excel:** `shared/data/Report_4.17.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
