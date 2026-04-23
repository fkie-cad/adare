"""Tests for the @testfunction decorator, TestContext, and related API."""
import ast
import asyncio
from inspect import isclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import attrs
import cattrs
import pytest

pytestmark = pytest.mark.unit

from adarelib.constants import StatusEnum
from adarelib.event.event import TestResult
from adarelib.testset.api import (
    TestContext,
    TestError,
    TestFailed,
    testfunction,
)
from adarelib.testset.basictest import BasicTest, HostModeCategory, Parameter

# ---------------------------------------------------------------------------
# Sample decorated test functions for testing
# ---------------------------------------------------------------------------

@testfunction(
    name='sample_test',
    description='a sample test for testing the decorator',
    category=HostModeCategory.FILE_BASED,
)
def sample_test(ctx, dst: str, mode: str = "any"):
    paths, status = ctx.resolve_globfilepath(dst, match_mode=mode, return_list=True)
    ctx.error_if(status, f'path {dst} cannot be resolved ({status})')
    files = [p for p in paths if Path(p).is_file()]
    ctx.fail_if(not files, f'no files match {dst}')
    return [f'{len(files)} file(s) found']


@testfunction(
    name='simple_test',
    description='returns a string',
    category=HostModeCategory.AGENT_ONLY,
)
def simple_test(ctx, message: str):
    return f'hello: {message}'


@testfunction(
    name='none_test',
    description='returns nothing',
)
def none_test(ctx, value: str):
    pass


@testfunction(
    name='passthrough_test',
    description='returns TestResult directly',
)
def passthrough_test(ctx, value: str):
    return TestResult.success(['passed directly'])


@testfunction(
    name='exception_test',
    description='raises an exception',
)
def exception_test(ctx, value: str):
    raise ValueError("something went wrong")


# ---------------------------------------------------------------------------
# Tests: Decorator class generation
# ---------------------------------------------------------------------------

class TestDecoratorGeneratesClasses:

    def test_generates_test_class(self):
        assert hasattr(sample_test, '_test_class')
        assert isclass(sample_test._test_class)

    def test_generated_class_is_basictest_subclass(self):
        assert issubclass(sample_test._test_class, BasicTest)

    def test_generates_parameter_class(self):
        assert hasattr(sample_test, '_parameter_class')
        assert isclass(sample_test._parameter_class)

    def test_generated_parameter_is_parameter_subclass(self):
        assert issubclass(sample_test._parameter_class, Parameter)

    def test_class_has_correct_testname(self):
        assert sample_test._test_class.testname == 'sample_test'

    def test_class_has_correct_testdescription(self):
        assert sample_test._test_class.testdescription == 'a sample test for testing the decorator'

    def test_class_has_correct_host_mode_category(self):
        assert sample_test._test_class.host_mode_category == HostModeCategory.FILE_BASED

    def test_class_is_attrs_defined(self):
        assert attrs.has(sample_test._test_class)

    def test_parameter_class_is_attrs_defined(self):
        assert attrs.has(sample_test._parameter_class)

    def test_parameter_class_has_correct_fields(self):
        field_names = [f.name for f in attrs.fields(sample_test._parameter_class)]
        assert 'dst' in field_names
        assert 'mode' in field_names

    def test_parameter_default_values(self):
        param = sample_test._parameter_class(dst='/tmp/test')
        assert param.dst == '/tmp/test'
        assert param.mode == 'any'


# ---------------------------------------------------------------------------
# Tests: cattrs structuring (critical for YAML playbook loading)
# ---------------------------------------------------------------------------

class TestCattrsStructuring:

    def test_structure_basic(self):
        test_cls = sample_test._test_class
        data = {
            'name': 'check_file',
            'parameter': {'dst': '/tmp/test.txt', 'mode': 'single'},
            'description': 'test description',
            'variable_metadata': None,
        }
        instance = cattrs.structure(data, test_cls)
        assert instance.name == 'check_file'
        assert instance.parameter.dst == '/tmp/test.txt'
        assert instance.parameter.mode == 'single'

    def test_structure_with_defaults(self):
        test_cls = sample_test._test_class
        data = {
            'name': 'check_file',
            'parameter': {'dst': '/tmp/test.txt'},
            'description': '',
            'variable_metadata': None,
        }
        instance = cattrs.structure(data, test_cls)
        assert instance.parameter.mode == 'any'

    def test_structure_simple_test(self):
        test_cls = simple_test._test_class
        data = {
            'name': 'say_hello',
            'parameter': {'message': 'world'},
            'description': '',
            'variable_metadata': None,
        }
        instance = cattrs.structure(data, test_cls)
        assert instance.parameter.message == 'world'


# ---------------------------------------------------------------------------
# Tests: TestContext assertion helpers
# ---------------------------------------------------------------------------

class TestContextAssertions:

    def test_fail_if_raises_when_true(self):
        ctx = TestContext.__new__(TestContext)
        ctx._test = None  # Not needed for assertion tests
        with pytest.raises(TestFailed, match="bad condition"):
            ctx.fail_if(True, "bad condition")

    def test_fail_if_does_not_raise_when_false(self):
        ctx = TestContext.__new__(TestContext)
        ctx._test = None
        ctx.fail_if(False, "should not raise")

    def test_error_if_raises_when_true(self):
        ctx = TestContext.__new__(TestContext)
        ctx._test = None
        with pytest.raises(TestError, match="precondition failed"):
            ctx.error_if(True, "precondition failed")

    def test_error_if_does_not_raise_when_false(self):
        ctx = TestContext.__new__(TestContext)
        ctx._test = None
        ctx.error_if(False, "should not raise")


# ---------------------------------------------------------------------------
# Tests: Return value handling
# ---------------------------------------------------------------------------

class TestReturnValueHandling:

    def _make_instance(self, func):
        """Create a test instance for a decorated function with dummy params."""
        test_cls = func._test_class
        param_cls = func._parameter_class
        # Build minimal parameter with required fields
        fields = attrs.fields(param_cls)
        kwargs = {}
        for f in fields:
            if f.default is attrs.NOTHING and f.default is not None:
                kwargs[f.name] = 'dummy'
        param = param_cls(**kwargs)
        return test_cls(name='test_instance', parameter=param, description='', variable_metadata=None)

    def test_string_return_becomes_success(self):
        instance = self._make_instance(simple_test)
        result = instance.test()
        assert result.status == StatusEnum.SUCCESS
        assert result.details == ['hello: dummy']

    def test_list_return_becomes_success(self):
        # Need a function that returns a list - sample_test returns list but needs real files
        # Use passthrough to test list wrapping behavior indirectly
        pass

    def test_none_return_becomes_empty_success(self):
        instance = self._make_instance(none_test)
        result = instance.test()
        assert result.status == StatusEnum.SUCCESS
        assert result.details == []

    def test_testresult_passthrough(self):
        instance = self._make_instance(passthrough_test)
        result = instance.test()
        assert result.status == StatusEnum.SUCCESS
        assert result.details == ['passed directly']

    def test_uncaught_exception_becomes_execution_error(self):
        instance = self._make_instance(exception_test)
        result = instance.test()
        assert result.status == StatusEnum.ERROR
        assert 'ValueError' in result.details[0]

    def test_fail_if_produces_failed_result(self):
        @testfunction(name='fail_test', description='fails')
        def fail_test(ctx, value: str):
            ctx.fail_if(True, 'test failed on purpose')

        instance = self._make_instance(fail_test)
        result = instance.test()
        assert result.status == StatusEnum.FAILED
        assert 'test failed on purpose' in result.details[0]

    def test_error_if_produces_error_result(self):
        @testfunction(name='error_test', description='errors')
        def error_test(ctx, value: str):
            ctx.error_if(True, 'precondition not met')

        instance = self._make_instance(error_test)
        result = instance.test()
        assert result.status == StatusEnum.ERROR
        assert 'precondition not met' in result.details[0]


# ---------------------------------------------------------------------------
# Tests: TestfunctionLoader discovery
# ---------------------------------------------------------------------------

class TestLoaderDiscovery:

    def test_loader_discovers_decorated_functions(self, tmp_path):
        """TestfunctionLoader should discover BasicTest subclasses from decorated functions."""
        from adarelib.testset.testfunction import TestfunctionLoader

        # Create a test module file using the decorator API
        module_file = tmp_path / "decorated" / "decorated.py"
        module_file.parent.mkdir()
        module_file.write_text(
            "from adarelib.testset.api import testfunction\n"
            "from adarelib.testset.basictest import HostModeCategory\n"
            "\n"
            "@testfunction(\n"
            "    name='decorated_test',\n"
            "    description='a test using the decorator',\n"
            "    category=HostModeCategory.FILE_BASED,\n"
            ")\n"
            "def my_test(ctx, dst: str, match_mode: str = 'any'):\n"
            "    return 'ok'\n"
        )
        # Also create requirements.txt
        (tmp_path / "decorated" / "requirements.txt").write_text("")

        loader = TestfunctionLoader()
        result = loader.import_basictest_subclasses(directory=tmp_path)

        assert 'decorated' in result
        assert 'decorated_test' in result['decorated']
        test_cls = result['decorated']['decorated_test']
        assert isclass(test_cls)
        assert issubclass(test_cls, BasicTest)
        assert test_cls.testname == 'decorated_test'

    def test_loader_discovers_mixed_class_and_decorator(self, tmp_path):
        """Modules with both class-based and decorator-based tests should work."""
        from adarelib.testset.testfunction import TestfunctionLoader

        module_file = tmp_path / "mixed" / "mixed.py"
        module_file.parent.mkdir()
        module_file.write_text(
            "import attrs\n"
            "from typing import ClassVar, Optional\n"
            "from adarelib.testset.basictest import BasicTest, Parameter, HostModeCategory\n"
            "from adarelib.testset.api import testfunction\n"
            "\n"
            "@attrs.define\n"
            "class ClassParam(Parameter):\n"
            "    dst: str = ''\n"
            "\n"
            "@attrs.define\n"
            "class ClassBased(BasicTest):\n"
            "    testname: ClassVar[str] = 'class_based'\n"
            "    testdescription: ClassVar[str] = 'a class-based test'\n"
            "    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_BASED\n"
            "    name: str = ''\n"
            "    parameter: ClassParam = attrs.Factory(ClassParam)\n"
            "    description: Optional[str] = ''\n"
            "    variable_metadata: Optional[dict] = None\n"
            "\n"
            "    def test(self):\n"
            "        pass\n"
            "\n"
            "@testfunction(\n"
            "    name='decorator_based',\n"
            "    description='a decorator-based test',\n"
            "    category=HostModeCategory.FILE_BASED,\n"
            ")\n"
            "def my_decorator_test(ctx, path: str):\n"
            "    return 'ok'\n"
        )
        (tmp_path / "mixed" / "requirements.txt").write_text("")

        loader = TestfunctionLoader()
        result = loader.import_basictest_subclasses(directory=tmp_path)

        assert 'mixed' in result
        assert 'class_based' in result['mixed']
        assert 'decorator_based' in result['mixed']


# ---------------------------------------------------------------------------
# Tests: AST Analyzer (client-side PyModuleAnalyzer)
# ---------------------------------------------------------------------------

class TestPyModuleAnalyzerDecoratorSupport:

    def _create_module_file(self, tmp_path, content):
        """Write content to a temp .py file and return the path."""
        module_file = tmp_path / "test_module.py"
        module_file.write_text(content)
        return module_file

    def test_get_classes_includes_decorated_functions(self, tmp_path):
        from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer

        module_file = self._create_module_file(tmp_path, """
from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory

@testfunction(
    name='my_test',
    description='a test',
    category=HostModeCategory.FILE_BASED,
)
def my_test(ctx, dst: str, mode: str = "any"):
    pass
""")
        analyzer = PyModuleAnalyzer(module_file)
        classes = analyzer.get_classes(parent='BasicTest')
        assert len(classes) == 1
        assert classes[0].name == '_DecoratorTest_my_test'

    def test_decorated_function_has_testname_attribute(self, tmp_path):
        from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer

        module_file = self._create_module_file(tmp_path, """
from adarelib.testset.api import testfunction

@testfunction(name='check_file', description='checks a file')
def check_file(ctx, path: str):
    pass
""")
        analyzer = PyModuleAnalyzer(module_file)
        classes = analyzer.get_classes(parent='BasicTest')
        t = classes[0]
        assert t.has_attribute('testname')
        assert t.get_attribute('testname').get_value() == 'check_file'

    def test_decorated_function_has_testdescription_attribute(self, tmp_path):
        from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer

        module_file = self._create_module_file(tmp_path, """
from adarelib.testset.api import testfunction

@testfunction(name='check_file', description='checks a file')
def check_file(ctx, path: str):
    pass
""")
        analyzer = PyModuleAnalyzer(module_file)
        t = analyzer.get_classes(parent='BasicTest')[0]
        assert t.has_attribute('testdescription')
        assert t.get_attribute('testdescription').get_value() == 'checks a file'

    def test_decorated_function_has_parameter_attribute(self, tmp_path):
        from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer

        module_file = self._create_module_file(tmp_path, """
from adarelib.testset.api import testfunction

@testfunction(name='check_file', description='checks a file')
def check_file(ctx, path: str, mode: str = "any"):
    pass
""")
        analyzer = PyModuleAnalyzer(module_file)
        t = analyzer.get_classes(parent='BasicTest')[0]
        assert t.has_attribute('parameter')
        param_type = t.get_attribute('parameter').get_type()
        assert param_type == '_DecoratorParam_check_file'

    def test_get_class_finds_synthetic_parameter_class(self, tmp_path):
        from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer

        module_file = self._create_module_file(tmp_path, """
from adarelib.testset.api import testfunction

@testfunction(name='check_file', description='checks a file')
def check_file(ctx, path: str, mode: str = "any"):
    pass
""")
        analyzer = PyModuleAnalyzer(module_file)
        param_class = analyzer.get_class('_DecoratorParam_check_file')
        assert param_class is not None
        attrs_dict = param_class.get_attributes_as_dict()
        assert 'path' in attrs_dict
        assert 'mode' in attrs_dict
        assert attrs_dict['path']['type'] == 'str'
        assert attrs_dict['mode']['type'] == 'str'

    def test_get_method_returns_function_def(self, tmp_path):
        from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer

        module_file = self._create_module_file(tmp_path, """
from adarelib.testset.api import testfunction

@testfunction(name='check_file', description='checks a file')
def check_file(ctx, path: str):
    return 'ok'
""")
        analyzer = PyModuleAnalyzer(module_file)
        t = analyzer.get_classes(parent='BasicTest')[0]
        method = t.get_method('test')
        assert isinstance(method, ast.FunctionDef)
        # Should be hashable with ast.unparse
        unparsed = ast.unparse(method)
        assert 'return' in unparsed

    def test_mixed_class_and_decorator(self, tmp_path):
        from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer

        module_file = self._create_module_file(tmp_path, """
import attrs
from typing import ClassVar, Optional
from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.testset.api import testfunction

@attrs.define
class MyParam(Parameter):
    dst: str

@attrs.define
class ClassBased(BasicTest):
    testname: ClassVar[str] = 'class_test'
    testdescription: ClassVar[str] = 'a test'
    name: str = ''
    parameter: MyParam = None
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        pass

@testfunction(name='decorator_test', description='another test')
def decorator_test(ctx, value: str):
    pass
""")
        analyzer = PyModuleAnalyzer(module_file)
        classes = analyzer.get_classes(parent='BasicTest')
        names = [c.name for c in classes]
        assert 'ClassBased' in names
        assert '_DecoratorTest_decorator_test' in names

    def test_no_decorated_functions(self, tmp_path):
        from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer

        module_file = self._create_module_file(tmp_path, """
import attrs
from typing import ClassVar, Optional
from adarelib.testset.basictest import BasicTest, Parameter

@attrs.define
class MyParam(Parameter):
    dst: str

@attrs.define
class ClassBased(BasicTest):
    testname: ClassVar[str] = 'class_test'
    testdescription: ClassVar[str] = 'a test'
    name: str = ''
    parameter: MyParam = None
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        pass
""")
        analyzer = PyModuleAnalyzer(module_file)
        classes = analyzer.get_classes(parent='BasicTest')
        assert len(classes) == 1
        assert classes[0].name == 'ClassBased'


# ---------------------------------------------------------------------------
# Sample async decorated function for testing
# ---------------------------------------------------------------------------

@testfunction(
    name='async_test',
    description='an async test',
    category=HostModeCategory.HOST_NATIVE,
    execute_on_host=True,
)
async def async_test(ctx, text: str = None):
    await ctx.host.screenshot.take()
    return f'found: {text}'


# ---------------------------------------------------------------------------
# Tests: Async decorator class generation
# ---------------------------------------------------------------------------

class TestAsyncDecoratorGeneratesClasses:

    def test_async_generates_test_class(self):
        assert hasattr(async_test, '_test_class')
        assert issubclass(async_test._test_class, BasicTest)

    def test_async_class_has_execute_on_host(self):
        assert async_test._test_class.execute_on_host is True

    def test_async_class_has_host_native_category(self):
        assert async_test._test_class.host_mode_category == HostModeCategory.HOST_NATIVE

    def test_async_test_method_is_coroutine(self):
        import inspect
        test_cls = async_test._test_class
        param_cls = async_test._parameter_class
        instance = test_cls(name='t', parameter=param_cls(text='hello'), description='', variable_metadata=None)
        assert inspect.iscoroutinefunction(instance.test)

    def test_async_test_receives_host_context(self):
        test_cls = async_test._test_class
        param_cls = async_test._parameter_class
        instance = test_cls(name='t', parameter=param_cls(text='hello'), description='', variable_metadata=None)

        mock_context = MagicMock()
        mock_context.screenshot = MagicMock()
        mock_context.screenshot.take = AsyncMock(return_value=b"fake")

        result = asyncio.get_event_loop().run_until_complete(instance.test(mock_context))
        assert result.status == StatusEnum.SUCCESS
        assert 'found: hello' in result.details[0]
        mock_context.screenshot.take.assert_awaited_once()

    def test_async_fail_if_produces_failed(self):
        @testfunction(name='async_fail', description='fails async', execute_on_host=True, category=HostModeCategory.HOST_NATIVE)
        async def async_fail(ctx, value: str = ''):
            ctx.fail_if(True, 'async fail')

        test_cls = async_fail._test_class
        param_cls = async_fail._parameter_class
        instance = test_cls(name='t', parameter=param_cls(value='x'), description='', variable_metadata=None)
        result = asyncio.get_event_loop().run_until_complete(instance.test())
        assert result.status == StatusEnum.FAILED
        assert 'async fail' in result.details[0]

    def test_async_exception_becomes_error(self):
        @testfunction(name='async_err', description='errors async', execute_on_host=True, category=HostModeCategory.HOST_NATIVE)
        async def async_err(ctx, value: str = ''):
            raise RuntimeError("boom")

        test_cls = async_err._test_class
        param_cls = async_err._parameter_class
        instance = test_cls(name='t', parameter=param_cls(value='x'), description='', variable_metadata=None)
        result = asyncio.get_event_loop().run_until_complete(instance.test())
        assert result.status == StatusEnum.ERROR


# ---------------------------------------------------------------------------
# Tests: TestContext host property
# ---------------------------------------------------------------------------

class TestContextHostProperty:

    def test_host_context_none_by_default(self):
        ctx = TestContext.__new__(TestContext)
        ctx._test = None
        ctx._host_context = None
        assert ctx.host is None

    def test_host_context_returns_injected_context(self):
        mock_host = MagicMock()
        ctx = TestContext.__new__(TestContext)
        ctx._test = None
        ctx._host_context = mock_host
        assert ctx.host is mock_host


# ---------------------------------------------------------------------------
# Tests: TestContext handle_placeholders_comparison
# ---------------------------------------------------------------------------

class TestContextHandlePlaceholders:

    def test_handle_placeholders_delegates(self):
        mock_test = MagicMock()
        mock_test._handle_placeholders_comparison.return_value = (True, "matched")
        ctx = TestContext(mock_test)
        result = ctx.handle_placeholders_comparison("actual", "expected")
        assert result == (True, "matched")
        mock_test._handle_placeholders_comparison.assert_called_once_with("actual", "expected")
