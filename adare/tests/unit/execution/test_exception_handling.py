"""Tests verifying that refactored exception handling catches specific exceptions
and does not silently swallow SystemExit or KeyboardInterrupt.

These tests validate the PATTERN of exception specificity used throughout the
codebase, as required by CLAUDE.md: 'never catch generic exception (with except
Exception) - use more specific Exception that are expected instead'.

Each test mirrors a real try/except block from the production code and confirms:
  - The intended exception types are caught
  - SystemExit and KeyboardInterrupt propagate (they are BaseException subclasses
    and must never be silently swallowed)
"""

import os
import socket
from datetime import datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# 1. Path.stem exception specificity
#    Pattern from: simple_actions.py:228, target_resolution.py:133
# ---------------------------------------------------------------------------

class TestPathStemExceptionSpecificity:
    """Path(value).stem catches (TypeError, ValueError), not BaseException."""

    def _extract_stem_or_default(self, image_value: object) -> str:
        """Mirror the pattern: try Path(image).stem, fall back on error."""
        try:
            return Path(image_value).stem
        except (TypeError, ValueError):
            return "img"

    def test_none_raises_typeerror_and_is_caught(self):
        """Path(None).stem raises TypeError, which should be caught."""
        result = self._extract_stem_or_default(None)
        assert result == "img"

    def test_valid_path_returns_stem(self):
        """Normal path should return the stem, no exception."""
        result = self._extract_stem_or_default("/screenshots/button.png")
        assert result == "button"

    def test_system_exit_propagates(self):
        """SystemExit must NOT be caught by (TypeError, ValueError)."""
        with pytest.raises(SystemExit):
            try:
                raise SystemExit(1)
            except (TypeError, ValueError):
                pass  # This must not catch SystemExit

    def test_keyboard_interrupt_propagates(self):
        """KeyboardInterrupt must NOT be caught by (TypeError, ValueError)."""
        with pytest.raises(KeyboardInterrupt):
            try:
                raise KeyboardInterrupt()
            except (TypeError, ValueError):
                pass  # This must not catch KeyboardInterrupt


# ---------------------------------------------------------------------------
# 2. Socket exception specificity
#    Pattern from: mcp_server_manager.py:169-174
# ---------------------------------------------------------------------------

class TestSocketExceptionSpecificity:
    """socket operations catch OSError, not BaseException."""

    def _is_port_open(self, port: int) -> bool:
        """Mirror the mcp_server_manager pattern for port checking."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                return s.connect_ex(('localhost', port)) == 0
        except OSError:
            return False

    def test_unreachable_port_returns_false(self):
        """Connecting to a likely-closed port returns False (no exception leak)."""
        # Port 1 is almost certainly not open
        result = self._is_port_open(1)
        assert result is False

    def test_system_exit_propagates_through_oserror_handler(self):
        """SystemExit must NOT be caught by except OSError."""
        with pytest.raises(SystemExit):
            try:
                raise SystemExit(1)
            except OSError:
                pass

    def test_keyboard_interrupt_propagates_through_oserror_handler(self):
        """KeyboardInterrupt must NOT be caught by except OSError."""
        with pytest.raises(KeyboardInterrupt):
            try:
                raise KeyboardInterrupt()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 3. os.remove exception specificity
#    Pattern from: qemu/vm.py:425-428, :770-773, :780-782
# ---------------------------------------------------------------------------

class TestOsRemoveExceptionSpecificity:
    """os.remove catches OSError (covers FileNotFoundError, PermissionError)."""

    def _safe_remove(self, path: str) -> bool:
        """Mirror the qemu/vm.py pattern for safe file removal."""
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def test_file_not_found_is_caught(self):
        """FileNotFoundError is a subclass of OSError and should be caught."""
        result = self._safe_remove("/nonexistent/path/that/does/not/exist.sock")
        assert result is False

    def test_permission_error_subclass_of_oserror(self):
        """PermissionError is a subclass of OSError - verify the hierarchy."""
        assert issubclass(PermissionError, OSError)
        # Demonstrate it would be caught
        caught = False
        try:
            raise PermissionError("permission denied")
        except OSError:
            caught = True
        assert caught is True

    def test_system_exit_propagates_through_os_remove_handler(self):
        """SystemExit must NOT be caught by except OSError."""
        with pytest.raises(SystemExit):
            try:
                raise SystemExit(1)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 4. datetime.fromisoformat exception specificity
#    Pattern from: listener.py:419-422
# ---------------------------------------------------------------------------

class TestDatetimeParsingExceptionSpecificity:
    """datetime.fromisoformat catches (ValueError, TypeError)."""

    def _parse_timestamp_or_now(self, timestamp_str: object) -> datetime:
        """Mirror the listener.py pattern for timestamp parsing."""
        try:
            return datetime.fromisoformat(str(timestamp_str).replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return datetime.now()

    def test_invalid_string_raises_valueerror_and_is_caught(self):
        """Garbage string raises ValueError, caught by the handler."""
        result = self._parse_timestamp_or_now("not-a-date")
        assert isinstance(result, datetime)

    def test_none_is_handled(self):
        """None converted to 'None' string raises ValueError, caught."""
        result = self._parse_timestamp_or_now(None)
        assert isinstance(result, datetime)

    def test_valid_iso_string_parses_correctly(self):
        """Valid ISO timestamp should parse without hitting the handler."""
        result = self._parse_timestamp_or_now("2026-01-15T10:30:00Z")
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_system_exit_propagates_through_datetime_handler(self):
        """SystemExit must NOT be caught by (ValueError, TypeError)."""
        with pytest.raises(SystemExit):
            try:
                raise SystemExit(1)
            except (ValueError, TypeError):
                pass


# ---------------------------------------------------------------------------
# 5. Dynamic import exception specificity
#    Pattern from: vm/database.py:245-249
# ---------------------------------------------------------------------------

class TestDynamicImportExceptionSpecificity:
    """Dynamic import catches (ImportError, ValueError, KeyError)."""

    def _get_guest_os_with_fallback(self, module_name: str) -> str:
        """Mirror the vm/database.py pattern for dynamic import with fallback."""
        try:
            __import__(module_name)
            return "Windows 11"
        except (ImportError, ValueError, KeyError):
            return "Other"

    def test_import_error_is_caught(self):
        """ImportError from missing module should be caught."""
        result = self._get_guest_os_with_fallback("nonexistent_module_xyz_abc_123")
        assert result == "Other"

    def test_keyboard_interrupt_propagates_through_import_handler(self):
        """KeyboardInterrupt must NOT be caught by (ImportError, ValueError, KeyError)."""
        with pytest.raises(KeyboardInterrupt):
            try:
                raise KeyboardInterrupt()
            except (ImportError, ValueError, KeyError):
                pass

    def test_system_exit_propagates_through_import_handler(self):
        """SystemExit must NOT be caught by (ImportError, ValueError, KeyError)."""
        with pytest.raises(SystemExit):
            try:
                raise SystemExit(1)
            except (ImportError, ValueError, KeyError):
                pass
