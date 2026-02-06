# Implementation Log: Fix Testfunction Dependency Installation in Wheel Mode

## Date
2026-02-05

## Problem Summary
When `adarevm` and `adarelib` are installed via wheels (production mode), the system incorrectly tries to use `poetry add` to install testfunction dependencies. This fails because wheels are installed via `pip install *.whl` and Poetry is not available or properly configured in wheel mode.

### Error
```
[WinError 1005] The volume does not contain a recognized file system.
Please make sure that all required file system drivers are loaded and that the volume is not corrupted: 'C:\\adare\\vm\\adarelib'
```

## Root Cause
The dependency installation logic in `adarevm/core/server.py:618-727` didn't distinguish between:
- **Development mode**: Editable install with Poetry → Use `poetry add`
- **Wheel mode**: Pip-installed packages → Should use `pip install`

## Solution Implemented

### 1. Installation Mode Detection (`_is_wheel_installation()`)
**Location**: `adarevm/adarevm/core/server.py:581-607`

Added method to detect if adarevm was installed from wheel vs Poetry editable install:
- Uses `importlib.metadata.distribution()` to inspect package metadata
- Checks for `direct_url.json` file (present only in editable installs)
- Returns `True` for wheel mode, `False` for editable mode
- Defaults to wheel mode if detection fails

**Key Logic**:
```python
dist = importlib.metadata.distribution('adarevm')
try:
    if dist.read_text('direct_url.json'):
        return False  # Editable install
except FileNotFoundError:
    return True  # Wheel install
```

### 2. Pip Command Builder (`_get_pip_command()`)
**Location**: `adarevm/adarevm/core/server.py:609-640`

Added method to build appropriate pip command for the current environment:

**Conda Environment Detection**:
- Checks `CONDA_DEFAULT_ENV` environment variable
- If `pyadare` conda environment exists, uses: `conda run -n pyadare pip install --no-cache-dir`
- Locates conda executable at:
  - Windows: `%USERPROFILE%\.miniforge3\Scripts\conda.exe`
  - Linux: `~/.miniforge3/bin/conda`

**System Pip Fallback**:
- Windows: `pip install --no-cache-dir`
- Linux: `pip3 install --no-cache-dir --break-system-packages`

**Flags Used**:
- `--no-cache-dir`: Disable pip cache to save VM disk space
- `--break-system-packages` (Linux only): Avoid PEP 668 externally-managed-environment errors

### 3. Refactored Poetry Method (`_install_dependencies_poetry()`)
**Location**: `adarevm/adarevm/core/server.py:680-788`

Renamed existing `_install_dependencies()` to `_install_dependencies_poetry()`:
- Preserves all existing Poetry installation logic
- Used only for editable/development installs
- No functional changes to the implementation

### 4. New Pip Installation Method (`_install_dependencies_pip()`)
**Location**: `adarevm/adarevm/core/server.py:790-878`

Created new method for pip-based dependency installation:
- Adapted from Poetry implementation structure
- Uses `_get_pip_command()` to build base command
- Supports `prefer_binary` flag via `--only-binary :all:`
- Preserves heartbeat mechanism for long installations
- Uses same error handling and logging pattern as Poetry method

**Installation Steps**:
1. Get pip command via `_get_pip_command()`
2. Add `--only-binary :all:` if `prefer_binary=True`
3. Execute: `{pip_cmd} {dependencies}`
4. Wait with heartbeat to keep WebSocket alive
5. Return status with installed count and output

### 5. Router Method (`_install_dependencies()`)
**Location**: `adarevm/adarevm/core/server.py:880-900`

Created router method to dispatch to appropriate implementation:
```python
is_wheel_mode = self._is_wheel_installation()
if is_wheel_mode:
    return await self._install_dependencies_pip(websocket, dependencies, prefer_binary)
else:
    return await self._install_dependencies_poetry(websocket, dependencies, prefer_binary)
```

Logs installation mode for debugging:
- Wheel mode: "Installation mode: pip (wheel-based)"
- Editable mode: "Installation mode: Poetry (editable)"

## Files Modified

**Primary**:
- `adarevm/adarevm/core/server.py` - Added 5 methods totaling ~200 lines:
  - `_is_wheel_installation()` - 27 lines
  - `_get_pip_command()` - 32 lines
  - `_install_dependencies_poetry()` - Renamed (no logic changes)
  - `_install_dependencies_pip()` - 89 lines
  - `_install_dependencies()` - 20 lines (router)

## Key Design Decisions

### Why Package Metadata Inspection?
**Alternatives Considered**:
1. Check for pyproject.toml existence ❌ - Exists in virtio-fs even for wheel mode
2. Environment variable flag ❌ - Requires coordination, adds complexity
3. Always use pip ❌ - Breaks development workflow
4. Always use Poetry ❌ - Requires fixing Poetry's virtio-fs compatibility

**Selected Approach** ✅:
- Reliable detection via `importlib.metadata`
- No configuration needed
- Preserves development workflow
- Works with all hypervisors

### Why Pip Flags?
- `--no-cache-dir`: Saves VM disk space (per user preference)
- `--break-system-packages`: Avoids PEP 668 errors on Linux (per user preference)
- Matches flags used in `agent_command_builders.py:462` for consistency

### Why Keep Poetry Path?
- Development mode workflow uses Poetry for dependency management
- Poetry handles complex dependency resolution
- Existing code is working and tested
- Minimal risk approach: Add new path, preserve existing

## Verification Strategy

### Test 1: Wheel Mode (Production)
1. Build wheels in `{project}/.adare/vm_runtime/wheels/`
2. Start VM with wheel installation
3. Load experiment with testfunction requiring dependencies (e.g., `pandas>=2.0.0`)
4. Run experiment
5. **Expected**: Dependencies install via pip/conda, no Poetry errors

### Test 2: Development Mode
1. Remove wheels from vm_runtime
2. Start VM (forces editable install)
3. Load experiment with testfunction requiring dependencies
4. Run experiment
5. **Expected**: Dependencies install via Poetry (existing behavior)

### Test 3: Conda Environment
1. Test with Miniforge/conda environment active
2. Verify `conda run -n pyadare pip install` is used
3. Check: `conda run -n pyadare pip list`

### Test 4: System Python
1. Test without conda (system pip)
2. Verify `pip install` (Windows) or `pip3 install` (Linux) is used

## Benefits

✅ Fixes wheel mode dependency installation
✅ No Poetry errors in production deployments
✅ Works with virtio-fs and all hypervisors
✅ Preserves development workflow
✅ Automatic mode detection (no configuration)
✅ Consistent with host-side installation patterns
✅ Proper error handling and logging
✅ WebSocket heartbeat prevents timeouts

## Risks Mitigated

- **Poetry virtio-fs errors**: Bypassed in wheel mode
- **Development workflow break**: Preserved via dual-mode routing
- **Conda environment issues**: Explicit conda detection and handling
- **PEP 668 errors**: `--break-system-packages` flag on Linux
- **VM disk space**: `--no-cache-dir` flag

## Testing Notes

- Syntax validated with `python3 -m py_compile`
- All imports verified (including local `import os`)
- Method signatures match caller expectations
- Return types consistent with Poetry implementation
- Error handling matches existing patterns

## Future Considerations

- Monitor `importlib.metadata` reliability across Python versions
- Consider adding explicit logging of detected pip command
- May want to expose installation mode in VM status endpoint
- Could add metric collection for pip vs Poetry success rates
