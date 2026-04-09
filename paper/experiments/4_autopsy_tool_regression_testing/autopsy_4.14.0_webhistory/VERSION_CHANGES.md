# Autopsy Version Changes: 4.13.0 → 4.14.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.14.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.13.0_to_4.14.0.json`

---

## Summary

**5 new sheet(s)** added | **16 row(s) added** | **28 row(s) modified**

**Non-breaking** change. Existing forensic workflows should remain compatible.

---

## Schema Changes

### Sheet Structure

| Sheet Name | Status | Notes |
|------------|--------|-------|
| Data Source Usage | **Added** | New artifact type |
| Installed Programs | **Added** | New artifact type |
| Operating System Information | **Added** | New artifact type |
| Operating System User Account | **Added** | New artifact type |
| USB Device Attached | **Added** | New artifact type |

**Summary:** +5 new


---

## Data Changes (Heatmap Analysis)

### Row-Level Changes (Type 1)

#### Shell Bags

- **Added Rows:** 16
  - See comparison JSON for complete list (16 rows)

### Cell-Level Changes (Type 2)

#### Recycle Bin

- **Modified Rows:** 14
- **Changed Columns:** Username

#### Shell Bags

- **Modified Rows:** 14
- **Changed Columns:** Last Write


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

**New Tests Needed:** 15

- `test_sheet_data_source_usage_exists` - Sheet existence
- `test_columns_data_source_usage` - Column validation
- `test_content_data_source_usage` - Content comparison
- `test_sheet_installed_programs_exists` - Sheet existence
- `test_columns_installed_programs` - Column validation
- `test_content_installed_programs` - Content comparison
- `test_sheet_operating_system_information_exists` - Sheet existence
- `test_columns_operating_system_information` - Column validation
- `test_content_operating_system_information` - Content comparison
- `test_sheet_operating_system_user_account_exists` - Sheet existence
- `test_columns_operating_system_user_account` - Column validation
- `test_content_operating_system_user_account` - Content comparison
- `test_sheet_usb_device_attached_exists` - Sheet existence
- `test_columns_usb_device_attached` - Column validation
- `test_content_usb_device_attached` - Content comparison


---

## References

- **Heatmap Comparison:** `output/changes_4.13.0_to_4.14.0.json`
- **Reference Excel:** `shared/data/Report_4.14.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
