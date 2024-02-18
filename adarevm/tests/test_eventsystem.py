import pytest
from unittest.mock import Mock
from pathlib import Path
from adarevm.event import EventSystemV1


# Mock the dict_to_yaml function to avoid actual file operations during tests
@pytest.fixture
def mock_dict_to_yaml(mocker):
    return mocker.patch('adarevm.event.dict_to_yaml', return_value=None)


# Happy path tests with various realistic test values
@pytest.mark.parametrize("test_id, message, level, expected_event", [
    ("HP-1", "Event occurred", "info", {"message": "Event occurred", "level": "info"}),
    ("HP-2", "Warning issued", "warning", {"message": "Warning issued", "level": "warning"}),
    ("HP-3", "Error encountered", "error", {"message": "Error encountered", "level": "error"}),
])
def test_log_event_happy_path(mock_dict_to_yaml, test_id, message, level, expected_event):
    # Arrange
    path = Path("/fake/path/events.yaml")
    event_system = EventSystemV1(path)

    # Act
    event_system.log(message, level)

    # Assert
    assert event_system.data['events'][-1]['message'] == expected_event['message']
    assert event_system.data['events'][-1]['level'] == expected_event['level']


# Edge case tests
@pytest.mark.parametrize("test_id, message, level", [
    ("EC-1", "", "info"),  # Empty message
    ("EC-2", "Event with no level", None),  # None level, should default to 'info'
])
def test_log_event_edge_cases(mock_dict_to_yaml, test_id, message, level):
    # Arrange
    path = Path("/fake/path/events.yaml")
    event_system = EventSystemV1(path)

    # Act
    event_system.log(message, level)

    # Assert
    assert event_system.data['events'][-1]['message'] == message
    assert event_system.data['events'][-1]['level'] == (level or 'info')


# Error case tests
@pytest.mark.parametrize("test_id, message, level, expected_exception", [
    ("ER-1", "Event occurred", "invalid_level", ValueError),  # Invalid level
])
def test_log_event_error_cases(mock_dict_to_yaml, test_id, message, level, expected_exception):
    # Arrange
    path = Path("/fake/path/events.yaml")
    event_system = EventSystemV1(path)

    # Act / Assert
    with pytest.raises(expected_exception):
        event_system.log(message, level)


# Test write method
@pytest.mark.parametrize("test_id", [
    ("WR-1"),
])
def test_write_method(mock_dict_to_yaml, test_id):
    # Arrange
    path = Path("/fake/path/events.yaml")
    event_system = EventSystemV1(path)
    event_system.log("Test event", "info")

    # Act
    event_system.write()

    # Assert
    mock_dict_to_yaml.assert_called_once_with(path, event_system.data)
    assert 'end_time' in event_system.data
