import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.unit

from adare.core.result import ErrorInfo, Result


class TestErrorInfo:
    def test_basic_construction(self):
        err = ErrorInfo(code="NOT_FOUND", message="Item not found")
        assert err.code == "NOT_FOUND"
        assert err.message == "Item not found"
        assert err.solutions is None
        assert err.context is None

    def test_full_construction(self):
        err = ErrorInfo(
            code="DUPLICATE",
            message="Already exists",
            solutions=["Use a different name"],
            context={"name": "test"},
        )
        assert err.solutions == ["Use a different name"]
        assert err.context == {"name": "test"}

    def test_to_dict_minimal(self):
        err = ErrorInfo(code="ERR", message="msg")
        d = err.to_dict()
        assert d == {"code": "ERR", "message": "msg"}
        assert "solutions" not in d
        assert "context" not in d

    def test_to_dict_full(self):
        err = ErrorInfo(
            code="ERR", message="msg",
            solutions=["fix it"], context={"k": "v"},
        )
        d = err.to_dict()
        assert d["solutions"] == ["fix it"]
        assert d["context"] == {"k": "v"}


class TestResultOk:
    def test_ok_with_string(self):
        r = Result.ok("hello")
        assert r.success is True
        assert r.data == "hello"
        assert r.error is None
        assert r.warnings == []

    def test_ok_with_dict(self):
        r = Result.ok({"key": "value"})
        assert r.data == {"key": "value"}

    def test_ok_with_none(self):
        r = Result.ok(None)
        assert r.success is True
        assert r.data is None

    def test_ok_with_warnings(self):
        r = Result.ok("data", warnings=["warn1", "warn2"])
        assert r.warnings == ["warn1", "warn2"]

    def test_ok_warnings_default_empty(self):
        r = Result.ok("data", warnings=None)
        assert r.warnings == []


class TestResultFail:
    def test_basic_fail(self):
        r = Result.fail("NOT_FOUND", "Not found")
        assert r.success is False
        assert r.data is None
        assert r.error is not None
        assert r.error.code == "NOT_FOUND"
        assert r.error.message == "Not found"

    def test_fail_with_solutions_and_context(self):
        r = Result.fail(
            "DUPLICATE", "Exists",
            solutions=["Rename it"],
            context={"name": "x"},
        )
        assert r.error.solutions == ["Rename it"]
        assert r.error.context == {"name": "x"}


class TestResultFromException:
    def test_from_exception(self):
        exc = MagicMock()
        exc.error_name = "TestError"
        exc.message = "Something failed"
        exc.possible_solutions = ["Try again"]
        r = Result.from_exception(exc)
        assert r.success is False
        assert r.error.code == "TestError"
        assert r.error.message == "Something failed"
        assert r.error.solutions == ["Try again"]

    def test_from_exception_no_solutions(self):
        exc = MagicMock(spec=[])  # no attributes by default
        exc.error_name = "Err"
        exc.message = "msg"
        r = Result.from_exception(exc)
        assert r.error.solutions is None


class TestResultToDict:
    def test_success_to_dict_with_str(self):
        r = Result.ok("hello")
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"] == "hello"
        assert "error" not in d

    def test_success_to_dict_with_to_dict_obj(self):
        obj = MagicMock()
        obj.to_dict.return_value = {"id": "1"}
        r = Result.ok(obj)
        d = r.to_dict()
        assert d["data"] == {"id": "1"}

    def test_success_to_dict_with_dataclass_like(self):
        class Foo:
            def __init__(self):
                self.x = 1
        r = Result.ok(Foo())
        d = r.to_dict()
        assert d["data"] == {"x": 1}

    def test_success_to_dict_none_data(self):
        r = Result.ok(None)
        d = r.to_dict()
        assert "data" not in d

    def test_fail_to_dict(self):
        r = Result.fail("ERR", "msg")
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"]["code"] == "ERR"
        assert "data" not in d

    def test_warnings_in_dict(self):
        r = Result.ok("x", warnings=["w1"])
        d = r.to_dict()
        assert d["warnings"] == ["w1"]

    def test_no_warnings_key_when_empty(self):
        r = Result.ok("x")
        d = r.to_dict()
        assert "warnings" not in d
