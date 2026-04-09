# Autopsy Version Changes: 4.12.0 → 4.13.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.13.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.12.0_to_4.13.0.json`

---

## Summary

**2 new sheet(s)** added

**Non-breaking** change. Existing forensic workflows should remain compatible.

---

## Schema Changes

### Sheet Structure

| Sheet Name | Status | Notes |
|------------|--------|-------|
| Recycle Bin | **Added** | New artifact type |
| Shell Bags | **Added** | New artifact type |

**Summary:** +2 new


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

**New Tests Needed:** 6

- `test_sheet_recycle_bin_exists` - Sheet existence
- `test_columns_recycle_bin` - Column validation
- `test_content_recycle_bin` - Content comparison
- `test_sheet_shell_bags_exists` - Sheet existence
- `test_columns_shell_bags` - Column validation
- `test_content_shell_bags` - Content comparison


---

## References

- **Heatmap Comparison:** `output/changes_4.12.0_to_4.13.0.json`
- **Reference Excel:** `shared/data/Report_4.13.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
