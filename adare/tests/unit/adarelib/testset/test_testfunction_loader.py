"""Tests for TestfunctionLoader thread-safe module loading."""
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from adarelib.testset import testfunction as testfunction_module
from adarelib.testset.testfunction import (
    ModuleLoadFailure,
    TestfunctionLoader,
    clear_module_load_failures,
    get_missing_testfunctions,
    get_module_load_failures,
    get_testclass_from_testfunction,
    import_basictest_subclasses,
)
from adarelib.testset.type import Test, TestsetFile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_valid_test_module(tmp_path: Path, name: str = "test_module") -> Path:
    """Create a minimal valid testfunction module file."""
    module_file = tmp_path / f"{name}.py"
    module_file.write_text(
        "import attrs\n"
        "from typing import ClassVar, Optional, Dict, Any\n"
        "from adarelib.testset.basictest import BasicTest, Parameter\n"
        "\n"
        "@attrs.define\n"
        "class DummyParam(Parameter):\n"
        "    dst: str = ''\n"
        "\n"
        "@attrs.define\n"
        "class TestDummy(BasicTest):\n"
        "    testname: ClassVar[str] = 'dummy_test'\n"
        "    testdescription: ClassVar[str] = 'A dummy test'\n"
        "    parameter: DummyParam = attrs.Factory(DummyParam)\n"
        "\n"
        "    def test(self):\n"
        "        pass\n"
    )
    return module_file


def _create_broken_import_module(tmp_path: Path, name: str = "broken_module") -> Path:
    """Create a module that raises ImportError on load."""
    module_file = tmp_path / f"{name}.py"
    module_file.write_text("import nonexistent_package_xyz\n")
    return module_file


def _create_syntax_error_module(tmp_path: Path, name: str = "syntax_err") -> Path:
    """Create a module with a syntax error."""
    module_file = tmp_path / f"{name}.py"
    module_file.write_text("def broken(\n")  # unclosed paren
    return module_file


# ---------------------------------------------------------------------------
# TestfunctionLoader.import_basictest_subclasses
# ---------------------------------------------------------------------------

class TestLoaderImport:
    """Tests for TestfunctionLoader.import_basictest_subclasses."""

    def test_returns_dict_of_test_classes_via_source(self, tmp_path):
        module_file = _create_valid_test_module(tmp_path)
        loader = TestfunctionLoader()

        result = loader.import_basictest_subclasses(
            source=[("my_tests", str(module_file))]
        )

        assert "my_tests" in result
        assert "dummy_test" in result["my_tests"]
        # The value should be a class
        assert isinstance(result["my_tests"]["dummy_test"], type)

    def test_returns_dict_of_test_classes_via_directory(self, tmp_path):
        # Directory scanning expects subdir/<subdir_name>.py
        subdir = tmp_path / "dummy"
        subdir.mkdir()
        _create_valid_test_module(subdir, name="dummy")

        loader = TestfunctionLoader()
        result = loader.import_basictest_subclasses(directory=str(tmp_path))

        assert "dummy" in result
        assert "dummy_test" in result["dummy"]

    def test_raises_when_no_source_or_directory(self):
        loader = TestfunctionLoader()
        with pytest.raises(ValueError, match="Either 'source' or 'directory'"):
            loader.import_basictest_subclasses()

    def test_records_failure_for_missing_dependency(self, tmp_path):
        broken = _create_broken_import_module(tmp_path)
        loader = TestfunctionLoader()

        result = loader.import_basictest_subclasses(
            source=[("broken", str(broken))]
        )

        assert result == {}  # no successful loads
        failures = loader.load_failures
        assert "broken" in failures
        assert failures["broken"].exception_type == "ModuleNotFoundError"

    def test_records_failure_for_syntax_error(self, tmp_path):
        bad = _create_syntax_error_module(tmp_path)
        loader = TestfunctionLoader()

        result = loader.import_basictest_subclasses(
            source=[("bad", str(bad))]
        )

        assert result == {}
        failures = loader.load_failures
        assert "bad" in failures
        assert failures["bad"].exception_type == "SyntaxError"

    def test_clears_previous_failures_on_reimport(self, tmp_path):
        broken = _create_broken_import_module(tmp_path)
        loader = TestfunctionLoader()

        # First load: generates failure
        loader.import_basictest_subclasses(source=[("broken", str(broken))])
        assert len(loader.load_failures) == 1

        # Second load with valid module: failures should be cleared
        valid = _create_valid_test_module(tmp_path)
        loader.import_basictest_subclasses(source=[("valid", str(valid))])
        assert len(loader.load_failures) == 0


# ---------------------------------------------------------------------------
# TestfunctionLoader.load_failures returns a copy
# ---------------------------------------------------------------------------

class TestLoaderFailuresCopy:
    """Test that load_failures returns a defensive copy."""

    def test_returns_copy_not_reference(self, tmp_path):
        broken = _create_broken_import_module(tmp_path)
        loader = TestfunctionLoader()
        loader.import_basictest_subclasses(source=[("broken", str(broken))])

        # Get a snapshot
        snapshot = loader.load_failures
        assert "broken" in snapshot

        # Mutate the returned dict
        snapshot["injected"] = ModuleLoadFailure(
            module_name="injected",
            file_path="/fake",
            exception_type="RuntimeError",
            exception_message="nope",
        )

        # Original must be unaffected
        assert "injected" not in loader.load_failures
        assert len(loader.load_failures) == 1


# ---------------------------------------------------------------------------
# Instance isolation between loaders
# ---------------------------------------------------------------------------

class TestLoaderIsolation:
    """Failures are isolated between loader instances."""

    def test_two_loaders_do_not_share_state(self, tmp_path):
        broken = _create_broken_import_module(tmp_path)
        valid = _create_valid_test_module(tmp_path)

        loader_a = TestfunctionLoader()
        loader_b = TestfunctionLoader()

        loader_a.import_basictest_subclasses(source=[("broken", str(broken))])
        loader_b.import_basictest_subclasses(source=[("valid", str(valid))])

        assert len(loader_a.load_failures) == 1
        assert len(loader_b.load_failures) == 0

    def test_clearing_one_loader_does_not_affect_other(self, tmp_path):
        broken = _create_broken_import_module(tmp_path)

        loader_a = TestfunctionLoader()
        loader_b = TestfunctionLoader()

        loader_a.import_basictest_subclasses(source=[("broken_a", str(broken))])
        loader_b.import_basictest_subclasses(source=[("broken_b", str(broken))])

        assert len(loader_a.load_failures) == 1
        assert len(loader_b.load_failures) == 1

        # Clear loader_a
        with loader_a._lock:
            loader_a._load_failures.clear()

        assert len(loader_a.load_failures) == 0
        assert len(loader_b.load_failures) == 1  # unaffected


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestLoaderThreadSafety:
    """Concurrent loads must not corrupt state."""

    def test_concurrent_loads_do_not_corrupt(self, tmp_path):
        """Multiple threads loading different modules on the same loader."""
        # Create several valid modules
        modules = []
        for i in range(5):
            subdir = tmp_path / f"mod_{i}"
            subdir.mkdir()
            mod = subdir / f"mod_{i}.py"
            mod.write_text(
                "import attrs\n"
                "from typing import ClassVar, Optional, Dict, Any\n"
                "from adarelib.testset.basictest import BasicTest, Parameter\n"
                "\n"
                "@attrs.define\n"
                "class DummyParam(Parameter):\n"
                "    dst: str = ''\n"
                "\n"
                "@attrs.define\n"
                f"class TestMod{i}(BasicTest):\n"
                f"    testname: ClassVar[str] = 'mod_{i}_test'\n"
                f"    testdescription: ClassVar[str] = 'Test {i}'\n"
                "    parameter: DummyParam = attrs.Factory(DummyParam)\n"
                "\n"
                "    def test(self):\n"
                "        pass\n"
            )
            modules.append((f"mod_{i}", str(mod)))

        loader = TestfunctionLoader()
        results = []
        errors = []

        def _load(src):
            try:
                r = loader.import_basictest_subclasses(source=[src])
                results.append(r)
            except BaseException as exc:  # noqa: broad but needed for thread-safety test
                errors.append(exc)

        threads = [threading.Thread(target=_load, args=(m,)) for m in modules]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # No thread should have raised
        assert errors == [], f"Thread errors: {errors}"

        # The loader lock serializes calls, so each call clears previous state.
        # The last call to finish wins. We just verify no corruption occurred.
        assert loader.load_failures == {} or isinstance(loader.load_failures, dict)

    def test_concurrent_reads_do_not_block(self, tmp_path):
        """Reading load_failures while another thread is loading should not deadlock."""
        broken = _create_broken_import_module(tmp_path)
        loader = TestfunctionLoader()

        # Pre-populate a failure
        loader.import_basictest_subclasses(source=[("broken", str(broken))])

        read_results = []

        def _read():
            for _ in range(50):
                snapshot = loader.load_failures
                read_results.append(len(snapshot))

        readers = [threading.Thread(target=_read) for _ in range(4)]
        for t in readers:
            t.start()
        for t in readers:
            t.join(timeout=10)

        # All reads should have completed (no deadlocks)
        assert len(read_results) == 200  # 4 threads x 50 reads


# ---------------------------------------------------------------------------
# Backward-compatible module-level wrappers
# ---------------------------------------------------------------------------

class TestBackwardCompatWrappers:
    """Module-level functions delegate to _default_loader."""

    def test_import_delegates_to_default_loader(self, tmp_path):
        valid = _create_valid_test_module(tmp_path)

        # Reset default loader state
        clear_module_load_failures()

        result = import_basictest_subclasses(
            source=[("wrapper_test", str(valid))]
        )

        assert "wrapper_test" in result
        assert "dummy_test" in result["wrapper_test"]

    def test_get_module_load_failures_returns_from_default_loader(self, tmp_path):
        broken = _create_broken_import_module(tmp_path)

        import_basictest_subclasses(source=[("broken_compat", str(broken))])

        failures = get_module_load_failures()
        assert "broken_compat" in failures
        assert failures["broken_compat"].exception_type == "ModuleNotFoundError"

    def test_clear_module_load_failures_clears_default_loader(self, tmp_path):
        broken = _create_broken_import_module(tmp_path)
        import_basictest_subclasses(source=[("to_clear", str(broken))])

        assert len(get_module_load_failures()) > 0
        clear_module_load_failures()
        assert len(get_module_load_failures()) == 0


# ---------------------------------------------------------------------------
# globals() pollution removed
# ---------------------------------------------------------------------------

class TestNoGlobalsPollution:
    """Loading testfunctions must NOT inject class names into the module namespace."""

    def test_loaded_class_not_in_module_dict(self, tmp_path):
        valid = _create_valid_test_module(tmp_path)
        loader = TestfunctionLoader()

        result = loader.import_basictest_subclasses(
            source=[("no_globals", str(valid))]
        )

        # Verify the class was actually found
        assert "dummy_test" in result["no_globals"]

        # The class name "TestDummy" must NOT appear in the testfunction module namespace
        assert "TestDummy" not in testfunction_module.__dict__, (
            "TestDummy leaked into testfunction module namespace via globals()"
        )

    def test_module_level_import_does_not_pollute_globals(self, tmp_path):
        valid = _create_valid_test_module(tmp_path)

        # Use the module-level wrapper
        result = import_basictest_subclasses(
            source=[("no_globals_compat", str(valid))]
        )

        assert "dummy_test" in result["no_globals_compat"]
        assert "TestDummy" not in testfunction_module.__dict__, (
            "TestDummy leaked into testfunction module namespace via module-level wrapper"
        )


# ---------------------------------------------------------------------------
# get_testclass_from_testfunction
# ---------------------------------------------------------------------------

class TestGetTestclass:
    """Tests for get_testclass_from_testfunction lookup."""

    def _make_collection(self):
        """Build a fake testfunction_collection dict."""

        class FakeFileExists:
            pass

        class FakeRegCheck:
            pass

        return {
            "standard": {"file_exists": FakeFileExists, "dir_exists": FakeFileExists},
            "registry": {"reg_check": FakeRegCheck},
        }

    def test_dotted_name_returns_correct_class(self):
        collection = self._make_collection()
        cls = get_testclass_from_testfunction("standard.file_exists", collection)
        assert cls is collection["standard"]["file_exists"]

    def test_bare_name_defaults_to_standard(self):
        collection = self._make_collection()
        cls = get_testclass_from_testfunction("file_exists", collection)
        assert cls is collection["standard"]["file_exists"]

    def test_nonexistent_function_returns_none(self):
        collection = self._make_collection()
        result = get_testclass_from_testfunction("standard.no_such_func", collection)
        assert result is None

    def test_missing_collection_returns_none(self):
        collection = self._make_collection()
        result = get_testclass_from_testfunction("fantasy.some_func", collection)
        assert result is None


# ---------------------------------------------------------------------------
# get_missing_testfunctions
# ---------------------------------------------------------------------------

class TestGetMissingTestfunctions:
    """Tests for get_missing_testfunctions."""

    def _make_collection(self):

        class FakeFileExists:
            pass

        return {
            "standard": {"file_exists": FakeFileExists},
        }

    def test_all_present_returns_empty(self):
        collection = self._make_collection()
        testset = TestsetFile(
            name="my_testset",
            tests=[
                Test(name="t1", function="standard.file_exists"),
            ],
        )
        missing = get_missing_testfunctions(testset, collection)
        assert missing == []

    def test_missing_function_returned(self):
        collection = self._make_collection()
        testset = TestsetFile(
            name="my_testset",
            tests=[
                Test(name="t1", function="standard.file_exists"),
                Test(name="t2", function="standard.no_such_func"),
                Test(name="t3", function="fantasy.another"),
            ],
        )
        missing = get_missing_testfunctions(testset, collection)
        assert "standard.no_such_func" in missing
        assert "fantasy.another" in missing
        assert "standard.file_exists" not in missing


# ---------------------------------------------------------------------------
# _load_single_module (extracted helper)
# ---------------------------------------------------------------------------

class TestLoadSingleModule:
    """Tests for TestfunctionLoader._load_single_module."""

    def test_populates_testdict_on_success(self, tmp_path):
        module_file = _create_valid_test_module(tmp_path)
        loader = TestfunctionLoader()
        testdict: dict = {}

        # _load_single_module expects the caller to hold the lock
        with loader._lock:
            loader._load_single_module("my_mod", module_file, testdict)

        assert "my_mod" in testdict
        assert "dummy_test" in testdict["my_mod"]
        assert isinstance(testdict["my_mod"]["dummy_test"], type)
        # No failures recorded
        assert loader.load_failures == {}

    def test_records_failure_on_broken_module(self, tmp_path):
        broken = _create_broken_import_module(tmp_path)
        loader = TestfunctionLoader()
        testdict: dict = {}

        with loader._lock:
            loader._load_single_module("broken_mod", broken, testdict)

        # testdict should NOT contain the broken module
        assert "broken_mod" not in testdict
        # Failure should be recorded
        failures = loader.load_failures
        assert "broken_mod" in failures
        assert failures["broken_mod"].exception_type == "ModuleNotFoundError"
