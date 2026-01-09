"""
Unit tests for adarevm.exception module.

Tests LoggedException and LoggedErrorException classes.
"""
import pytest
import logging
from unittest.mock import MagicMock, call

from adarevm.exception import LoggedException, LoggedErrorException


class TestLoggedException:
    """Tests for LoggedException class."""

    def test_logged_exception_with_info_level(self):
        """Test LoggedException logs at info level by default."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Test info message"

        with pytest.raises(LoggedException) as exc_info:
            raise LoggedException(mock_logger, message)

        assert str(exc_info.value) == message
        mock_logger.info.assert_called_once_with(message)

    def test_logged_exception_with_debug_level(self):
        """Test LoggedException logs at debug level when specified."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Test debug message"

        with pytest.raises(LoggedException) as exc_info:
            raise LoggedException(mock_logger, message, level='debug')

        assert str(exc_info.value) == message
        mock_logger.debug.assert_called_once_with(message)

    def test_logged_exception_with_warning_level(self):
        """Test LoggedException logs at warning level when specified."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Test warning message"

        with pytest.raises(LoggedException) as exc_info:
            raise LoggedException(mock_logger, message, level='warning')

        assert str(exc_info.value) == message
        mock_logger.warning.assert_called_once_with(message)

    def test_logged_exception_with_error_level(self):
        """Test LoggedException logs at error level when specified."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Test error message"

        with pytest.raises(LoggedException) as exc_info:
            raise LoggedException(mock_logger, message, level='error')

        assert str(exc_info.value) == message
        mock_logger.error.assert_called_once_with(message)

    def test_logged_exception_with_critical_level(self):
        """Test LoggedException logs at critical level when specified."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Test critical message"

        with pytest.raises(LoggedException) as exc_info:
            raise LoggedException(mock_logger, message, level='critical')

        assert str(exc_info.value) == message
        mock_logger.critical.assert_called_once_with(message)

    def test_logged_exception_stores_logger_reference(self):
        """Test LoggedException stores the logger reference."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Test message"

        exc = LoggedException(mock_logger, message)

        assert exc.log is mock_logger

    def test_logged_exception_inherits_from_exception(self):
        """Test LoggedException inherits from Exception."""
        assert issubclass(LoggedException, Exception)

    def test_logged_exception_message_passed_to_parent(self):
        """Test LoggedException passes message to parent Exception."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Exception message"

        exc = LoggedException(mock_logger, message)

        assert exc.args[0] == message

    def test_logged_exception_with_unknown_level_does_not_log(self):
        """Test LoggedException with unknown level does not log."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Test message"

        exc = LoggedException(mock_logger, message, level='unknown')

        # None of the logging methods should be called for unknown level
        mock_logger.info.assert_not_called()
        mock_logger.debug.assert_not_called()
        mock_logger.warning.assert_not_called()
        mock_logger.error.assert_not_called()
        mock_logger.critical.assert_not_called()


class TestLoggedErrorException:
    """Tests for LoggedErrorException class."""

    def test_logged_error_exception_logs_at_error_level(self):
        """Test LoggedErrorException always logs at error level."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Error occurred"

        with pytest.raises(LoggedErrorException) as exc_info:
            raise LoggedErrorException(mock_logger, message)

        mock_logger.error.assert_called_once_with(message)

    def test_logged_error_exception_str_format(self):
        """Test LoggedErrorException __str__ method returns formatted message."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Error message"

        exc = LoggedErrorException(mock_logger, message)

        assert str(exc) == f"LoggedErrorException: {message}"

    def test_logged_error_exception_stores_message(self):
        """Test LoggedErrorException stores message attribute."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Error message"

        exc = LoggedErrorException(mock_logger, message)

        assert exc.message == message

    def test_logged_error_exception_stores_logger(self):
        """Test LoggedErrorException stores logger reference."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Error message"

        exc = LoggedErrorException(mock_logger, message)

        assert exc.log is mock_logger

    def test_logged_error_exception_inherits_from_logged_exception(self):
        """Test LoggedErrorException inherits from LoggedException."""
        assert issubclass(LoggedErrorException, LoggedException)

    def test_logged_error_exception_inherits_from_exception(self):
        """Test LoggedErrorException inherits from Exception (via LoggedException)."""
        assert issubclass(LoggedErrorException, Exception)

    def test_logged_error_exception_can_be_caught_as_logged_exception(self):
        """Test LoggedErrorException can be caught as LoggedException."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Error message"

        caught = False
        try:
            raise LoggedErrorException(mock_logger, message)
        except LoggedException:
            caught = True

        assert caught is True

    def test_logged_error_exception_can_be_caught_as_exception(self):
        """Test LoggedErrorException can be caught as generic Exception."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Error message"

        caught = False
        try:
            raise LoggedErrorException(mock_logger, message)
        except Exception:
            caught = True

        assert caught is True

    def test_logged_error_exception_with_empty_message(self):
        """Test LoggedErrorException with empty message."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = ""

        exc = LoggedErrorException(mock_logger, message)

        assert exc.message == ""
        assert str(exc) == "LoggedErrorException: "
        mock_logger.error.assert_called_once_with("")

    def test_logged_error_exception_with_multiline_message(self):
        """Test LoggedErrorException with multiline message."""
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Line 1\nLine 2\nLine 3"

        exc = LoggedErrorException(mock_logger, message)

        assert exc.message == message
        assert str(exc) == f"LoggedErrorException: {message}"
        mock_logger.error.assert_called_once_with(message)
