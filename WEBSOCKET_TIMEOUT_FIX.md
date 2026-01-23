# WebSocket Timeout Fix - Implementation Summary

## Problem
`adare dev playbook` timed out after 30 seconds even though the VM successfully completed shell commands in ~8 seconds. The same playbook worked fine with `adare exp run`.

## Root Cause
Dev mode was making TWO separate `asyncio.run()` calls, creating two different event loops:
1. First call: Get/restore session (creates loop A, starts WebSocket message handler)
2. Second call: Execute playbook (creates loop B, but message handler from loop A is dead)

Result: Responses from VM were sent but never processed, causing 30-second timeout.

## Solution
Consolidated event loops by creating async helper methods that execute the entire flow (session retrieval + execution) in ONE `asyncio.run()` call.

## Changes Made

### File: `adare/adare/services/devmode_service.py`

#### 1. execute_action() Method
- **Added:** `_execute_action_async()` helper (lines 649-689)
- **Modified:** `execute_action()` to use single asyncio.run() call (lines 691-751)

#### 2. execute_playbook() Method
- **Added:** `_execute_playbook_async()` helper (lines 753-796)
- **Modified:** `execute_playbook()` to use single asyncio.run() call (lines 798-877)

#### 3. reset_soft() Method
- **Added:** `_reset_soft_async()` helper (lines 883-908)
- **Modified:** `reset_soft()` to use single asyncio.run() call (lines 910-957)

#### 4. reset_hard() Method
- **Added:** `_reset_hard_async()` helper (lines 959-984)
- **Modified:** `reset_hard()` to use single asyncio.run() call (lines 986-1033)

#### 5. create_checkpoint() Method
- **Added:** `_create_checkpoint_async()` helper (lines 1039-1061)
- **Modified:** `create_checkpoint()` to use single asyncio.run() call (lines 1063-1105)

#### 6. restore_checkpoint() Method
- **Added:** `_restore_checkpoint_async()` helper (lines 1107-1129)
- **Modified:** `restore_checkpoint()` to use single asyncio.run() call (lines 1131-1175)

## Pattern Used

Each refactored method follows this pattern:

```python
async def _method_async(self, request):
    """Execute operation in a single event loop."""
    # Get or restore session (stays in same event loop)
    session = await self._manager.get_or_restore_session(...)
    if not session:
        raise RuntimeError("Session not found")

    # Execute operation (in same event loop!)
    result = await session.operation(...)
    return result

def method(self, request):
    """Public method with Result return type."""
    try:
        # CRITICAL: Execute entire flow in ONE asyncio.run() call
        # This keeps the WebSocket message_handler_task alive throughout execution
        result = asyncio.run(self._method_async(request))
        return Result.ok(result)
    except RuntimeError as e:
        return Result.fail("SESSION_NOT_FOUND", str(e), [...])
    except Exception as e:
        return Result.fail("ERROR", str(e), [...])
```

## Testing Recommendations

### 1. Basic Playbook Execution
```bash
# Start a dev session
adare dev start <experiment> -e <environment>

# Execute a playbook with a shell command
adare dev playbook -f p.yml
```

**Expected:** Command completes in actual execution time (~8 seconds), not timeout (30 seconds)

### 2. Long-Running Command
```yaml
actions:
  - command: sleep 15
    timeout: 30
```

**Expected:** Completes in ~15 seconds

### 3. Multiple Commands in Sequence
```yaml
actions:
  - command: echo "First command"
  - command: echo "Second command"
  - command: echo "Third command"
```

**Expected:** All commands complete successfully

### 4. WebSocket Stability
Check VM logs (`adarevm.log`):
- Commands complete successfully
- Responses are sent back
- No "Client disconnected" messages during execution
- Connection only closes after playbook completes

## Success Criteria
- ✅ No timeouts for commands that complete successfully on the VM
- ✅ Execution times match actual command duration (not fixed 30s timeout)
- ✅ WebSocket stays connected throughout playbook execution
- ✅ No "Client disconnected" messages in VM logs during execution
- ✅ All dev mode operations (action, playbook, reset, checkpoint) work consistently

## Notes
- `delete_checkpoint()` was NOT modified as it only has one asyncio.run() call
- `list_checkpoints()` was NOT modified as it's read-only and doesn't use asyncio
- Each command can still have its own event loop (we don't need to maintain loops across multiple `adare dev playbook` invocations)
- The fix only ensures ONE loop per operation execution
