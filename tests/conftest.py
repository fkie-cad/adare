"""
Shared pytest fixtures and configuration for ADARE test suite.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
import tempfile
import shutil
from contextlib import contextmanager

# === Path Fixtures ===

@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"

@pytest.fixture
def temp_directory():
    """Provide a temporary directory that's cleaned up after test."""
    temp_dir = Path(tempfile.mkdtemp(prefix="adare_test_"))
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

# === Timestamp Fixtures ===

@pytest.fixture
def fixed_datetime():
    """Fixed datetime for deterministic timestamp testing."""
    return datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

# === Database Fixtures (for integration tests) ===

@pytest.fixture
def mock_database_session():
    """Mock SQLAlchemy session for database tests."""
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session

# === WebSocket Fixtures ===

@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection for protocol testing."""
    ws = MagicMock()
    ws.send = AsyncMock(return_value=None)
    ws.recv = AsyncMock(return_value='{"type": "pong"}')
    ws.remote_address = ("127.0.0.1", 12345)
    return ws

# === Mock Factory Class ===

class MockFactory:
    """Factory for creating common test mocks."""

    @staticmethod
    def create_subprocess_result(returncode=0, stdout="", stderr=""):
        """Create a mock subprocess.CompletedProcess."""
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    @staticmethod
    @contextmanager
    def mock_subprocess(returncode=0, stdout="", stderr=""):
        """Context manager to mock subprocess.run."""
        result = MockFactory.create_subprocess_result(returncode, stdout, stderr)
        with patch('subprocess.run', return_value=result) as mock_run:
            yield mock_run

    @staticmethod
    def create_websocket_client():
        """Create mock WebSocket client."""
        ws = MagicMock()
        ws.connected = True
        ws.send = AsyncMock(return_value=None)
        return ws

@pytest.fixture
def mock_factory():
    """Provide MockFactory instance for tests."""
    return MockFactory()
