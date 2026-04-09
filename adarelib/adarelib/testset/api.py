# external imports
import sys
import inspect
import attrs
from typing import ClassVar, Optional, Dict, Any

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter, HostModeCategory
from adarelib.event.event import TestResult

# configure logging
import logging

log = logging.getLogger(__name__)


class TestFailed(Exception):
    """Raised by ctx.fail_if when a test condition is not met."""
    pass


class TestError(Exception):
    """Raised by ctx.error_if when a precondition/setup fails."""
    pass


class TestContext:
    """Wraps a BasicTest instance to provide helper methods to decorated test functions."""

    def __init__(self, test_instance: BasicTest, host_context=None):
        self._test = test_instance
        self._host_context = host_context

    @property
    def host(self):
        """Access host context (screenshot, cv, vm_file) — only available in host-mode tests."""
        return self._host_context

    # Assertion methods

    def fail_if(self, condition: bool, message: str):
        """Fail the test if condition is truthy."""
        if condition:
            raise TestFailed(message)

    def error_if(self, condition: bool, message: str):
        """Error the test if condition is truthy (precondition/setup issue)."""
        if condition:
            raise TestError(message)

    # Delegated helpers from BasicTest

    def resolve_globfilepath(self, globfilepath: str, match_mode: str = "single",
                             return_list: bool = False):
        return self._test.resolve_globfilepath(globfilepath, match_mode=match_mode, return_list=return_list)

    def has_placeholders(self, text: str) -> bool:
        return self._test.has_placeholders(text)

    def get_placeholders(self, text: str) -> list:
        return self._test.get_placeholders(text)

    def resolve_variables(self, text: str) -> str:
        return self._test.resolve_variables(text)

    def compare_with_placeholder(self, placeholder_name: str, actual_value: str):
        return self._test.compare_with_placeholder(placeholder_name, actual_value)

    def get_placeholder_metadata(self, placeholder_name: str) -> Dict[str, Any]:
        return self._test.get_placeholder_metadata(placeholder_name)

    def has_tolerance_metadata(self, placeholder_name: str) -> bool:
        return self._test.has_tolerance_metadata(placeholder_name)

    def handle_placeholders_comparison(self, actual_content, expected_template):
        return self._test._handle_placeholders_comparison(actual_content, expected_template)

    @property
    def variable_metadata(self) -> Optional[Dict[str, Any]]:
        return self._test.variable_metadata


def _build_type_annotation_map(sig: inspect.Signature) -> dict:
    """Extract parameter names, types, and defaults from a function signature (skipping 'ctx')."""
    params = []
    for name, param in sig.parameters.items():
        if name == 'ctx':
            continue
        annotation = param.annotation if param.annotation is not inspect.Parameter.empty else str
        default = param.default if param.default is not inspect.Parameter.empty else attrs.NOTHING
        params.append((name, annotation, default))
    return params


def _make_parameter_class(func_name: str, param_specs: list) -> type:
    """Dynamically create a Parameter subclass with proper type annotations for cattrs."""
    annotations = {}
    namespace = {}
    for name, annotation, default in param_specs:
        annotations[name] = annotation
        if default is not attrs.NOTHING:
            namespace[name] = default

    namespace['__annotations__'] = annotations
    param_cls = type(f'_DecoratorParam_{func_name}', (Parameter,), namespace)
    param_cls = attrs.define(param_cls)
    return param_cls


def _make_test_class(func_name: str, testname: str, testdescription: str,
                     host_mode_category: HostModeCategory, execute_on_host: bool,
                     param_cls: type, test_func) -> type:
    """Dynamically create a BasicTest subclass that calls the decorated function."""

    is_async = inspect.iscoroutinefunction(test_func)

    def _convert_result(result):
        """Convert a test function's return value to a TestResult."""
        if isinstance(result, TestResult):
            return result
        elif result is None:
            return TestResult.success([])
        elif isinstance(result, str):
            return TestResult.success([result])
        elif isinstance(result, list):
            return TestResult.success(result)
        else:
            return TestResult.success([str(result)])

    if is_async:
        async def test_method(self, context=None):
            ctx = TestContext(self, host_context=context)
            kwargs = attrs.asdict(self.parameter)
            try:
                result = await test_func(ctx, **kwargs)
            except TestFailed as e:
                return TestResult.failed([str(e)])
            except TestError as e:
                return TestResult.error([str(e)])
            except Exception as e:
                return TestResult.execution_error(e, f"Error in testfunction '{testname}'")
            return _convert_result(result)
    else:
        def test_method(self):
            ctx = TestContext(self)
            kwargs = attrs.asdict(self.parameter)
            try:
                result = test_func(ctx, **kwargs)
            except TestFailed as e:
                return TestResult.failed([str(e)])
            except TestError as e:
                return TestResult.error([str(e)])
            except Exception as e:
                return TestResult.execution_error(e, f"Error in testfunction '{testname}'")
            return _convert_result(result)

    # Build the class using type() + @attrs.define for proper cattrs compatibility
    namespace = {
        '__annotations__': {
            'name': str,
            'parameter': param_cls,
            'description': Optional[str],
            'variable_metadata': Optional[dict],
        },
        'description': '',
        'variable_metadata': None,
        # ClassVars
        'testname': testname,
        'testdescription': testdescription,
        'host_mode_category': host_mode_category,
        'execute_on_host': execute_on_host,
        # Method
        'test': test_method,
    }

    test_cls = type(f'_DecoratorTest_{func_name}', (BasicTest,), namespace)
    test_cls = attrs.define(test_cls)
    return test_cls


def testfunction(name: str, description: str,
                 category: HostModeCategory = HostModeCategory.AGENT_ONLY,
                 execute_on_host: bool = False):
    """
    Decorator that turns a plain function into a BasicTest subclass.

    The decorated function should accept (ctx, **params) where ctx is a TestContext
    and params are extracted from the function signature annotations.

    Usage:
        @testfunction(
            name='file_exists',
            description='tests if file(s) exist',
            category=HostModeCategory.FILE_BASED,
        )
        def file_exists(ctx, dst: str, match_mode: str = "any"):
            paths, status = ctx.resolve_globfilepath(dst, match_mode=match_mode, return_list=True)
            ctx.error_if(status, f'path {dst} cannot be resolved ({status})')
            files = [p for p in paths if Path(p).is_file()]
            ctx.fail_if(not files, f'no files match {dst}')
            return [f'{len(files)} file(s) found', f'files: {", ".join(files)}']

    Returns:
        The decorated function, with a generated BasicTest subclass attached
        as `_test_class` attribute and registered as a module-level name.
    """
    def decorator(func):
        sig = inspect.signature(func)
        param_specs = _build_type_annotation_map(sig)

        param_cls = _make_parameter_class(func.__name__, param_specs)
        test_cls = _make_test_class(
            func.__name__, name, description, category, execute_on_host,
            param_cls, func
        )

        # Register the generated class in the caller's module so TestfunctionLoader
        # can discover it via dir(module) + isclass() + issubclass(cls, BasicTest).
        # Use frame-based injection because the module may not be in sys.modules
        # (e.g., when loaded via importlib.util.spec_from_file_location).
        class_attr_name = f'_DecoratorTest_{func.__name__}'
        caller_module = sys.modules.get(func.__module__)
        if caller_module is not None:
            setattr(caller_module, class_attr_name, test_cls)
        else:
            # Fallback: inject into the caller's global namespace directly
            caller_globals = sys._getframe(1).f_globals
            caller_globals[class_attr_name] = test_cls

        # Attach to the function for direct access
        func._test_class = test_cls
        func._parameter_class = param_cls

        return func

    return decorator
