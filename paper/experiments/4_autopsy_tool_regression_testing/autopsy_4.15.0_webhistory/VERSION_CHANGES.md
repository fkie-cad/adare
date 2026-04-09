# Autopsy Version Changes: 4.14.0 → 4.15.0

**Generated:** 2026-02-06
**Experiment:** autopsy_4.15.0_webhistory
**Analysis Type:** Web History Forensic Artifacts
**Source:** Automated comparison using excel_comparator heatmap tool
**Comparison File:** `changes_4.14.0_to_4.15.0.json`

---

## Summary

**1 column change(s)** | **2 row(s) added**

**Non-breaking** change. Existing forensic workflows should remain compatible.

---

## Schema Changes

### Column Schema Changes

#### Recent Documents

| Column Name | Change Type | Notes |
|-------------|-------------|-------|
| Comment | **Added** | New data field |


---

## Data Changes (Heatmap Analysis)

### Row-Level Changes (Type 1)

#### Recent Documents

- **Added Rows:** 2
  - Details: See JSON for full row data


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

**Tests to Update:** 1

- `test_columns_recent_documents` - Update expected column list


---

## References

- **Heatmap Comparison:** `output/changes_4.14.0_to_4.15.0.json`
- **Reference Excel:** `shared/data/Report_4.15.0_reference.xlsx`
- **Playbook:** `playbook.yml`
- **Heatmap Tool:** `/media/miq/FKIE/AdarePaper/casestudies/Autopsy/heatmaptool/`
