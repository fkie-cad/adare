# Autopsy Version Changes: 4.19.1 → 4.19.2

**Generated:** 2026-02-06
**Experiment:** autopsy_4.19.2_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.19.1_to_4.19.2.json`

---

## Summary

**7 row(s) added** | **28 row(s) modified**

**Non-breaking** change. Existing forensic workflows should remain compatible.

---

## Schema Changes

### Schema Changes

**No schema changes detected.** All sheets and columns remain unchanged.


---

## Data Changes (Heatmap Analysis)

### Row-Level Changes (Type 1)

#### Recent Documents

- **Added Rows:** 7
  - See comparison JSON for complete list (7 rows)

### Cell-Level Changes (Type 2)

#### Recycle Bin

- **Modified Rows:** 14
- **Changed Columns:** Username

#### Shell Bags

- **Modified Rows:** 14
- **Changed Columns:** Path


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

- **Heatmap Comparison:** `output/changes_4.19.1_to_4.19.2.json`
- **Reference Excel:** `shared/data/Report_4.19.2_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
