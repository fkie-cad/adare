from unittest.mock import patch

import pytest


@pytest.fixture
def global_db(tmp_path):
    """A fresh global database for the test."""
    with patch('adare.config.database.get_global_database_location', return_value=tmp_path / 'global.db'):
        yield tmp_path / 'global.db'
