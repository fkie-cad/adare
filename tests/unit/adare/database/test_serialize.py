"""
Unit tests for SerializeApi class.

Tests the serialization logic for converting database model objects
to dictionaries suitable for API responses.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import sys

from adare.config import TIMESTAMP_FORMAT
from adarelib.constants import StatusEnum


# Module-level fixture setup to mock the database dependencies before import
@pytest.fixture(scope="module")
def mock_db_setup():
    """Set up mocks before importing SerializeApi."""
    with patch.dict(sys.modules, {'adare.config.database': MagicMock()}):
        yield


def create_serialize_api():
    """Factory function to create SerializeApi with mocked dependencies."""
    # Import here to ensure patches are in place
    with patch('adare.config.database.get_database_location', return_value=MagicMock()):
        with patch('adare.database.api.database.DatabaseApi.__init__', return_value=None):
            from adare.database.api.serialize import SerializeApi
            api = SerializeApi.__new__(SerializeApi)
            api._session = MagicMock()
            return api


class TestSerializeResult:
    """Tests for serialize_result method."""

    @pytest.fixture
    def serialize_api(self):
        """Create a SerializeApi instance with mocked database connection."""
        return create_serialize_api()

    def test_serialize_result_with_valid_result(self, serialize_api):
        """Test serializing a valid Result object."""
        mock_result = MagicMock()
        mock_result.status = StatusEnum.SUCCESS
        mock_result.details = "Test passed successfully"

        result_dict = serialize_api.serialize_result(mock_result)

        assert result_dict == {
            'status': StatusEnum.SUCCESS,
            'details': "Test passed successfully"
        }

    def test_serialize_result_with_none_returns_empty_dict(self, serialize_api):
        """Test serializing None returns empty dictionary."""
        result_dict = serialize_api.serialize_result(None)

        assert result_dict == {}

    def test_serialize_result_with_none_details(self, serialize_api):
        """Test serializing result with None details."""
        mock_result = MagicMock()
        mock_result.status = StatusEnum.FAILED
        mock_result.details = None

        result_dict = serialize_api.serialize_result(mock_result)

        assert result_dict['status'] == StatusEnum.FAILED
        assert result_dict['details'] is None


class TestSerializeEvent:
    """Tests for serialize_event method."""

    @pytest.fixture
    def serialize_api(self):
        """Create a SerializeApi instance with mocked database connection."""
        return create_serialize_api()

    @pytest.fixture
    def base_event(self):
        """Create a base mock event with common attributes."""
        event = MagicMock()
        event.ulid = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        event.timestamp = datetime(2024, 1, 15, 10, 30, 0, 123456)
        event.category = "test_category"
        event.error = None
        return event

    def test_serialize_command_event(self, serialize_api, base_event):
        """Test serializing a command event."""
        base_event.event_type = 'command_event'
        base_event.name = "run_test"
        base_event.command = "python test.py"
        base_event.returncode = 0
        base_event.stdout = "Test output"

        result = serialize_api.serialize_event(base_event)

        assert result['ulid'] == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        assert result['event_type'] == 'command_event'
        assert result['category'] == 'test_category'
        assert result['name'] == "run_test"
        assert result['command'] == "python test.py"
        assert result['returncode'] == 0
        assert result['stdout'] == "Test output"
        assert result['error'] is None

    def test_serialize_test_event_with_remote_ulid(self, serialize_api, base_event):
        """Test serializing a test event that has remote_ulid."""
        base_event.event_type = 'test_event'

        mock_abstract_test = MagicMock()
        mock_abstract_test.remote_ulid = "remote_ulid_123"
        mock_abstract_test.id = "local_id_456"
        base_event.abstract_test = mock_abstract_test

        mock_result = MagicMock()
        mock_result.status = StatusEnum.SUCCESS
        mock_result.details = "Test passed"
        base_event.result = mock_result

        result = serialize_api.serialize_event(base_event)

        assert result['event_type'] == 'test_event'
        assert result['abstract_test_ulid'] == "remote_ulid_123"
        assert result['result']['status'] == StatusEnum.SUCCESS

    def test_serialize_test_event_fallback_to_id(self, serialize_api, base_event):
        """Test serializing a test event that falls back to id when no remote_ulid."""
        base_event.event_type = 'test_event'

        mock_abstract_test = MagicMock()
        mock_abstract_test.remote_ulid = None
        mock_abstract_test.id = "local_id_456"
        base_event.abstract_test = mock_abstract_test

        mock_result = MagicMock()
        mock_result.status = StatusEnum.FAILED
        mock_result.details = None
        base_event.result = mock_result

        result = serialize_api.serialize_event(base_event)

        assert result['abstract_test_ulid'] == "local_id_456"

    def test_serialize_error_event(self, serialize_api, base_event):
        """Test serializing an error event."""
        base_event.event_type = 'error_event'
        base_event.error_name = "TestError"
        base_event.error_msg = "Something went wrong"

        result = serialize_api.serialize_event(base_event)

        assert result['event_type'] == 'error_event'
        assert result['error_name'] == "TestError"
        assert result['error_msg'] == "Something went wrong"

    def test_serialize_gui_find_event(self, serialize_api, base_event):
        """Test serializing a GUI find event."""
        base_event.event_type = 'gui_find_event'
        base_event.text = "Button"
        base_event.objective = "Find submit button"
        base_event.success = True
        base_event.positions = [(100, 200), (150, 250)]

        result = serialize_api.serialize_event(base_event)

        assert result['event_type'] == 'gui_find_event'
        assert result['text'] == "Button"
        assert result['objective'] == "Find submit button"
        assert result['success'] is True
        assert result['positions'] == [(100, 200), (150, 250)]

    def test_serialize_gui_click_event(self, serialize_api, base_event):
        """Test serializing a GUI click event."""
        base_event.event_type = 'gui_click_event'
        base_event.clicktype = "left"
        base_event.modifiers = ["ctrl"]
        base_event.target = "submit_button"

        result = serialize_api.serialize_event(base_event)

        assert result['event_type'] == 'gui_click_event'
        assert result['clicktype'] == "left"
        assert result['modifiers'] == ["ctrl"]
        assert result['target'] == "submit_button"

    def test_serialize_gui_keypress_event(self, serialize_api, base_event):
        """Test serializing a GUI keypress event."""
        base_event.event_type = 'gui_keypress_event'
        base_event.keys = ["enter", "tab"]

        result = serialize_api.serialize_event(base_event)

        assert result['event_type'] == 'gui_keypress_event'
        assert result['keys'] == ["enter", "tab"]

    def test_serialize_gui_idle_event(self, serialize_api, base_event):
        """Test serializing a GUI idle event."""
        base_event.event_type = 'gui_idle_event'
        base_event.seconds = 5.5

        result = serialize_api.serialize_event(base_event)

        assert result['event_type'] == 'gui_idle_event'
        assert result['seconds'] == 5.5

    def test_serialize_unknown_event_type_logs_warning(self, serialize_api, base_event):
        """Test that unknown event type logs a warning."""
        base_event.event_type = 'unknown_event_type'

        with patch('adare.database.api.serialize.log') as mock_log:
            serialize_api.serialize_event(base_event)

            mock_log.warning.assert_called_once()
            assert 'Unknown event type' in str(mock_log.warning.call_args)

    def test_serialize_event_timestamp_format(self, serialize_api, base_event):
        """Test that timestamp is formatted correctly."""
        base_event.event_type = 'gui_idle_event'
        base_event.seconds = 1
        base_event.timestamp = datetime(2024, 6, 15, 14, 30, 45, 123456)

        result = serialize_api.serialize_event(base_event)

        expected_timestamp = "2024-06-15T14:30:45.123456"
        assert result['timestamp'] == expected_timestamp


class TestSerializeRun:
    """Tests for serialize_run method."""

    @pytest.fixture
    def serialize_api(self):
        """Create a SerializeApi instance with mocked database connection."""
        return create_serialize_api()

    @pytest.fixture
    def mock_run(self):
        """Create a mock ExperimentRun object."""
        run = MagicMock()
        run.id = "run_ulid_123"
        run.status = StatusEnum.SUCCESS
        run.result_status = StatusEnum.SUCCESS
        run.start_time = datetime(2024, 1, 15, 10, 0, 0, 0)
        run.end_time = datetime(2024, 1, 15, 10, 30, 0, 0)

        # Mock experiment
        run.experiment = MagicMock()
        run.experiment.remote_ulid = "exp_remote_ulid"
        run.experiment.id = "exp_local_id"

        # Mock environment
        run.environment = MagicMock()
        run.environment.remote_ulid = "env_remote_ulid"
        run.environment_id = "env_local_id"

        # Mock events (empty list for simplicity)
        run.events = []

        # Mock files
        run.files = MagicMock()
        run.files.log_adarevm = MagicMock()
        run.files.log_adarevm.path = "/path/to/adarevm.log"
        run.files.log_installations = MagicMock()
        run.files.log_installations.path = "/path/to/installations.log"
        run.files.package_dump = MagicMock()
        run.files.package_dump.path = "/path/to/packagedump.log"

        return run

    def test_serialize_run_returns_tuple(self, serialize_api, mock_run):
        """Test that serialize_run returns a tuple of (run_dict, files_dict)."""
        result = serialize_api.serialize_run(mock_run)

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_serialize_run_data_structure(self, serialize_api, mock_run):
        """Test the structure of serialized run data."""
        run_dict, files_dict = serialize_api.serialize_run(mock_run)

        assert run_dict['ulid'] == "run_ulid_123"
        assert run_dict['status'] == StatusEnum.SUCCESS
        assert run_dict['result_status'] == StatusEnum.SUCCESS
        assert run_dict['experiment_ulid'] == "exp_remote_ulid"
        assert run_dict['environment_ulid'] == "env_remote_ulid"
        assert 'timestamp_start' in run_dict
        assert 'timestamp_end' in run_dict
        assert 'events' in run_dict

    def test_serialize_run_files_structure(self, serialize_api, mock_run):
        """Test the structure of serialized files data."""
        run_dict, files_dict = serialize_api.serialize_run(mock_run)

        assert files_dict['adarevm_log'] == "/path/to/adarevm.log"
        assert files_dict['installations_log'] == "/path/to/installations.log"
        assert files_dict['packagedump_log'] == "/path/to/packagedump.log"

    def test_serialize_run_fallback_to_local_ids(self, serialize_api, mock_run):
        """Test that serialize_run falls back to local IDs when remote_ulid is None."""
        mock_run.experiment.remote_ulid = None
        mock_run.environment.remote_ulid = None

        run_dict, _ = serialize_api.serialize_run(mock_run)

        assert run_dict['experiment_ulid'] == "exp_local_id"
        assert run_dict['environment_ulid'] == "env_local_id"

    def test_serialize_run_with_events(self, serialize_api, mock_run):
        """Test serializing run with events."""
        # Create mock events
        mock_event = MagicMock()
        mock_event.ulid = "event_ulid_1"
        mock_event.timestamp = datetime(2024, 1, 15, 10, 15, 0, 0)
        mock_event.event_type = 'gui_idle_event'
        mock_event.category = 'action'
        mock_event.error = None
        mock_event.seconds = 2

        mock_run.events = [mock_event]

        run_dict, _ = serialize_api.serialize_run(mock_run)

        assert len(run_dict['events']) == 1
        assert run_dict['events'][0]['ulid'] == "event_ulid_1"

    def test_serialize_run_timestamp_format(self, serialize_api, mock_run):
        """Test that timestamps are formatted correctly."""
        run_dict, _ = serialize_api.serialize_run(mock_run)

        assert run_dict['timestamp_start'] == "2024-01-15T10:00:00.000000"
        assert run_dict['timestamp_end'] == "2024-01-15T10:30:00.000000"


class TestSerializeRunByUlid:
    """Tests for serialize_run_by_ulid method."""

    @pytest.fixture
    def serialize_api(self):
        """Create a SerializeApi instance with mocked database connection."""
        return create_serialize_api()

    def test_serialize_run_by_ulid_queries_database(self, serialize_api):
        """Test that serialize_run_by_ulid queries the database correctly."""
        mock_run = MagicMock()
        mock_run.id = "run_ulid_123"
        mock_run.status = StatusEnum.SUCCESS
        mock_run.result_status = StatusEnum.SUCCESS
        mock_run.start_time = datetime(2024, 1, 15, 10, 0, 0, 0)
        mock_run.end_time = datetime(2024, 1, 15, 10, 30, 0, 0)
        mock_run.experiment = MagicMock(remote_ulid="exp_ulid", id="exp_id")
        mock_run.environment = MagicMock(remote_ulid="env_ulid")
        mock_run.environment_id = "env_id"
        mock_run.events = []
        mock_run.files = MagicMock()
        mock_run.files.log_adarevm = MagicMock(path="/log1")
        mock_run.files.log_installations = MagicMock(path="/log2")
        mock_run.files.package_dump = MagicMock(path="/log3")

        # Set up mock query chain
        serialize_api._session.query.return_value.filter.return_value.first.return_value = mock_run

        serialize_api.serialize_run_by_ulid("run_ulid_123")

        # Verify query was called
        serialize_api._session.query.assert_called_once()


class TestSerializationRoundTrip:
    """Tests to verify serialization produces consistent output."""

    @pytest.fixture
    def serialize_api(self):
        """Create a SerializeApi instance with mocked database connection."""
        return create_serialize_api()

    def test_serialize_result_idempotent(self, serialize_api):
        """Test that serializing the same result produces identical output."""
        mock_result = MagicMock()
        mock_result.status = StatusEnum.SUCCESS
        mock_result.details = "Test details"

        result1 = serialize_api.serialize_result(mock_result)
        result2 = serialize_api.serialize_result(mock_result)

        assert result1 == result2

    def test_serialize_event_all_fields_present(self, serialize_api):
        """Test that all required fields are present in serialized event."""
        event = MagicMock()
        event.ulid = "test_ulid"
        event.timestamp = datetime(2024, 1, 1, 0, 0, 0, 0)
        event.event_type = 'gui_idle_event'
        event.category = 'action'
        event.error = None
        event.seconds = 1

        result = serialize_api.serialize_event(event)

        required_fields = ['ulid', 'timestamp', 'event_type', 'category', 'error']
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"
