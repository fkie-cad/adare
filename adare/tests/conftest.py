"""Root-level pytest fixtures for ADARE tests."""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sqlalchemy
from sqlalchemy.orm import sessionmaker

# Point the appdata directory at a throwaway tree before any adare module is
# imported: config paths are resolved at import time, and tests must never read
# or write the developer's real ~/.adare.
_TEST_HOME = tempfile.mkdtemp(prefix="adare-test-")
os.environ["ADARE_HOME"] = _TEST_HOME


def pytest_unconfigure(config):
    shutil.rmtree(_TEST_HOME, ignore_errors=True)


@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_db_session():
    """In-memory SQLite session for database tests."""
    engine = sqlalchemy.create_engine("sqlite:///:memory:", echo=False)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = Session()
    yield engine, session
    session.close()
    engine.dispose()


@pytest.fixture
def mock_result_ok():
    """Factory for creating successful Result objects."""
    from adare.core.result import Result

    def _make(data=None, warnings=None):
        return Result.ok(data, warnings=warnings)

    return _make


@pytest.fixture
def mock_result_fail():
    """Factory for creating failed Result objects."""
    from adare.core.result import Result

    def _make(code="TEST_ERROR", message="Test error", solutions=None, context=None):
        return Result.fail(code, message, solutions=solutions, context=context)

    return _make


@pytest.fixture
def mock_api():
    """Mock AdareAPI instance with all sub-APIs mocked."""
    api = MagicMock()
    api.project = MagicMock()
    api.environment = MagicMock()
    api.experiment = MagicMock()
    api.vm = MagicMock()
    api.testfunction = MagicMock()
    api.manage = MagicMock()
    api.show = MagicMock()
    api.web = MagicMock()
    api.devmode = MagicMock()
    return api
