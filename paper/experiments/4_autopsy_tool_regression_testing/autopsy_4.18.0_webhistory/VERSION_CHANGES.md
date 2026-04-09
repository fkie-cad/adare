# Autopsy Version Changes: 4.17.0 → 4.18.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.18.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.17.0_to_4.18.0.json`

---

## Summary

**1 new sheet(s)** added | **147 row(s) modified**

**Non-breaking** change. Existing forensic workflows should remain compatible.

---

## Schema Changes

### Sheet Structure

| Sheet Name | Status | Notes |
|------------|--------|-------|
| Web Categories | **Added** | New artifact type |

**Summary:** +1 new


---

## Data Changes (Heatmap Analysis)

### Cell-Level Changes (Type 2)

#### Web Bookmarks

- **Modified Rows:** 12
- **Changed Columns:** Domain

#### Web History

- **Modified Rows:** 118
- **Changed Columns:** Domain

#### Web Search

- **Modified Rows:** 17
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

**New Tests Needed:** 3

- `test_sheet_web_categories_exists` - Sheet existence
- `test_columns_web_categories` - Column validation
- `test_content_web_categories` - Content comparison


---

## References

- **Heatmap Comparison:** `output/changes_4.17.0_to_4.18.0.json`
- **Reference Excel:** `shared/data/Report_4.18.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
