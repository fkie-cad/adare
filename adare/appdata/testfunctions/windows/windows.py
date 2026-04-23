# external imports
import platform
from typing import Optional, Union

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

# configure logging
import logging
log = logging.getLogger(__name__)


# Check if winreg is available (Windows only)
try:
    import winreg
    WINREG_AVAILABLE = True
except ImportError:
    WINREG_AVAILABLE = False
    winreg = None
    log.info("Windows registry tests not available (winreg module not found)")


# ============================================================================
# Module-level helpers (deduplicated)
# ============================================================================

def _parse_registry_path(key_path):
    """Parse registry path into root key and subkey"""
    if not WINREG_AVAILABLE:
        raise ImportError("winreg module not available")

    hive_mapping = {
        'HKEY_CLASSES_ROOT': winreg.HKEY_CLASSES_ROOT,
        'HKCR': winreg.HKEY_CLASSES_ROOT,
        'HKEY_CURRENT_USER': winreg.HKEY_CURRENT_USER,
        'HKCU': winreg.HKEY_CURRENT_USER,
        'HKEY_LOCAL_MACHINE': winreg.HKEY_LOCAL_MACHINE,
        'HKLM': winreg.HKEY_LOCAL_MACHINE,
        'HKEY_USERS': winreg.HKEY_USERS,
        'HKU': winreg.HKEY_USERS,
        'HKEY_CURRENT_CONFIG': winreg.HKEY_CURRENT_CONFIG,
        'HKCC': winreg.HKEY_CURRENT_CONFIG
    }

    # Split path
    parts = key_path.replace('/', '\\').split('\\', 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid registry path format: {key_path}")

    hive_name = parts[0].upper()
    subkey = parts[1]

    if hive_name not in hive_mapping:
        raise ValueError(f"Invalid registry hive: {hive_name}")

    return hive_mapping[hive_name], subkey


def _format_registry_type(reg_type):
    """Convert registry type to string name"""
    if not WINREG_AVAILABLE:
        raise ImportError("winreg module not available")

    type_mapping = {
        winreg.REG_SZ: 'REG_SZ',
        winreg.REG_EXPAND_SZ: 'REG_EXPAND_SZ',
        winreg.REG_BINARY: 'REG_BINARY',
        winreg.REG_DWORD: 'REG_DWORD',
        winreg.REG_DWORD_LITTLE_ENDIAN: 'REG_DWORD_LITTLE_ENDIAN',
        winreg.REG_DWORD_BIG_ENDIAN: 'REG_DWORD_BIG_ENDIAN',
        winreg.REG_LINK: 'REG_LINK',
        winreg.REG_MULTI_SZ: 'REG_MULTI_SZ',
        winreg.REG_RESOURCE_LIST: 'REG_RESOURCE_LIST',
    }
    return type_mapping.get(reg_type, f'UNKNOWN_TYPE_{reg_type}')


# ============================================================================
# Windows-only registry tests
# ============================================================================

@testfunction(
    name='registry_key_exists',
    description='tests if Windows registry key exists (Windows only)',
    category=HostModeCategory.QGA_PROBE,
)
def registry_key_exists(ctx: TestContext, key_path: str):
    if platform.system() != 'Windows':
        return TestResult.execution_error(None, "This test only runs on Windows")

    if not WINREG_AVAILABLE:
        return TestResult.execution_error(None, "winreg module not available")

    try:
        # Handle variables in key path
        if ctx.has_placeholders(key_path):
            key_path = ctx.resolve_variables(key_path)

        try:
            hive, subkey = _parse_registry_path(key_path)

            try:
                key = winreg.OpenKey(hive, subkey)
                winreg.CloseKey(key)
                return TestResult.success([f'registry key exists: {key_path}'])
            except FileNotFoundError:
                return TestResult.failed([f'registry key does not exist: {key_path}'])
            except PermissionError:
                return TestResult.execution_error(None, f"Permission denied accessing registry key: {key_path}")

        except ValueError as e:
            return TestResult.execution_error(e, "Registry path parsing error")

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in registry key exists test")


@testfunction(
    name='registry_value_matches',
    description='tests if Windows registry value matches expected value (Windows only)',
    category=HostModeCategory.QGA_PROBE,
)
def registry_value_matches(ctx: TestContext, key_path: str, value_name: str,
                           expected_value: str | int | bytes,
                           value_type: str | None = None):
    if platform.system() != 'Windows':
        return TestResult.execution_error(None, "This test only runs on Windows")

    if not WINREG_AVAILABLE:
        return TestResult.execution_error(None, "winreg module not available")

    try:
        # Handle variables in paths and values
        if ctx.has_placeholders(key_path):
            key_path = ctx.resolve_variables(key_path)

        if ctx.has_placeholders(value_name):
            value_name = ctx.resolve_variables(value_name)

        # Handle expected value variables (preserve type where possible)
        if isinstance(expected_value, str) and ctx.has_placeholders(expected_value):
            expected_value = ctx.resolve_variables(str(expected_value))
            # Try to convert back to appropriate type
            if isinstance(expected_value, str) and expected_value.isdigit():
                expected_value = int(expected_value)

        try:
            hive, subkey = _parse_registry_path(key_path)

            try:
                key = winreg.OpenKey(hive, subkey)
                actual_value, reg_type = winreg.QueryValueEx(key, value_name)
                winreg.CloseKey(key)

                # Type checking if specified
                if value_type:
                    expected_type_name = value_type.upper()
                    actual_type_name = _format_registry_type(reg_type)

                    if expected_type_name != actual_type_name:
                        return TestResult.failed([f'registry value type mismatch. Expected: {expected_type_name}, Got: {actual_type_name}'])

                # Value comparison
                if actual_value == expected_value:
                    return TestResult.success([f'registry value matches: {actual_value} ({_format_registry_type(reg_type)})'])
                return TestResult.failed([f'registry value mismatch. Expected: {expected_value}, Got: {actual_value} ({_format_registry_type(reg_type)})'])

            except FileNotFoundError:
                return TestResult.failed([f'registry key or value does not exist: {key_path}\\{value_name}'])
            except PermissionError:
                return TestResult.execution_error(None, f"Permission denied accessing registry: {key_path}\\{value_name}")

        except ValueError as e:
            return TestResult.execution_error(e, "Registry path parsing error")

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in registry value matches test")
