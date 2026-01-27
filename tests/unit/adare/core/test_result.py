
import pytest
from adare.core.result import Result, ErrorInfo
from adare.exceptions import LoggedErrorException
import logging

class TestResult:
    def test_ok_success(self):
        """Test creating a successful result."""
        data = {"key": "value"}
        result = Result.ok(data)
        
        assert result.success is True
        assert result.data == data
        assert result.error is None
        assert result.warnings == []

    def test_ok_with_warnings(self):
        """Test creating a successful result with warnings."""
        data = "test data"
        warnings = ["warning 1", "warning 2"]
        result = Result.ok(data, warnings=warnings)
        
        assert result.success is True
        assert result.data == data
        assert result.warnings == warnings

    def test_fail_creation(self):
        """Test creating a failed result."""
        code = "TEST_ERROR"
        message = "Something went wrong"
        solutions = ["Fix it"]
        context = {"detail": "info"}
        
        result = Result.fail(code, message, solutions, context)
        
        assert result.success is False
        assert result.data is None
        assert result.error is not None
        assert result.error.code == code
        assert result.error.message == message
        assert result.error.solutions == solutions
        assert result.error.context == context

    def test_from_exception(self):
        """Test creating a result from a LoggedErrorException."""
        # Create a mock Logger
        logger = logging.getLogger("test")
        
        # Create a LoggedErrorException
        exc = LoggedErrorException(
            log=logger,
            message="Exception message",
            possible_solutions=["Try this"]
        )
        
        result = Result.from_exception(exc)
        
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "LoggedErrorException"
        assert result.error.message == "Exception message"
        assert result.error.solutions == ["Try this"]

    def test_from_exception_no_solutions(self):
        """Test creating a result from a LoggedErrorException without solutions."""
        logger = logging.getLogger("test")
        exc = LoggedErrorException(
            log=logger,
            message="Exception message"
        )
        # LoggedErrorException might default error_name to something if not provided, 
        # but let's see how it behaves. Assuming default behavior.
        
        result = Result.from_exception(exc)
        
        assert result.success is False
        assert result.error is not None
        assert result.error.message == "Exception message"
        # solutions might be None or empty list depending on LoggedErrorException implementation
        if hasattr(exc, 'possible_solutions'):
            assert result.error.solutions == exc.possible_solutions
        else:
            assert result.error.solutions is None

    def test_to_dict_success(self):
        """Test converting success result to dict."""
        data = "simple string"
        result = Result.ok(data)
        
        result_dict = result.to_dict()
        assert result_dict == {
            "success": True,
            "data": "simple string"
        }

    def test_to_dict_success_object_with_to_dict(self):
        """Test converting success result with object having to_dict."""
        class DataObj:
            def to_dict(self):
                return {"foo": "bar"}
        
        result = Result.ok(DataObj())
        result_dict = result.to_dict()
        
        assert result_dict == {
            "success": True,
            "data": {"foo": "bar"}
        }

    def test_to_dict_failure(self):
        """Test converting failure result to dict."""
        result = Result.fail("ERR", "Msg", solutions=["Sol"])
        result_dict = result.to_dict()
        
        assert result_dict == {
            "success": False,
            "error": {
                "code": "ERR",
                "message": "Msg",
                "solutions": ["Sol"]
            }
        }
