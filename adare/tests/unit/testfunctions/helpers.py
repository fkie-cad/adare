"""Shared utilities for testfunction unit tests."""

from pathlib import Path


def assert_test_success(result):
    """Assert that a test result is successful."""
    from adarelib.constants import StatusEnum
    assert result.status == StatusEnum.SUCCESS, f"Test failed: {result.details}"


def assert_test_failed(result):
    """Assert that a test result is failed (not error)."""
    from adarelib.constants import StatusEnum
    assert result.status == StatusEnum.FAILED, f"Expected FAILED, got {result.status}: {result.details}"


def assert_test_error(result):
    """Assert that a test result is error."""
    from adarelib.constants import StatusEnum
    assert result.status == StatusEnum.ERROR, f"Expected ERROR, got {result.status}: {result.details}"


def assert_test_execution_error(result):
    """Assert that a test result is execution error (alias for ERROR)."""
    from adarelib.constants import StatusEnum
    assert result.status == StatusEnum.ERROR, f"Expected ERROR, got {result.status}: {result.details}"


def create_file_with_content(path: Path, content: str):
    """Create a file with the given content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def create_binary_file(path: Path, data: bytes):
    """Create a binary file with the given data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
