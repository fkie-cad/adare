"""Fixtures for testfunction unit tests."""

import csv
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

# === Path Fixtures ===

@pytest.fixture
def testfunctions_fixtures_dir(fixtures_dir):
    """Path to testfunction-specific fixtures."""
    return fixtures_dir / "testfunctions"


# === File Creation Factory Fixtures ===

@pytest.fixture
def create_csv_file(tmp_path):
    """Factory to create CSV files."""
    def _create(filename, rows):
        filepath = tmp_path / filename
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        return filepath
    return _create


@pytest.fixture
def create_json_file(tmp_path):
    """Factory to create JSON files."""
    def _create(filename, data):
        filepath = tmp_path / filename
        with open(filepath, 'w') as f:
            json.dump(data, f)
        return filepath
    return _create


@pytest.fixture
def create_xml_file(tmp_path):
    """Factory to create XML files."""
    def _create(filename, content):
        filepath = tmp_path / filename
        with open(filepath, 'w') as f:
            f.write(content)
        return filepath
    return _create


@pytest.fixture
def create_sqlite_db(tmp_path):
    """Factory to create SQLite databases."""
    def _create(filename, schema, data=None):
        filepath = tmp_path / filename
        conn = sqlite3.connect(str(filepath))
        cursor = conn.cursor()
        cursor.execute(schema)
        if data:
            for row in data:
                placeholders = ','.join(['?'] * len(row))
                cursor.execute(f"INSERT INTO test_table VALUES ({placeholders})", row)
        conn.commit()
        conn.close()
        return filepath
    return _create


@pytest.fixture
def create_excel_file(tmp_path):
    """Factory to create Excel files with multiple sheets."""
    def _create(filename, sheets_data):
        """
        Create an Excel file with specified sheets and data.

        Args:
            filename: Name of the Excel file to create
            sheets_data: Dict[sheet_name, List[List[str]]] - Sheet names mapped to row data

        Returns:
            Path to created Excel file
        """
        filepath = tmp_path / filename
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            for sheet_name, rows in sheets_data.items():
                df = pd.DataFrame(rows) if rows else pd.DataFrame()
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)
        return filepath
    return _create


# === Metadata Fixtures (for placeholder tests) ===

@pytest.fixture
def variable_metadata_with_tolerance():
    """Metadata with timestamp tolerance."""
    return {
        "TIMESTAMP": {
            "type": "timestamp",
            "resolved_value": "1705314600",  # 2024-01-15 10:30:00 UTC
            "tolerance": [5, -5]  # ±5 seconds
        },
        "REGEX_VAR": {
            "type": "regex",
            "resolved_value": r"\d{3}-\d{4}"
        },
        "STRING_VAR": {
            "type": "string",
            "resolved_value": "expected_value"
        }
    }


@pytest.fixture
def variable_metadata_simple():
    """Simple metadata without tolerance."""
    return {
        "VAR1": {
            "type": "string",
            "resolved_value": "value1"
        },
        "VAR2": {
            "type": "string",
            "resolved_value": "value2"
        },
        "NAME_VAR": {
            "type": "string",
            "resolved_value": "Alice"
        }
    }


# === Mock Factories ===

@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for system tests."""
    with patch('subprocess.run') as mock_run:
        yield mock_run


@pytest.fixture
def mock_visual_context():
    """Mock context for visual tests (host-side execution)."""
    context = MagicMock()
    context.cv = MagicMock()
    context.cv.find_text = AsyncMock(return_value=[])
    context.cv.find_icon = AsyncMock(return_value=[])
    context.screenshot = MagicMock()
    context.screenshot.take = AsyncMock(return_value=b"fake_screenshot")
    context.playbook_dir = Path("/fake/playbook/dir")
    return context
