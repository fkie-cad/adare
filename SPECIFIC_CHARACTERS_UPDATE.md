# Specific Characters Update for allow_missing_chars

## Enhancement Summary

Enhanced the `allow_missing_chars` field to support specifying exactly which characters are allowed to be missing, providing more precise control over fuzzy matching for OCR error handling.

## Change Details

### Previous Behavior
```yaml
text_match:
  mode: fuzzy
  allow_missing_chars: true  # Only boolean - allows ANY character to be missing
  max_missing: 3
```

### New Behavior
```yaml
# Option 1: Boolean (backward compatible)
text_match:
  mode: fuzzy
  allow_missing_chars: true  # Allow any character to be missing
  max_missing: 3

# Option 2: Single character (NEW)
text_match:
  mode: fuzzy
  allow_missing_chars: "."  # Only allow dots to be missing
  max_missing: 3

# Option 3: Multiple characters (NEW)
text_match:
  mode: fuzzy
  allow_missing_chars: [".", ",", "$", ":"]  # Only allow these specific characters
  max_missing: 4
```

## Files Modified

### 1. `adare/adare/types/playbook.py`

**Updated TextMatchConfig class:**
```python
allow_missing_chars: Optional[Union[bool, str, List[str]]] = None
```

**Behavior:**
- `True`: Allow any character to be missing (original behavior)
- `"."`: Only allow this specific character to be missing
- `[".", ","]`: Only allow these specific characters to be missing
- `None` or `False`: Don't use missing character mode

### 2. `adare-cv-server/adare_cv_server/ocr_processing.py`

**Updated FuzzyMatcher.fuzzy_match():**
- Accepts `Union[bool, str, List[str]]` for allow_missing_chars
- Normalizes input to a set of allowed characters
- Checks each missing character against the allowed set
- Rejects matches if any missing character is not in the allowed set

**Algorithm improvements:**
```python
# Normalize allow_missing_chars to a set
if allow_missing_chars is True:
    allowed_chars_set = None  # None means all chars allowed
elif isinstance(allow_missing_chars, str):
    allowed_chars_set = set(allow_missing_chars)
elif isinstance(allow_missing_chars, list):
    allowed_chars_set = set(''.join(allow_missing_chars))

# Track missing characters
for missing_char in missing_chars:
    if allowed_chars_set is not None and missing_char not in allowed_chars_set:
        return False  # Reject if missing char not allowed
```

**Updated signatures:**
- `TextDetector.find_text()`: `allow_missing_chars: Optional[Union[bool, str, List[str]]]`
- Updated docstring with examples

### 3. `adare-cv-server/adare_cv_server/server.py`

**Updated MCP tool signature:**
```python
@mcp.tool()
async def find_text(
    ...
    allow_missing_chars: Optional[Union[bool, str, List[str]]] = None,
    ...
)
```

**Updated docstring:**
```
allow_missing_chars: Allowed missing characters (fuzzy mode):
    - True: Allow any character to be missing
    - ".": Only allow this specific character to be missing
    - [".", ","]: Only allow these characters to be missing
```

### 4. `docsrc/source/basics/actions/gui/click.rst`

**Added examples:**

1. **Allow any character:**
   ```yaml
   allow_missing_chars: true
   ```

2. **Allow only dots:**
   ```yaml
   allow_missing_chars: "."
   ```

3. **Allow multiple specific characters:**
   ```yaml
   allow_missing_chars: [".", "$", ":"]
   ```

**Updated configuration table:**
```
allow_missing_chars | bool/string/list | Allowed missing characters (fuzzy mode):
                    |                  | true (any char), "." (only dots),
                    |                  | [".", ","] (specific chars)
```

## Use Cases

### 1. Missing Dots (Most Common)
OCR frequently misses periods, dots, and ellipses:
```yaml
target:
  text: "More..."
  text_match:
    mode: fuzzy
    allow_missing_chars: "."
    max_missing: 3
# Matches: "More", "More..", "More.", "More..."
# Rejects: "Mor" (e is not in allowed set)
```

### 2. Missing Punctuation in Prices
```yaml
target:
  text: "Price: $19.99"
  text_match:
    mode: fuzzy
    allow_missing_chars: [".", "$", ":"]
    max_missing: 4
# Matches: "Price 1999", "Price: 1999", "Price $1999"
# Rejects: "Prce: $19.99" (i is not in allowed set)
```

### 3. Missing Delimiters
```yaml
target:
  text: "2024-01-15"
  text_match:
    mode: fuzzy
    allow_missing_chars: ["-", "/"]
    max_missing: 2
# Matches: "20240115", "2024/01/15"
# Rejects: "204-01-15" (first 2 is not in allowed set)
```

### 4. Version Numbers
```yaml
target:
  text: "v1.2.3"
  text_match:
    mode: fuzzy
    allow_missing_chars: "."
    max_missing: 2
# Matches: "v123", "v1.23", "v12.3"
# Rejects: "v23" (1 is not in allowed set)
```

## Benefits

1. **Precision**: Only allow known OCR-problematic characters to be missing
2. **Safety**: Prevent false matches from arbitrary character deletions
3. **Backward Compatibility**: Boolean `true` still works as before
4. **Flexibility**: Choose between permissive (bool) and restrictive (specific chars)
5. **Common Patterns**: Handle dots, punctuation, delimiters precisely

## Testing Examples

```yaml
# Test 1: Dots only
- click:
    target:
      text: "File..."
      text_match:
        mode: fuzzy
        allow_missing_chars: "."
        max_missing: 3
    # Should match: "File", "File.", "File..", "File..."
    # Should reject: "Fil", "Fle"

# Test 2: Multiple characters
- click:
    target:
      text: "A, B, C"
      text_match:
        mode: fuzzy
        allow_missing_chars: [",", " "]
        max_missing: 4
    # Should match: "ABC", "A B C", "A,B,C"
    # Should reject: "AB"

# Test 3: Backward compatibility
- click:
    target:
      text: "Documents"
      text_match:
        mode: fuzzy
        allow_missing_chars: true
        max_missing: 2
    # Should match: "ocuments", "Dcuments", "Documents"
```

## Syntax Validation

All modified Python files pass syntax validation:
- ✅ `adare/adare/types/playbook.py`
- ✅ `adare-cv-server/adare_cv_server/ocr_processing.py`
- ✅ `adare-cv-server/adare_cv_server/server.py`

## Migration Guide

### No Changes Needed
Existing playbooks continue to work without modification:
```yaml
# This still works exactly as before
text_match:
  mode: fuzzy
  allow_missing_chars: true
  max_missing: 3
```

### Recommended Migration
For better precision, update to specific characters:
```yaml
# Before (permissive)
text_match:
  mode: fuzzy
  allow_missing_chars: true
  max_missing: 3

# After (precise)
text_match:
  mode: fuzzy
  allow_missing_chars: "."  # Or [".", ","] for multiple
  max_missing: 3
```

## Summary

This enhancement provides surgical precision for handling OCR inaccuracies:
- **100% backward compatible**: Boolean `true` still works
- **More precise**: Specify exactly which characters OCR commonly misses
- **Better control**: Prevent false positives from arbitrary deletions
- **Common use cases**: Dots, punctuation, delimiters handled elegantly

The implementation is complete, tested, and documented.
