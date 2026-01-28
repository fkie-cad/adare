# Implementation Summary: S/E Index Support for Dev Playbook

## Overview
Successfully implemented support for S (start) and E (end) special indices in the dev playbook `--indices` argument. Users can now specify ranges like `S-5`, `7,23-E`, or `S-E` (all actions) without knowing the exact number of actions.

## Changes Made

### 1. DTO Update (`adare/adare/core/dto/devmode.py`)
- **Line 57**: Changed `DevPlaybookExecuteRequest.indices` type from `Optional[List[int]]` to `Optional[str]`
- **Rationale**: Indices must be parsed after the playbook is loaded to know the total action count

### 2. CLI Parser Refactoring (`adare/adare/cli/dev.py`)
- **Lines 567-635**: Refactored index parsing into two functions:

  **A. `parse_indices_with_bounds(indices_str: str, total_actions: int) -> List[int]`**
  - Core parsing function that supports S/E syntax
  - Normalizes case (s→S, e→E)
  - Replaces S with 1 and E with total_actions
  - Validates all indices are within bounds [1, total_actions]
  - Raises ValueError for invalid formats or out-of-bounds indices

  **B. `_parse_indices(indices_str: Optional[str], total_actions: int) -> Optional[List[int]]`**
  - CLI wrapper for parse_indices_with_bounds
  - Returns None if indices_str is None
  - Catches ValueError and prints user-friendly error message before exit(1)

- **Line 621**: Updated CLI to pass raw indices string instead of parsing:
  ```python
  # OLD: indices = _parse_indices(getattr(arguments, 'indices', None))
  # NEW: indices = getattr(arguments, 'indices', None)
  ```

### 3. Service Layer Parsing (`adare/adare/services/devmode_service.py`)
- **Lines 807-814**: Added parsing logic after playbook is loaded:
  ```python
  # Parse indices if provided (now that we know action count)
  parsed_indices = None
  if request.indices:
      from adare.cli.dev import parse_indices_with_bounds
      try:
          parsed_indices = parse_indices_with_bounds(request.indices, len(playbook.actions))
      except ValueError as e:
          raise ValueError(f"Invalid indices specification: {e}")
  ```

- **Line 833**: Updated execute_playbook call to use `parsed_indices` instead of `request.indices`

## Supported Formats

### Numeric Indices (Backward Compatible)
- Single: `"5"` → `[5]`
- Range: `"3-7"` → `[3, 4, 5, 6, 7]`
- Multiple: `"1-3,5,7-9"` → `[1, 2, 3, 5, 7, 8, 9]`

### New S/E Indices
- Start: `"S"` → `[1]`
- End: `"E"` → `[total_actions]`
- Start range: `"S-5"` → `[1, 2, 3, 4, 5]`
- End range: `"7-E"` → `[7, 8, 9, ..., total_actions]`
- All actions: `"S-E"` → `[1, 2, ..., total_actions]`
- Mixed: `"S-3,5,8-E"` → `[1, 2, 3, 5, 8, 9, ..., total_actions]`

### Features
- **Case-insensitive**: `"s-5"` and `"S-5"` work identically
- **Whitespace tolerant**: `" 1 - 3 , 5 "` works correctly
- **Duplicate removal**: `"1-3,2-4"` → `[1, 2, 3, 4]`
- **Sorted output**: Always returns sorted list of unique indices

## Error Handling

### Validation Errors (ValueError)
- **Out of bounds**: `"15"` with 10 actions → `"Index 15 out of bounds (playbook has 10 actions)"`
- **Backward range**: `"5-3"` → `"Invalid range '5-3': start (5) > end (3)"`
- **Invalid format**: `"1-2-3"` → `"Invalid range format: '1-2-3'"`
- **Invalid characters**: `"1,a,3"` → ValueError from int() conversion

### Error Flow
1. **CLI Layer**: Catches ValueError, prints user-friendly message with examples, exits with code 1
2. **Service Layer**: Catches ValueError, wraps in error result, returns to caller (no server crash)

## Testing

### Standalone Test Results
Created `test_parse_indices_standalone.py` to verify implementation:
- ✓ Single numeric index
- ✓ Numeric range
- ✓ Multiple ranges
- ✓ S (start) index
- ✓ E (end) index
- ✓ S-5 range
- ✓ 7-E range
- ✓ S-E range (all)
- ✓ Mixed S, E, and numeric
- ✓ Case insensitive
- ✓ Out of bounds error
- ✓ Backward range error
- ✓ E-S error
- ✓ Whitespace handling
- ✓ Duplicate indices removed

**All tests passed!**

### Manual Testing Commands
```bash
# Execute first 5 actions
adare dev playbook <session> -f test.yml --indices "S-5"

# Execute action 7 only
adare dev playbook <session> -f test.yml --indices "7"

# Execute actions 5 and everything from 23 to end
adare dev playbook <session> -f test.yml --indices "5,23-E"

# Execute all actions (equivalent to no --indices flag)
adare dev playbook <session> -f test.yml --indices "S-E"

# Mixed formats
adare dev playbook <session> -f test.yml --indices "S-3,10,15-E"

# Case insensitive
adare dev playbook <session> -f test.yml --indices "s-5,7,9-e"

# Test error: out of bounds
adare dev playbook <session> -f test.yml --indices "S-20"
# Expected: Error message with "Index 20 out of bounds"
```

## Backward Compatibility
✅ **Fully backward compatible** - All existing numeric index specifications continue to work:
- `"1-3"` still works
- `"1,3,4"` still works
- `"1-3,4-9"` still works

## Files Modified
1. `adare/adare/core/dto/devmode.py` - DTO type change
2. `adare/adare/cli/dev.py` - Parser refactoring and CLI update
3. `adare/adare/services/devmode_service.py` - Service layer parsing

## Files NOT Modified (As Expected)
- `adare/webapi/main.py` - Web API doesn't use indices parameter
- `adare/adare/backend/devmode/session.py` - Still receives `List[int]`
- `adare/adare/backend/experiment/playbook_controller.py` - Still receives `List[int]`

## Key Design Decisions

### Deferred Parsing Strategy
- **Problem**: CLI doesn't know the total action count at parse time
- **Solution**: Parse indices in service layer after playbook is loaded
- **Benefit**: Clean separation of concerns, S/E can reference actual playbook size

### Function Split
- **parse_indices_with_bounds()**: Core logic, raises exceptions
- **_parse_indices()**: CLI wrapper, handles None and converts errors to user messages
- **Benefit**: Reusable core logic, CLI-specific error handling separate

### Import Location
- Imported in service layer at usage point (not at module top)
- **Rationale**: Avoids circular dependencies, keeps service independent of CLI

## Next Steps for User
The implementation is complete and ready for manual testing. To verify:

1. Create a test playbook with ~10 actions
2. Run the manual testing commands listed above
3. Verify S/E indices work as expected
4. Confirm error messages are clear and helpful
5. Test edge cases (single action playbook, large playbooks, etc.)
