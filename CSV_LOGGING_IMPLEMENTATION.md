# CSV Logging Implementation Summary

## Overview
Successfully implemented CSV logging feature for CV server debug mode. When `adare dev cv start --debug` is used, the system now saves both PNG screenshots with visual annotations AND structured CSV files containing detected text data.

## Changes Made

### 1. Constants Addition
**File:** `adare-cv-server/adare_cv_server/constants.py:43`

Added `DEBUG_CSV_HEADER` constant to `OCRConstants` class:
```python
DEBUG_CSV_HEADER = "operation,timestamp,screenshot_file,text,confidence,center_x,center_y,box_x1,box_y1,box_x2,box_y2,box_x3,box_y3,box_x4,box_y4"
```

### 2. New CSV Saving Method
**File:** `adare-cv-server/adare_cv_server/ocr_processing.py:153-221`

Added `TextDetector._save_debug_csv()` classmethod that:
- Accepts detections, prefix, and optional timestamp
- Writes CSV file with matching timestamp to PNG
- Includes operation name, timestamp, screenshot filename
- Records detected text, confidence scores, center points, and full bounding boxes
- Uses Python's csv module for proper escaping
- Logs success/failure appropriately

### 3. Timestamp Refactoring
**File:** `adare-cv-server/adare_cv_server/ocr_processing.py:112,139-141`

Updated `_save_debug_image()` method:
- Added optional `timestamp` parameter to signature
- Generates timestamp only if not provided
- Ensures PNG and CSV files use identical timestamps

### 4. Updated Callsites
**File:** `adare-cv-server/adare_cv_server/ocr_processing.py`

**In `get_all_text()` (lines 236-239):**
```python
# Save debug output with matching timestamps
timestamp = datetime.now().strftime("%H%M%S_%f")
TextDetector._save_debug_image(screenshot_bytes, result, "get_all_text", timestamp)
TextDetector._save_debug_csv(result, "get_all_text", timestamp)
```

**In `find_text()` (lines 288-292):**
```python
# Save debug output with matching timestamps
timestamp = datetime.now().strftime("%H%M%S_%f")
prefix = f"find_text_{text}"
TextDetector._save_debug_image(screenshot_bytes, result, prefix, timestamp)
TextDetector._save_debug_csv(result, prefix, timestamp)
```

## CSV Format

Each CSV file contains:
- **Header row:** operation, timestamp, screenshot_file, text, confidence, center_x, center_y, box_x1-4, box_y1-4
- **Data rows:** One per detected text instance

Example:
```csv
operation,timestamp,screenshot_file,text,confidence,center_x,center_y,box_x1,box_y1,box_x2,box_y2,box_x3,box_y3,box_x4,box_y4
get_all_text,153042_123456,get_all_text_153042_123456.png,Login,0.9823,450,120,440,115,460,115,460,125,440,125
get_all_text,153042_123456,get_all_text_153042_123456.png,Password,0.9512,450,160,430,155,470,155,470,165,430,165
```

## File Naming Convention

Both files use identical naming:
- PNG: `{operation}_{timestamp}.png`
- CSV: `{operation}_{timestamp}.csv`

Examples:
- `get_all_text_143025_123456.png` / `get_all_text_143025_123456.csv`
- `find_text_Login_143030_789012.png` / `find_text_Login_143030_789012.csv`

## Usage Examples

### Start Debug Mode
```bash
adare dev start
adare dev cv start --debug
# Run playbook actions that use text detection
```

Debug files auto-saved to: `{experiment_run_dir}/screenshots/cv_debug/`

### Search CSV Files
```bash
# Find all instances of specific text
grep "Login" *.csv

# Filter by confidence threshold (>0.95)
awk -F',' '$5 > 0.95' *.csv | column -t -s','

# Count text detections per operation
cut -d',' -f1 *.csv | sort | uniq -c

# Extract all high-confidence text
awk -F',' '$5 > 0.90 {print $4}' *.csv | sort | uniq
```

## Benefits

1. **Searchability:** Quickly grep for specific text across debug sessions
2. **Filtering:** Use awk/pandas to filter by confidence thresholds
3. **Analysis:** Import into Excel, SQL, or pandas for deeper analysis
4. **Correlation:** Screenshot filename column enables direct PNG lookup
5. **Auditability:** Structured data aligns with ADARE's forensic principles
6. **Minimal Impact:** CSV writing only happens in debug mode (opt-in)

## Verification Steps

1. Start experiment in dev mode: `adare dev start`
2. Restart CV server with debug: `adare dev cv start --debug`
3. Run playbook action that uses text detection
4. Check debug output directory
5. Verify paired PNG/CSV files exist with matching timestamps
6. Verify CSV structure matches expected format
7. Test grep/awk commands for searchability
8. Verify bounding box coordinates align with PNG annotations

## Technical Notes

- Uses Python's `csv` module for proper escaping of special characters
- Handles text containing commas, quotes, newlines correctly
- Same error handling pattern as existing debug image saving
- No breaking changes - purely additive feature
- Follows existing code patterns and conventions
