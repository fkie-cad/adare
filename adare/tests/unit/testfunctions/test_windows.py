"""Comprehensive unit tests for Windows testfunctions."""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import from adarelib.constants as required
from adarelib.constants import StatusEnum

# Import testfunctions dynamically
from adare.helperfunctions.module import import_module_from_pyfile

# Load Windows testfunctions module
windows_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "windows" / "windows.py"
windows_module = import_module_from_pyfile(windows_module_path)

# Extract testfunctions from module
RegistryKeyExists = windows_module.RegistryKeyExists
RegistryKeyExistsParameter = windows_module.RegistryKeyExistsParameter
RegistryValueMatches = windows_module.RegistryValueMatches
RegistryValueMatchesParameter = windows_module.RegistryValueMatchesParameter

# Import test helpers
import importlib.util
helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error


# ============================================================================
# Mock winreg module
# ============================================================================

class MockWinreg:
    """Mock winreg module for testing on non-Windows platforms."""

    # Mock registry hive constants
    HKEY_CLASSES_ROOT = 0x80000000
    HKEY_CURRENT_USER = 0x80000001
    HKEY_LOCAL_MACHINE = 0x80000002
    HKEY_USERS = 0x80000003
    HKEY_CURRENT_CONFIG = 0x80000005

    # Mock registry type constants
    REG_SZ = 1
    REG_EXPAND_SZ = 2
    REG_BINARY = 3
    REG_DWORD = 4
    REG_DWORD_LITTLE_ENDIAN = 4
    REG_DWORD_BIG_ENDIAN = 5
    REG_LINK = 6
    REG_MULTI_SZ = 7
    REG_RESOURCE_LIST = 8

    @staticmethod
    def OpenKey(hive, subkey):
        """Mock OpenKey function."""
        raise NotImplementedError("OpenKey should be mocked in tests")

    @staticmethod
    def QueryValueEx(key, value_name):
        """Mock QueryValueEx function."""
        raise NotImplementedError("QueryValueEx should be mocked in tests")

    @staticmethod
    def CloseKey(key):
        """Mock CloseKey function."""
        pass


# ============================================================================
# RegistryKeyExists Tests
# ============================================================================

class TestRegistryKeyExists:
    """Tests for RegistryKeyExists testfunction."""

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_success_hklm(self, mock_winreg, mock_platform):
        """Test successful registry key existence check with HKEY_LOCAL_MACHINE."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.CloseKey = MagicMock()

        test = RegistryKeyExists(
            name="test_key_exists",
            parameter=RegistryKeyExistsParameter(
                key_path=r"HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "registry key exists" in result.details[0]
        mock_winreg.OpenKey.assert_called_once()
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_success_hklm_abbreviation(self, mock_winreg, mock_platform):
        """Test successful registry key existence with HKLM abbreviation."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.CloseKey = MagicMock()

        test = RegistryKeyExists(
            name="test_key_exists",
            parameter=RegistryKeyExistsParameter(
                key_path=r"HKLM\Software\Microsoft"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "registry key exists" in result.details[0]

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_success_hkcu(self, mock_winreg, mock_platform):
        """Test successful registry key existence with HKEY_CURRENT_USER."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.CloseKey = MagicMock()

        test = RegistryKeyExists(
            name="test_key_exists",
            parameter=RegistryKeyExistsParameter(
                key_path=r"HKEY_CURRENT_USER\Software\Classes"
            )
        )
        result = test.test()

        assert_test_success(result)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_success_forward_slash(self, mock_winreg, mock_platform):
        """Test successful registry key existence with forward slash path separator."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.CloseKey = MagicMock()

        test = RegistryKeyExists(
            name="test_key_exists",
            parameter=RegistryKeyExistsParameter(
                key_path="HKLM/Software/Microsoft/Windows"
            )
        )
        result = test.test()

        assert_test_success(result)
        # Verify that forward slashes were converted to backslashes
        assert "registry key exists" in result.details[0]

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_failure_not_found(self, mock_winreg, mock_platform):
        """Test failure when registry key doesn't exist."""
        mock_winreg.OpenKey = MagicMock(side_effect=FileNotFoundError("Key not found"))

        test = RegistryKeyExists(
            name="test_key_exists",
            parameter=RegistryKeyExistsParameter(
                key_path=r"HKLM\Software\NonExistent\Key"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_error_permission_denied(self, mock_winreg, mock_platform):
        """Test execution error when permission is denied."""
        mock_winreg.OpenKey = MagicMock(side_effect=PermissionError("Access denied"))

        test = RegistryKeyExists(
            name="test_key_exists",
            parameter=RegistryKeyExistsParameter(
                key_path=r"HKLM\Software\Restricted"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert any("Permission denied" in detail for detail in result.details)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_error_invalid_hive(self, mock_winreg, mock_platform):
        """Test execution error with invalid registry hive."""
        test = RegistryKeyExists(
            name="test_key_exists",
            parameter=RegistryKeyExistsParameter(
                key_path=r"INVALID_HIVE\Software\Test"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert any("Registry path parsing error" in detail for detail in result.details)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_error_invalid_path_format(self, mock_winreg, mock_platform):
        """Test execution error with invalid path format."""
        test = RegistryKeyExists(
            name="test_key_exists",
            parameter=RegistryKeyExistsParameter(
                key_path="InvalidPathWithoutBackslash"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert any("Registry path parsing error" in detail for detail in result.details)

    @patch('platform.system', return_value='Linux')
    def test_registry_key_exists_error_non_windows(self, mock_platform):
        """Test execution error when run on non-Windows platform."""
        test = RegistryKeyExists(
            name="test_key_exists",
            parameter=RegistryKeyExistsParameter(
                key_path=r"HKLM\Software\Test"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert any("only runs on Windows" in detail for detail in result.details)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_with_placeholder(self, mock_winreg, mock_platform, variable_metadata_simple):
        """Test registry key existence with placeholder resolution."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.CloseKey = MagicMock()

        def mock_resolve_variables(self, text):
            """Mock resolve_variables to replace {{VAR1}} with value1"""
            if '{{VAR1}}' in text:
                return text.replace('{{VAR1}}', 'value1')
            if '{{VAR2}}' in text:
                return text.replace('{{VAR2}}', 'value2')
            return text

        # Temporarily add the method to the class
        RegistryKeyExists.resolve_variables = mock_resolve_variables
        try:
            test = RegistryKeyExists(
                name="test_key_exists",
                parameter=RegistryKeyExistsParameter(
                    key_path=r"HKLM\Software\{{VAR1}}"
                ),
                variable_metadata=variable_metadata_simple
            )
            result = test.test()
        finally:
            # Clean up
            if hasattr(RegistryKeyExists, 'resolve_variables'):
                delattr(RegistryKeyExists, 'resolve_variables')

        assert_test_success(result)
        # Verify that placeholder was resolved
        call_args = mock_winreg.OpenKey.call_args
        assert "value1" in str(call_args)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_key_exists_all_hives(self, mock_winreg, mock_platform):
        """Test all supported registry hives and abbreviations."""
        hives = [
            "HKEY_CLASSES_ROOT", "HKCR",
            "HKEY_CURRENT_USER", "HKCU",
            "HKEY_LOCAL_MACHINE", "HKLM",
            "HKEY_USERS", "HKU",
            "HKEY_CURRENT_CONFIG", "HKCC"
        ]

        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.CloseKey = MagicMock()

        for hive in hives:
            test = RegistryKeyExists(
                name=f"test_{hive}",
                parameter=RegistryKeyExistsParameter(
                    key_path=f"{hive}\\Software\\Test"
                )
            )
            result = test.test()
            assert_test_success(result)


# ============================================================================
# RegistryValueMatches Tests
# ============================================================================

class TestRegistryValueMatches:
    """Tests for RegistryValueMatches testfunction."""

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_success_string(self, mock_winreg, mock_platform):
        """Test successful registry value match with string type."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=("TestValue", MockWinreg.REG_SZ))
        mock_winreg.CloseKey = MagicMock()

        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"HKLM\Software\Test",
                value_name="TestName",
                expected_value="TestValue"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "registry value matches" in result.details[0]
        mock_winreg.OpenKey.assert_called_once()
        mock_winreg.QueryValueEx.assert_called_once_with(mock_key, "TestName")
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_success_dword(self, mock_winreg, mock_platform):
        """Test successful registry value match with DWORD type."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=(1, MockWinreg.REG_DWORD))
        mock_winreg.CloseKey = MagicMock()

        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"HKLM\Software\Test",
                value_name="DwordValue",
                expected_value=1
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "REG_DWORD" in result.details[0]

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_success_with_type_check(self, mock_winreg, mock_platform):
        """Test successful registry value match with explicit type checking."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=("TestValue", MockWinreg.REG_SZ))
        mock_winreg.CloseKey = MagicMock()

        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"HKLM\Software\Test",
                value_name="TestName",
                expected_value="TestValue",
                value_type="REG_SZ"
            )
        )
        result = test.test()

        assert_test_success(result)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_failure_value_mismatch(self, mock_winreg, mock_platform):
        """Test failure when registry value doesn't match."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=("ActualValue", MockWinreg.REG_SZ))
        mock_winreg.CloseKey = MagicMock()

        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"HKLM\Software\Test",
                value_name="TestName",
                expected_value="ExpectedValue"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "value mismatch" in result.details[0]
        assert "Expected: ExpectedValue" in result.details[0]
        assert "Got: ActualValue" in result.details[0]

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_failure_type_mismatch(self, mock_winreg, mock_platform):
        """Test failure when registry value type doesn't match."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=("TestValue", MockWinreg.REG_SZ))
        mock_winreg.CloseKey = MagicMock()

        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"HKLM\Software\Test",
                value_name="TestName",
                expected_value="TestValue",
                value_type="REG_DWORD"  # Expecting DWORD but got SZ
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "type mismatch" in result.details[0]
        assert "Expected: REG_DWORD" in result.details[0]
        assert "Got: REG_SZ" in result.details[0]

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_failure_key_not_found(self, mock_winreg, mock_platform):
        """Test failure when registry key doesn't exist."""
        mock_winreg.OpenKey = MagicMock(side_effect=FileNotFoundError("Key not found"))

        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"HKLM\Software\NonExistent",
                value_name="TestName",
                expected_value="TestValue"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_failure_value_not_found(self, mock_winreg, mock_platform):
        """Test failure when registry value doesn't exist."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(side_effect=FileNotFoundError("Value not found"))
        mock_winreg.CloseKey = MagicMock()

        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"HKLM\Software\Test",
                value_name="NonExistentValue",
                expected_value="TestValue"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_error_permission_denied(self, mock_winreg, mock_platform):
        """Test execution error when permission is denied."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(side_effect=PermissionError("Access denied"))
        mock_winreg.CloseKey = MagicMock()

        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"HKLM\Software\Restricted",
                value_name="SecureValue",
                expected_value="TestValue"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert any("Permission denied" in detail for detail in result.details)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_with_placeholder_key_path(self, mock_winreg, mock_platform, variable_metadata_simple):
        """Test registry value match with placeholder in key path."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=("TestValue", MockWinreg.REG_SZ))
        mock_winreg.CloseKey = MagicMock()

        def mock_resolve_variables(self, text):
            """Mock resolve_variables to replace placeholders"""
            if '{{VAR1}}' in text:
                return text.replace('{{VAR1}}', 'value1')
            if '{{VAR2}}' in text:
                return text.replace('{{VAR2}}', 'value2')
            return text

        # Temporarily add the method to the class
        RegistryValueMatches.resolve_variables = mock_resolve_variables
        try:
            test = RegistryValueMatches(
                name="test_value_matches",
                parameter=RegistryValueMatchesParameter(
                    key_path=r"HKLM\Software\{{VAR1}}",
                    value_name="TestName",
                    expected_value="TestValue"
                ),
                variable_metadata=variable_metadata_simple
            )
            result = test.test()

            assert_test_success(result)
            # Verify that placeholder was resolved
            call_args = mock_winreg.OpenKey.call_args
            assert "value1" in str(call_args)
        finally:
            # Clean up
            if hasattr(RegistryValueMatches, 'resolve_variables'):
                delattr(RegistryValueMatches, 'resolve_variables')

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_with_placeholder_value_name(self, mock_winreg, mock_platform, variable_metadata_simple):
        """Test registry value match with placeholder in value name."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=("TestValue", MockWinreg.REG_SZ))
        mock_winreg.CloseKey = MagicMock()

        def mock_resolve_variables(self, text):
            """Mock resolve_variables to replace placeholders"""
            if '{{VAR1}}' in text:
                return text.replace('{{VAR1}}', 'value1')
            if '{{VAR2}}' in text:
                return text.replace('{{VAR2}}', 'value2')
            return text

        # Temporarily add the method to the class
        RegistryValueMatches.resolve_variables = mock_resolve_variables
        try:
            test = RegistryValueMatches(
                name="test_value_matches",
                parameter=RegistryValueMatchesParameter(
                    key_path=r"HKLM\Software\Test",
                    value_name="{{VAR1}}",
                    expected_value="TestValue"
                ),
                variable_metadata=variable_metadata_simple
            )
            result = test.test()

            assert_test_success(result)
            # Verify that placeholder was resolved
            call_args = mock_winreg.QueryValueEx.call_args
            assert "value1" in str(call_args)
        finally:
            # Clean up
            if hasattr(RegistryValueMatches, 'resolve_variables'):
                delattr(RegistryValueMatches, 'resolve_variables')

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_with_placeholder_expected_value(self, mock_winreg, mock_platform, variable_metadata_simple):
        """Test registry value match with placeholder in expected value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=("value1", MockWinreg.REG_SZ))
        mock_winreg.CloseKey = MagicMock()

        def mock_resolve_variables(self, text):
            """Mock resolve_variables to replace placeholders"""
            if '{{VAR1}}' in text:
                return text.replace('{{VAR1}}', 'value1')
            if '{{VAR2}}' in text:
                return text.replace('{{VAR2}}', 'value2')
            return text

        # Temporarily add the method to the class
        RegistryValueMatches.resolve_variables = mock_resolve_variables
        try:
            test = RegistryValueMatches(
                name="test_value_matches",
                parameter=RegistryValueMatchesParameter(
                    key_path=r"HKLM\Software\Test",
                    value_name="TestName",
                    expected_value="{{VAR1}}"
                ),
                variable_metadata=variable_metadata_simple
            )
            result = test.test()

            assert_test_success(result)
        finally:
            # Clean up
            if hasattr(RegistryValueMatches, 'resolve_variables'):
                delattr(RegistryValueMatches, 'resolve_variables')

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_forward_slash(self, mock_winreg, mock_platform):
        """Test registry value match with forward slash path separator."""
        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=("TestValue", MockWinreg.REG_SZ))
        mock_winreg.CloseKey = MagicMock()

        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path="HKLM/Software/Test",
                value_name="TestName",
                expected_value="TestValue"
            )
        )
        result = test.test()

        assert_test_success(result)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_various_types(self, mock_winreg, mock_platform):
        """Test registry value match with various registry types."""
        type_tests = [
            (MockWinreg.REG_SZ, "string", "REG_SZ"),
            (MockWinreg.REG_EXPAND_SZ, "expanded", "REG_EXPAND_SZ"),
            (MockWinreg.REG_BINARY, b"binary", "REG_BINARY"),
            (MockWinreg.REG_DWORD_LITTLE_ENDIAN, 42, "REG_DWORD_LITTLE_ENDIAN"),
            (MockWinreg.REG_MULTI_SZ, ["a", "b"], "REG_MULTI_SZ"),
        ]

        for reg_type, test_value, type_name in type_tests:
            mock_key = MagicMock()
            mock_winreg.OpenKey = MagicMock(return_value=mock_key)
            mock_winreg.QueryValueEx = MagicMock(return_value=(test_value, reg_type))
            mock_winreg.CloseKey = MagicMock()

            test = RegistryValueMatches(
                name=f"test_{type_name}",
                parameter=RegistryValueMatchesParameter(
                    key_path=r"HKLM\Software\Test",
                    value_name="Value",
                    expected_value=test_value,
                    value_type=type_name
                )
            )
            result = test.test()
            assert_test_success(result)

    @patch('platform.system', return_value='Linux')
    def test_registry_value_matches_error_non_windows(self, mock_platform):
        """Test execution error when run on non-Windows platform."""
        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"HKLM\Software\Test",
                value_name="TestName",
                expected_value="TestValue"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert any("only runs on Windows" in detail for detail in result.details)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_error_invalid_hive(self, mock_winreg, mock_platform):
        """Test execution error with invalid registry hive."""
        test = RegistryValueMatches(
            name="test_value_matches",
            parameter=RegistryValueMatchesParameter(
                key_path=r"INVALID_HIVE\Software\Test",
                value_name="TestName",
                expected_value="TestValue"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert any("Registry path parsing error" in detail for detail in result.details)

    @patch('platform.system', return_value='Windows')
    @patch.object(windows_module, 'WINREG_AVAILABLE', True)
    @patch.object(windows_module, 'winreg', new_callable=lambda: MockWinreg)
    def test_registry_value_matches_all_hives(self, mock_winreg, mock_platform):
        """Test registry value match with all supported hives."""
        hives = [
            "HKEY_CLASSES_ROOT", "HKCR",
            "HKEY_CURRENT_USER", "HKCU",
            "HKEY_LOCAL_MACHINE", "HKLM",
            "HKEY_USERS", "HKU",
            "HKEY_CURRENT_CONFIG", "HKCC"
        ]

        mock_key = MagicMock()
        mock_winreg.OpenKey = MagicMock(return_value=mock_key)
        mock_winreg.QueryValueEx = MagicMock(return_value=("TestValue", MockWinreg.REG_SZ))
        mock_winreg.CloseKey = MagicMock()

        for hive in hives:
            test = RegistryValueMatches(
                name=f"test_{hive}",
                parameter=RegistryValueMatchesParameter(
                    key_path=f"{hive}\\Software\\Test",
                    value_name="TestName",
                    expected_value="TestValue"
                )
            )
            result = test.test()
            assert_test_success(result)
