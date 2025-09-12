# external imports
import attrs
import platform
from typing import ClassVar, Optional, Union

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter
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


# Windows-only registry tests
@attrs.define
class RegistryKeyExistsParameter(Parameter):
    key_path: str  # Full registry path like "HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion"

@attrs.define
class RegistryKeyExists(BasicTest):
    testname: ClassVar[str] = 'registry_key_exists'
    testdescription: ClassVar[str] = 'tests if Windows registry key exists (Windows only)'

    name: str
    parameter: RegistryKeyExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_registry_path(self, key_path):
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

    def test(self):
        if platform.system() != 'Windows':
            return TestResult.execution_error(None, "This test only runs on Windows")
        
        if not WINREG_AVAILABLE:
            return TestResult.execution_error(None, "winreg module not available")
            
        try:
            # Handle variables in key path
            key_path = self.parameter.key_path
            if self.has_placeholders(key_path):
                key_path = self.resolve_variables(key_path)
            
            try:
                hive, subkey = self._parse_registry_path(key_path)
                
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

@attrs.define
class RegistryValueMatchesParameter(Parameter):
    key_path: str  # Registry key path
    value_name: str  # Value name within the key
    expected_value: Union[str, int, bytes]
    value_type: Optional[str] = None  # REG_SZ, REG_DWORD, REG_BINARY, etc.

@attrs.define
class RegistryValueMatches(BasicTest):
    testname: ClassVar[str] = 'registry_value_matches'
    testdescription: ClassVar[str] = 'tests if Windows registry value matches expected value (Windows only)'

    name: str
    parameter: RegistryValueMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_registry_path(self, key_path):
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

    def _format_registry_type(self, reg_type):
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

    def test(self):
        if platform.system() != 'Windows':
            return TestResult.execution_error(None, "This test only runs on Windows")
        
        if not WINREG_AVAILABLE:
            return TestResult.execution_error(None, "winreg module not available")
            
        try:
            # Handle variables in paths and values
            key_path = self.parameter.key_path
            value_name = self.parameter.value_name
            expected_value = self.parameter.expected_value
            
            if self.has_placeholders(key_path):
                key_path = self.resolve_variables(key_path)
            
            if self.has_placeholders(value_name):
                value_name = self.resolve_variables(value_name)
            
            # Handle expected value variables (preserve type where possible)
            if isinstance(expected_value, str) and self.has_placeholders(expected_value):
                expected_value = self.resolve_variables(str(expected_value))
                # Try to convert back to appropriate type
                if isinstance(expected_value, str) and expected_value.isdigit():
                    expected_value = int(expected_value)
            
            try:
                hive, subkey = self._parse_registry_path(key_path)
                
                try:
                    key = winreg.OpenKey(hive, subkey)
                    actual_value, reg_type = winreg.QueryValueEx(key, value_name)
                    winreg.CloseKey(key)
                    
                    # Type checking if specified
                    if self.parameter.value_type:
                        expected_type_name = self.parameter.value_type.upper()
                        actual_type_name = self._format_registry_type(reg_type)
                        
                        if expected_type_name != actual_type_name:
                            return TestResult.failed([f'registry value type mismatch. Expected: {expected_type_name}, Got: {actual_type_name}'])
                    
                    # Value comparison
                    if actual_value == expected_value:
                        return TestResult.success([f'registry value matches: {actual_value} ({self._format_registry_type(reg_type)})'])
                    else:
                        return TestResult.failed([f'registry value mismatch. Expected: {expected_value}, Got: {actual_value} ({self._format_registry_type(reg_type)})'])
                        
                except FileNotFoundError:
                    return TestResult.failed([f'registry key or value does not exist: {key_path}\\{value_name}'])
                except PermissionError:
                    return TestResult.execution_error(None, f"Permission denied accessing registry: {key_path}\\{value_name}")
                    
            except ValueError as e:
                return TestResult.execution_error(e, "Registry path parsing error")
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in registry value matches test")