"""Comprehensive unit tests for standard testfunctions."""

import pytest
import os
import stat
import platform
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

pytestmark = pytest.mark.unit

# Add paths for imports
# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import from adarelib.constants as required
from adarelib.constants import StatusEnum

# Import testfunctions dynamically
from adare.helperfunctions.module import import_module_from_pyfile

# Load standard testfunctions module
standard_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "standard" / "standard.py"
standard_module = import_module_from_pyfile(standard_module_path)

# Extract testfunctions from module (decorator pattern: ._test_class / ._parameter_class)
FileExists = standard_module.file_exists._test_class
FileExistsParameter = standard_module.file_exists._parameter_class
FileDoesNotExist = standard_module.file_does_not_exist._test_class
FileDoesNotExistParameter = standard_module.file_does_not_exist._parameter_class
DirExists = standard_module.dir_exists._test_class
DirExistsParameter = standard_module.dir_exists._parameter_class
DirDoesNotExist = standard_module.dir_does_not_exist._test_class
DirDoesNotExistParameter = standard_module.dir_does_not_exist._parameter_class
DirContent = standard_module.dir_content._test_class
DirContentParameter = standard_module.dir_content._parameter_class
FileContentMatchesRegex = standard_module.file_content_matches_regex._test_class
FileContentMatchesRegexParameter = standard_module.file_content_matches_regex._parameter_class
FileContentEquals = standard_module.file_content_equals._test_class
FileContentEqualsParameter = standard_module.file_content_equals._parameter_class
FileHashMatches = standard_module.file_hash_matches._test_class
FileHashMatchesParameter = standard_module.file_hash_matches._parameter_class
FileTimestamps = standard_module.file_timestamps._test_class
FileTimestampsParameter = standard_module.file_timestamps._parameter_class
FilePermissions = standard_module.file_permissions._test_class
FilePermissionsParameter = standard_module.file_permissions._parameter_class
FileContentContains = standard_module.file_content_contains._test_class
FileContentContainsParameter = standard_module.file_content_contains._parameter_class

# Import test helpers (use direct path import)
helpers_path = Path(__file__).parent / "helpers.py"
import importlib.util
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error
create_file_with_content = helpers.create_file_with_content
create_binary_file = helpers.create_binary_file


# ============================================================================
# FileExists Tests
# ============================================================================

class TestFileExists:
    """Tests for FileExists testfunction."""

    def test_file_exists_success(self, tmp_path):
        """Test successful file existence check."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        test = FileExists(
            name="test_exists",
            parameter=FileExistsParameter(dst=str(test_file))
        )
        result = test.test()

        assert_test_success(result)
        assert str(test_file) in result.details[0]

    def test_file_exists_failure_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test_file = tmp_path / "nonexistent.txt"

        test = FileExists(
            name="test_exists",
            parameter=FileExistsParameter(dst=str(test_file))
        )
        result = test.test()

        assert_test_failed(result)
        # When path doesn't exist, resolve_globfilepath returns it as-is
        # Then FileExists checks if it's a file, which it's not (doesn't exist)
        assert "does not exist" in result.details[0] or "matched but none are files" in result.details[0]

    def test_file_exists_failure_is_directory(self, tmp_path):
        """Test failure when path exists but is a directory."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        test = FileExists(
            name="test_exists",
            parameter=FileExistsParameter(dst=str(test_dir))
        )
        result = test.test()

        assert_test_failed(result)
        # When path is a directory, it reports "matched but none are files"
        assert "matched but none are files" in result.details[0] or "not a file" in result.details[0]

    @pytest.mark.parametrize("match_mode", ["single", "any"])
    def test_file_exists_glob_single_match(self, tmp_path, match_mode):
        """Test glob pattern with single file match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        test = FileExists(
            name="test_exists",
            parameter=FileExistsParameter(
                dst=str(tmp_path / "*.txt"),
                match_mode=match_mode
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_exists_glob_multiple_match_any_mode(self, tmp_path):
        """Test glob pattern with multiple files in 'any' mode."""
        for i in range(3):
            (tmp_path / f"test{i}.txt").write_text(f"content{i}")

        test = FileExists(
            name="test_exists",
            parameter=FileExistsParameter(
                dst=str(tmp_path / "*.txt"),
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "3 file(s) found" in result.details[0]

    def test_file_exists_glob_multiple_match_single_mode_error(self, tmp_path):
        """Test glob pattern with multiple files in 'single' mode returns error."""
        for i in range(3):
            (tmp_path / f"test{i}.txt").write_text(f"content{i}")

        test = FileExists(
            name="test_exists",
            parameter=FileExistsParameter(
                dst=str(tmp_path / "*.txt"),
                match_mode="single"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert "no unambiguous file could be identified" in result.details[0]

    def test_file_exists_glob_no_match_any_mode(self, tmp_path):
        """Test glob pattern with no matches in 'any' mode."""
        test = FileExists(
            name="test_exists",
            parameter=FileExistsParameter(
                dst=str(tmp_path / "*.txt"),
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "no files match pattern" in result.details[0]


# ============================================================================
# FileDoesNotExist Tests
# ============================================================================

class TestFileDoesNotExist:
    """Tests for FileDoesNotExist testfunction."""

    def test_file_does_not_exist_success(self, tmp_path):
        """Test successful check that file doesn't exist."""
        test_file = tmp_path / "nonexistent.txt"

        test = FileDoesNotExist(
            name="test_not_exists",
            parameter=FileDoesNotExistParameter(dst=str(test_file))
        )
        result = test.test()

        assert_test_success(result)
        # Can be either message depending on whether path resolves
        assert "does not exist" in result.details[0] or "matched but none are files" in result.details[0]

    def test_file_does_not_exist_failure_file_exists(self, tmp_path):
        """Test failure when file exists."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        test = FileDoesNotExist(
            name="test_not_exists",
            parameter=FileDoesNotExistParameter(dst=str(test_file))
        )
        result = test.test()

        assert_test_failed(result)
        # The message includes the file path and says it exists
        assert "exist" in result.details[0].lower()

    def test_file_does_not_exist_success_path_is_directory(self, tmp_path):
        """Test success when path exists but is a directory (not a file)."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        test = FileDoesNotExist(
            name="test_not_exists",
            parameter=FileDoesNotExistParameter(dst=str(test_dir))
        )
        result = test.test()

        assert_test_success(result)

    def test_file_does_not_exist_glob_any_mode_success(self, tmp_path):
        """Test glob pattern with no file matches in 'any' mode."""
        test = FileDoesNotExist(
            name="test_not_exists",
            parameter=FileDoesNotExistParameter(
                dst=str(tmp_path / "*.txt"),
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "no files match pattern" in result.details[0]

    def test_file_does_not_exist_glob_any_mode_failure(self, tmp_path):
        """Test glob pattern with file matches in 'any' mode."""
        for i in range(2):
            (tmp_path / f"test{i}.txt").write_text(f"content{i}")

        test = FileDoesNotExist(
            name="test_not_exists",
            parameter=FileDoesNotExistParameter(
                dst=str(tmp_path / "*.txt"),
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "2 file(s) exist" in result.details[0]


# ============================================================================
# DirExists Tests
# ============================================================================

class TestDirExists:
    """Tests for DirExists testfunction."""

    def test_dir_exists_success(self, tmp_path):
        """Test successful directory existence check."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        test = DirExists(
            name="test_dir_exists",
            parameter=DirExistsParameter(dst=str(test_dir))
        )
        result = test.test()

        assert_test_success(result)
        assert str(test_dir) in result.details[0]

    def test_dir_exists_failure_not_found(self, tmp_path):
        """Test failure when directory doesn't exist."""
        test_dir = tmp_path / "nonexistent"

        test = DirExists(
            name="test_dir_exists",
            parameter=DirExistsParameter(dst=str(test_dir))
        )
        result = test.test()

        assert_test_failed(result)
        # Path is returned as-is but it's not a directory
        assert "does not exist" in result.details[0] or "matched but none are directories" in result.details[0]

    def test_dir_exists_failure_is_file(self, tmp_path):
        """Test failure when path exists but is a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        test = DirExists(
            name="test_dir_exists",
            parameter=DirExistsParameter(dst=str(test_file))
        )
        result = test.test()

        assert_test_failed(result)
        # Path is returned but it's not a directory
        assert "not a directory" in result.details[0] or "matched but none are directories" in result.details[0]

    def test_dir_exists_glob_multiple_match_any_mode(self, tmp_path):
        """Test glob pattern with multiple directories in 'any' mode."""
        for i in range(3):
            (tmp_path / f"dir{i}").mkdir()

        test = DirExists(
            name="test_dir_exists",
            parameter=DirExistsParameter(
                dst=str(tmp_path / "dir*"),
                match_mode="any"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "3 directory(ies) found" in result.details[0]


# ============================================================================
# DirDoesNotExist Tests
# ============================================================================

class TestDirDoesNotExist:
    """Tests for DirDoesNotExist testfunction."""

    def test_dir_does_not_exist_success(self, tmp_path):
        """Test successful check that directory doesn't exist."""
        test_dir = tmp_path / "nonexistent"

        test = DirDoesNotExist(
            name="test_dir_not_exists",
            parameter=DirDoesNotExistParameter(dst=str(test_dir))
        )
        result = test.test()

        assert_test_success(result)
        # Can be either message
        assert "does not exist" in result.details[0] or "matched but none are directories" in result.details[0]

    def test_dir_does_not_exist_failure_dir_exists(self, tmp_path):
        """Test failure when directory exists."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        test = DirDoesNotExist(
            name="test_dir_not_exists",
            parameter=DirDoesNotExistParameter(dst=str(test_dir))
        )
        result = test.test()

        assert_test_failed(result)
        # The message includes directory info
        assert "exist" in result.details[0].lower()

    def test_dir_does_not_exist_success_path_is_file(self, tmp_path):
        """Test success when path exists but is a file (not a directory)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        test = DirDoesNotExist(
            name="test_dir_not_exists",
            parameter=DirDoesNotExistParameter(dst=str(test_file))
        )
        result = test.test()

        assert_test_success(result)


# ============================================================================
# DirContent Tests
# ============================================================================

class TestDirContent:
    """Tests for DirContent testfunction."""

    def test_dir_content_success_exact_match(self, tmp_path):
        """Test successful directory content check with exact match."""
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir").mkdir()

        test = DirContent(
            name="test_dir_content",
            parameter=DirContentParameter(
                dst=str(tmp_path),
                files=["file1.txt", "file2.txt", "subdir"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_dir_content_failure_missing_files(self, tmp_path):
        """Test failure when expected files are missing."""
        (tmp_path / "file1.txt").write_text("content1")

        test = DirContent(
            name="test_dir_content",
            parameter=DirContentParameter(
                dst=str(tmp_path),
                files=["file1.txt", "file2.txt", "file3.txt"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "expected missing files" in result.details[0]
        assert "file2.txt" in result.details[0]

    def test_dir_content_success_with_additional_files(self, tmp_path):
        """Test behavior when directory has additional files.

        Note: The implementation only fails if expected files are missing.
        Additional files don't cause a failure, they succeed.
        """
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "extra.txt").write_text("extra")

        test = DirContent(
            name="test_dir_content",
            parameter=DirContentParameter(
                dst=str(tmp_path),
                files=["file1.txt"]
            )
        )
        result = test.test()

        # The implementation only checks if expected files are present
        # Additional files are noted in details but don't cause failure
        assert_test_success(result)

    def test_dir_content_error_dir_not_found(self, tmp_path):
        """Test error when directory doesn't exist."""
        test = DirContent(
            name="test_dir_content",
            parameter=DirContentParameter(
                dst=str(tmp_path / "nonexistent"),
                files=["file1.txt"]
            )
        )
        result = test.test()

        assert_test_error(result)


# ============================================================================
# FileContentMatchesRegex Tests
# ============================================================================

class TestFileContentMatchesRegex:
    """Tests for FileContentMatchesRegex testfunction."""

    def test_file_content_matches_regex_success(self, tmp_path):
        """Test successful regex match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World 123")

        test = FileContentMatchesRegex(
            name="test_regex",
            parameter=FileContentMatchesRegexParameter(
                dst=str(test_file),
                regex=r"World \d+"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_content_matches_regex_failure_no_match(self, tmp_path):
        """Test failure when regex doesn't match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        test = FileContentMatchesRegex(
            name="test_regex",
            parameter=FileContentMatchesRegexParameter(
                dst=str(test_file),
                regex=r"\d{5}"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not match" in result.details[0]

    def test_file_content_matches_regex_error_invalid_regex(self, tmp_path):
        """Test error with invalid regex pattern."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        test = FileContentMatchesRegex(
            name="test_regex",
            parameter=FileContentMatchesRegexParameter(
                dst=str(test_file),
                regex=r"[invalid("
            )
        )
        result = test.test()

        assert_test_error(result)
        assert "Invalid regex pattern" in result.details[0]

    def test_file_content_matches_regex_failure_file_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = FileContentMatchesRegex(
            name="test_regex",
            parameter=FileContentMatchesRegexParameter(
                dst=str(tmp_path / "nonexistent.txt"),
                regex=r".*"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_file_content_matches_regex_with_encoding(self, tmp_path):
        """Test regex match with specific encoding."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Héllo Wörld", encoding="utf-8")

        test = FileContentMatchesRegex(
            name="test_regex",
            parameter=FileContentMatchesRegexParameter(
                dst=str(test_file),
                regex=r"Héllo",
                encoding="utf-8"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_content_matches_regex_with_bom(self, tmp_path):
        """Test regex match with BOM stripping."""
        test_file = tmp_path / "test.txt"
        # Write UTF-8 BOM + content
        test_file.write_bytes(b'\xef\xbb\xbfHello World')

        test = FileContentMatchesRegex(
            name="test_regex",
            parameter=FileContentMatchesRegexParameter(
                dst=str(test_file),
                regex=r"^Hello",
                encoding="utf-8",
                strip_bom=True
            )
        )
        result = test.test()

        assert_test_success(result)


# ============================================================================
# FileContentEquals Tests
# ============================================================================

class TestFileContentEquals:
    """Tests for FileContentEquals testfunction."""

    def test_file_content_equals_success(self, tmp_path):
        """Test successful content equality check."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        test = FileContentEquals(
            name="test_equals",
            parameter=FileContentEqualsParameter(
                dst=str(test_file),
                content="Hello World"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_content_equals_failure_not_equal(self, tmp_path):
        """Test failure when content doesn't match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        test = FileContentEquals(
            name="test_equals",
            parameter=FileContentEqualsParameter(
                dst=str(test_file),
                content="Different Content"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Diff:" in result.details[1]

    def test_file_content_equals_failure_file_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = FileContentEquals(
            name="test_equals",
            parameter=FileContentEqualsParameter(
                dst=str(tmp_path / "nonexistent.txt"),
                content="content"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_file_content_equals_with_encoding(self, tmp_path):
        """Test content equality with specific encoding."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Héllo Wörld", encoding="utf-8")

        test = FileContentEquals(
            name="test_equals",
            parameter=FileContentEqualsParameter(
                dst=str(test_file),
                content="Héllo Wörld",
                encoding="utf-8"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_content_equals_with_bom_stripping(self, tmp_path):
        """Test content equality with BOM stripping."""
        test_file = tmp_path / "test.txt"
        # Write UTF-8 BOM + content
        test_file.write_bytes(b'\xef\xbb\xbfHello World')

        test = FileContentEquals(
            name="test_equals",
            parameter=FileContentEqualsParameter(
                dst=str(test_file),
                content="Hello World",
                encoding="utf-8",
                strip_bom=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_content_equals_empty_file(self, tmp_path):
        """Test content equality with empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        test = FileContentEquals(
            name="test_equals",
            parameter=FileContentEqualsParameter(
                dst=str(test_file),
                content=""
            )
        )
        result = test.test()

        assert_test_success(result)


# ============================================================================
# FileHashMatches Tests
# ============================================================================

class TestFileHashMatches:
    """Tests for FileHashMatches testfunction."""

    @pytest.mark.parametrize("hash_type,expected_hash", [
        ("md5", "b10a8db164e0754105b7a99be72e3fe5"),
        ("sha1", "0a4d55a8d778e5022fab701977c5d840bbc486d0"),
        ("sha256", "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"),
        ("sha512", "2c74fd17edafd80e8447b0d46741ee243b7eb74dd2149a0ab1b9246fb30382f27e853d8585719e0e67cbda0daa8f51671064615d645ae27acb15bfb1447f459b"),
    ])
    def test_file_hash_matches_success(self, tmp_path, hash_type, expected_hash):
        """Test successful hash match for different algorithms."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        test = FileHashMatches(
            name="test_hash",
            parameter=FileHashMatchesParameter(
                dst=str(test_file),
                expected_hash=expected_hash,
                hash_type=hash_type
            )
        )
        result = test.test()

        assert_test_success(result)
        assert hash_type.upper() in result.details[0]

    def test_file_hash_matches_failure_wrong_hash(self, tmp_path):
        """Test failure when hash doesn't match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        test = FileHashMatches(
            name="test_hash",
            parameter=FileHashMatchesParameter(
                dst=str(test_file),
                expected_hash="0000000000000000000000000000000000000000000000000000000000000000",
                hash_type="sha256"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "hash mismatch" in result.details[0]

    def test_file_hash_matches_failure_file_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = FileHashMatches(
            name="test_hash",
            parameter=FileHashMatchesParameter(
                dst=str(tmp_path / "nonexistent.txt"),
                expected_hash="0000000000000000000000000000000000000000000000000000000000000000",
                hash_type="sha256"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_file_hash_matches_error_invalid_hash_type(self, tmp_path):
        """Test error with invalid hash type."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        test = FileHashMatches(
            name="test_hash",
            parameter=FileHashMatchesParameter(
                dst=str(test_file),
                expected_hash="abc123",
                hash_type="invalid_hash"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert "Unsupported hash type" in result.details[0]

    def test_file_hash_matches_case_insensitive(self, tmp_path):
        """Test that hash comparison is case insensitive."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        test = FileHashMatches(
            name="test_hash",
            parameter=FileHashMatchesParameter(
                dst=str(test_file),
                expected_hash="B10A8DB164E0754105B7A99BE72E3FE5",  # uppercase
                hash_type="md5"
            )
        )
        result = test.test()

        assert_test_success(result)


# ============================================================================
# FileTimestamps Tests
# ============================================================================

class TestFileTimestamps:
    """Tests for FileTimestamps testfunction."""

    def test_file_timestamps_equals_success(self, tmp_path):
        """Test successful timestamp equals comparison."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Get actual modification time
        actual_mtime = test_file.stat().st_mtime

        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(test_file),
                timestamp_type="modified",
                comparison_type="equals",
                expected_time=actual_mtime,
                tolerance_seconds=2
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_timestamps_equals_failure(self, tmp_path):
        """Test failure when timestamp doesn't match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Use a time far in the past
        past_time = datetime(2020, 1, 1).timestamp()

        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(test_file),
                timestamp_type="modified",
                comparison_type="equals",
                expected_time=past_time,
                tolerance_seconds=1
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "timestamp mismatch" in result.details[0]

    def test_file_timestamps_before_success(self, tmp_path):
        """Test successful 'before' timestamp comparison."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Use a time in the future
        future_time = datetime.now().timestamp() + 3600

        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(test_file),
                timestamp_type="modified",
                comparison_type="before",
                expected_time=future_time
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_timestamps_after_success(self, tmp_path):
        """Test successful 'after' timestamp comparison."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Use a time in the past
        past_time = datetime.now().timestamp() - 3600

        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(test_file),
                timestamp_type="modified",
                comparison_type="after",
                expected_time=past_time
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_timestamps_between_success(self, tmp_path):
        """Test successful 'between' timestamp comparison."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Create a time range around current time
        now = datetime.now().timestamp()
        start_time = now - 3600
        end_time = now + 3600

        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(test_file),
                timestamp_type="modified",
                comparison_type="between",
                start_time=start_time,
                end_time=end_time
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_timestamps_within_last_success(self, tmp_path):
        """Test successful 'within_last' timestamp comparison."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # File was just created, so it should be within last hour
        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(test_file),
                timestamp_type="modified",
                comparison_type="within_last",
                within_duration="1h"
            )
        )
        result = test.test()

        assert_test_success(result)

    @pytest.mark.parametrize("duration,unit", [
        ("60s", "s"),
        ("5m", "m"),
        ("1h", "h"),
        ("1d", "d"),
    ])
    def test_file_timestamps_within_last_various_durations(self, tmp_path, duration, unit):
        """Test 'within_last' with various duration formats."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(test_file),
                timestamp_type="modified",
                comparison_type="within_last",
                within_duration=duration
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_timestamps_string_format_parsing(self, tmp_path):
        """Test timestamp parsing with string format."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Get current time and format it
        current_time = datetime.now()
        time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")

        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(test_file),
                timestamp_type="modified",
                comparison_type="equals",
                expected_time=time_str,
                time_format="%Y-%m-%d %H:%M:%S",
                tolerance_seconds=10
            )
        )
        result = test.test()

        # Should succeed or fail based on timing, but not error
        assert result.status in [StatusEnum.SUCCESS, StatusEnum.FAILED]

    def test_file_timestamps_failure_file_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(tmp_path / "nonexistent.txt"),
                timestamp_type="modified",
                comparison_type="equals",
                expected_time=datetime.now().timestamp()
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    @pytest.mark.parametrize("timestamp_type", ["modified", "accessed"])
    def test_file_timestamps_various_types(self, tmp_path, timestamp_type):
        """Test different timestamp types."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # For accessed, actually access the file
        if timestamp_type == "accessed":
            test_file.read_text()

        test = FileTimestamps(
            name="test_timestamps",
            parameter=FileTimestampsParameter(
                dst=str(test_file),
                timestamp_type=timestamp_type,
                comparison_type="within_last",
                within_duration="1h"
            )
        )
        result = test.test()

        assert_test_success(result)


# ============================================================================
# FilePermissions Tests
# ============================================================================

class TestFilePermissions:
    """Tests for FilePermissions testfunction."""

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix permissions not applicable on Windows")
    def test_file_permissions_octal_success(self, tmp_path):
        """Test successful permission check with octal notation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Set permissions to 644
        test_file.chmod(0o644)

        test = FilePermissions(
            name="test_permissions",
            parameter=FilePermissionsParameter(
                dst=str(test_file),
                expected_permissions="644"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "644" in result.details[0]

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix permissions not applicable on Windows")
    def test_file_permissions_symbolic_success(self, tmp_path):
        """Test successful permission check with symbolic notation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Set permissions to 755
        test_file.chmod(0o755)

        test = FilePermissions(
            name="test_permissions",
            parameter=FilePermissionsParameter(
                dst=str(test_file),
                expected_permissions="rwxr-xr-x"
            )
        )
        result = test.test()

        assert_test_success(result)

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix permissions not applicable on Windows")
    def test_file_permissions_failure_wrong_permissions(self, tmp_path):
        """Test failure when permissions don't match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Set permissions to 644
        test_file.chmod(0o644)

        test = FilePermissions(
            name="test_permissions",
            parameter=FilePermissionsParameter(
                dst=str(test_file),
                expected_permissions="755"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "permission mismatch" in result.details[0]

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix permissions not applicable on Windows")
    def test_file_permissions_with_owner_check(self, tmp_path):
        """Test permission check with owner verification."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        test_file.chmod(0o644)

        # Get current user
        import pwd
        current_user = pwd.getpwuid(os.getuid()).pw_name

        test = FilePermissions(
            name="test_permissions",
            parameter=FilePermissionsParameter(
                dst=str(test_file),
                expected_permissions="644",
                check_owner=current_user
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "owner matches" in result.details[1]

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix permissions not applicable on Windows")
    def test_file_permissions_with_group_check(self, tmp_path):
        """Test permission check with group verification."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        test_file.chmod(0o644)

        # Get current group
        import grp
        current_group = grp.getgrgid(os.getgid()).gr_name

        test = FilePermissions(
            name="test_permissions",
            parameter=FilePermissionsParameter(
                dst=str(test_file),
                expected_permissions="644",
                check_group=current_group
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "group matches" in result.details[1]

    def test_file_permissions_failure_file_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = FilePermissions(
            name="test_permissions",
            parameter=FilePermissionsParameter(
                dst=str(tmp_path / "nonexistent.txt"),
                expected_permissions="644"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]


# ============================================================================
# FileContentContains Tests
# ============================================================================

class TestFileContentContains:
    """Tests for FileContentContains testfunction."""

    def test_file_content_contains_string_success(self, tmp_path):
        """Test successful string content search."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World, this is a test.")

        test = FileContentContains(
            name="test_contains",
            parameter=FileContentContainsParameter(
                dst=str(test_file),
                content="World",
                content_type="string"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "string content found" in result.details[0]

    def test_file_content_contains_string_failure(self, tmp_path):
        """Test failure when string not found."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        test = FileContentContains(
            name="test_contains",
            parameter=FileContentContainsParameter(
                dst=str(test_file),
                content="NotFound",
                content_type="string"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "string content not found" in result.details[0]

    def test_file_content_contains_bytes_success(self, tmp_path):
        """Test successful byte pattern search."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"Hello\x00World\xFF")

        test = FileContentContains(
            name="test_contains",
            parameter=FileContentContainsParameter(
                dst=str(test_file),
                content=r"\x00World",
                content_type="bytes"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "byte pattern found" in result.details[0]

    def test_file_content_contains_bytes_failure(self, tmp_path):
        """Test failure when byte pattern not found."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"Hello World")

        test = FileContentContains(
            name="test_contains",
            parameter=FileContentContainsParameter(
                dst=str(test_file),
                content=r"\xFF\xFF",
                content_type="bytes"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "byte pattern not found" in result.details[0]

    def test_file_content_contains_with_encoding(self, tmp_path):
        """Test string search with specific encoding."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Héllo Wörld", encoding="utf-8")

        test = FileContentContains(
            name="test_contains",
            parameter=FileContentContainsParameter(
                dst=str(test_file),
                content="Wörld",
                content_type="string",
                encoding="utf-8"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_content_contains_with_bom_stripping(self, tmp_path):
        """Test string search with BOM stripping."""
        test_file = tmp_path / "test.txt"
        # Write UTF-8 BOM + content
        test_file.write_bytes(b'\xef\xbb\xbfHello World')

        test = FileContentContains(
            name="test_contains",
            parameter=FileContentContainsParameter(
                dst=str(test_file),
                content="Hello",
                content_type="string",
                encoding="utf-8",
                strip_bom=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_file_content_contains_failure_file_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = FileContentContains(
            name="test_contains",
            parameter=FileContentContainsParameter(
                dst=str(tmp_path / "nonexistent.txt"),
                content="test"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_file_content_contains_empty_file(self, tmp_path):
        """Test behavior with empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        test = FileContentContains(
            name="test_contains",
            parameter=FileContentContainsParameter(
                dst=str(test_file),
                content="anything"
            )
        )
        result = test.test()

        assert_test_failed(result)

    def test_file_content_contains_special_characters(self, tmp_path):
        """Test string search with special characters."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line1\nLine2\tTabbed\r\nWindows")

        test = FileContentContains(
            name="test_contains",
            parameter=FileContentContainsParameter(
                dst=str(test_file),
                content="\n"
            )
        )
        result = test.test()

        assert_test_success(result)
