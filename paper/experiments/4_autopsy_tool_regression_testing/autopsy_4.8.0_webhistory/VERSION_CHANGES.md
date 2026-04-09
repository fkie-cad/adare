# Autopsy Version Changes: 4.7.0 → 4.8.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.8.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.7.0_to_4.8.0.json`

---

## Summary

**75 row(s) modified**

**Non-breaking** change. Existing forensic workflows should remain compatible.

---

## Schema Changes

### Schema Changes

**No schema changes detected.** All sheets and columns remain unchanged.


---

## Data Changes (Heatmap Analysis)

### Cell-Level Changes (Type 2)

#### Web Cookies

- **Modified Rows:** 75
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

**No test modifications required.** Existing tests remain valid.


---

## References

- **Heatmap Comparison:** `output/changes_4.7.0_to_4.8.0.json`
- **Reference Excel:** `shared/data/Report_4.8.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
