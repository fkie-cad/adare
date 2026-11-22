# external imports
import inspect

# configure logging
import logging
import re
import shutil
import sys
import tempfile
from typing import Any, Optional

import attrs

from adarelib.event.event import TestResult

# internal imports
from adarelib.testset import archive
from adarelib.testset.basictest import BasicTest, HostModeCategory, Parameter, PlaceholderError

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
        # Archive members (dst: 'a.tar.gz!/x.json') are extracted into a per-test temp dir,
        # created on first use and removed by close().
        self._archive_workdir: str | None = None
        self._archive_details: list[str] = []
        self._archive_display: dict[str, str] = {}

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

    def resolve_globfilepath(self, globfilepath: str, match_mode: str = "single", return_list: bool = False):
        """Resolve a guest path (glob allowed) to a local file path, as BasicTest does.

        A path with an archive separator (``backup.tar.gz!/etc/app.json``) resolves to the
        member, extracted into a temp dir: a missing member gives a path that does not exist
        (like a missing plain file); an unusable archive gives an empty path and a status
        (the test ERRORs). See :mod:`adarelib.testset.archive`.
        """
        if archive.has_archive_separator(globfilepath):
            return self._resolve_archive_path(globfilepath, match_mode, return_list)
        return self._test.resolve_globfilepath(globfilepath, match_mode=match_mode, return_list=return_list)

    def _resolve_archive_path(self, path: str, match_mode: str, return_list: bool):
        empty = [] if return_list else ''
        archive_part, members = archive.split_archive_path(path)
        # the archive itself must be exactly one file, also for a glob
        archive_path, status = self._test.resolve_globfilepath(archive_part, match_mode='single')
        if status:
            return empty, f'archive {archive_part}: {status}'
        if self._archive_workdir is None:
            self._archive_workdir = tempfile.mkdtemp(prefix='adare-archive-')
        workdir = tempfile.mkdtemp(dir=self._archive_workdir)
        try:
            resolution = archive.resolve_archive_path(
                archive_path,
                members,
                workdir,
                match_mode=match_mode,
                max_bytes=archive.max_bytes_from_env(),
                companions=tuple(getattr(type(self._test), 'host_mode_sidecars', ())),
            )
        except archive.ArchiveError as e:
            return empty, f'archive error: {e}'
        self._archive_details.extend(resolution.details)
        self._archive_display.update(resolution.display)
        if resolution.status:
            return empty, resolution.status
        if return_list:
            return list(resolution.paths), ''
        return (resolution.paths[0] if resolution.paths else ''), ''

    def _finish(self, result: TestResult) -> TestResult:
        """Add archive provenance to the result and show members by their archive path."""
        if not self._archive_details and not self._archive_display:
            return result
        details = []
        for detail in result.details:
            if isinstance(detail, str):
                # longest first, so a path is never replaced inside a longer one
                for local in sorted(self._archive_display, key=len, reverse=True):
                    detail = detail.replace(local, self._archive_display[local])
            details.append(detail)
        result.details = details + [d for d in self._archive_details if d not in details]
        return result

    def close(self) -> None:
        """Remove files extracted from archives during this test."""
        if self._archive_workdir is not None:
            shutil.rmtree(self._archive_workdir, ignore_errors=True)
            self._archive_workdir = None

    def has_placeholders(self, text: str) -> bool:
        return self._test.has_placeholders(text)

    def get_placeholders(self, text: str) -> list:
        return self._test.get_placeholders(text)

    def resolve_variables(self, text: str) -> str:
        return self._test.resolve_variables(text)

    def compare_with_placeholder(self, placeholder_name: str, actual_value: str):
        return self._test.compare_with_placeholder(placeholder_name, actual_value)

    def get_placeholder_metadata(self, placeholder_name: str) -> dict[str, Any]:
        return self._test.get_placeholder_metadata(placeholder_name)

    def has_tolerance_metadata(self, placeholder_name: str) -> bool:
        return self._test.has_tolerance_metadata(placeholder_name)

    def handle_placeholders_comparison(self, actual_content, expected_template):
        return self._test._handle_placeholders_comparison(actual_content, expected_template)

    @property
    def variable_metadata(self) -> dict[str, Any] | None:
        return self._test.variable_metadata


def _validate_signature(func, testname: str, sig: inspect.Signature) -> None:
    """Enforce the authoring contract on a decorated test function's signature.

    Raised at decoration time (i.e. at module import/load) so a malformed
    testfunction fails loudly with an actionable message rather than misbehaving
    silently — e.g. an unannotated parameter would otherwise default to `str`
    and structure wrong values from the playbook.
    """
    params = list(sig.parameters.values())
    location = f"testfunction '{testname}' (function {func.__name__})"

    if not params or params[0].name != 'ctx':
        raise ValueError(
            f"{location}: first parameter must be 'ctx' "
            f"(got {params[0].name!r} — signature: def {func.__name__}(ctx, ...))"
            if params
            else f"{location}: must accept 'ctx' as its first parameter (signature: def {func.__name__}(ctx, ...))"
        )

    unannotated = [
        p.name
        for p in params[1:]
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        and p.annotation is inspect.Parameter.empty
    ]
    if unannotated:
        raise ValueError(
            f"{location}: parameter(s) {', '.join(unannotated)} lack type annotations. "
            f"Annotate every parameter (e.g. `dst: str`) — annotations drive cattrs "
            f"validation of playbook `parameter:` blocks."
        )


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


def _result_from_exception(e: Exception, testname: str) -> TestResult:
    """The result for an exception a testfunction raised (always ERROR, except TestFailed)."""
    if isinstance(e, TestFailed):
        return TestResult.failed([str(e)])
    if isinstance(e, TestError):
        return TestResult.error([str(e)])
    if isinstance(e, PlaceholderError):
        return TestResult.error([f'placeholder error: {e}'])
    if isinstance(e, re.error):  # an invalid regex parameter: a test-definition problem, no trace needed
        return TestResult.error([str(e) if 'regex' in str(e) else f'invalid regex: {e}'])
    return TestResult.execution_error(e, f"Error in testfunction '{testname}'")


def _make_test_class(
    func_name: str,
    testname: str,
    testdescription: str,
    host_mode_category: HostModeCategory,
    execute_on_host: bool,
    param_cls: type,
    test_func,
) -> type:
    """Dynamically create a BasicTest subclass that calls the decorated function."""

    is_async = inspect.iscoroutinefunction(test_func)

    def _convert_result(result):
        """Convert a test function's return value to a TestResult."""
        if isinstance(result, TestResult):
            return result
        if result is None:
            return TestResult.success([])
        if isinstance(result, str):
            return TestResult.success([result])
        if isinstance(result, list):
            return TestResult.success(result)
        return TestResult.success([str(result)])

    # Every result goes through ctx._finish (archive provenance) and ctx.close removes
    # files extracted from archives, whatever the outcome.
    if is_async:

        async def test_method(self, context=None):
            ctx = TestContext(self, host_context=context)
            kwargs = attrs.asdict(self.parameter)
            try:
                try:
                    result = _convert_result(await test_func(ctx, **kwargs))
                except Exception as e:  # a testfunction may raise anything: report it as ERROR
                    result = _result_from_exception(e, testname)
                return ctx._finish(result)
            finally:
                ctx.close()
    else:

        def test_method(self):
            ctx = TestContext(self)
            kwargs = attrs.asdict(self.parameter)
            try:
                try:
                    result = _convert_result(test_func(ctx, **kwargs))
                except Exception as e:  # a testfunction may raise anything: report it as ERROR
                    result = _result_from_exception(e, testname)
                return ctx._finish(result)
            finally:
                ctx.close()

    # Build the class using type() + @attrs.define for proper cattrs compatibility
    namespace = {
        '__annotations__': {
            'name': str,
            'parameter': param_cls,
            # Runtime annotations consumed by attrs/cattrs structuring on the guest;
            # kept as typing.Optional until `X | None` is verified there.
            'description': Optional[str],  # noqa: UP045
            'variable_metadata': Optional[dict],  # noqa: UP045
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


def testfunction(
    name: str,
    description: str,
    category: HostModeCategory = HostModeCategory.AGENT_ONLY,
    execute_on_host: bool = False,
    negative: bool = False,
):
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

    ``negative=True`` declares that a pass asserts an absence (deleted, never written, not
    shown): the host then reports an unproven pass as INCONCLUSIVE (see BasicTest.negative).

    Returns:
        The decorated function, with a generated BasicTest subclass attached
        as `_test_class` attribute and registered as a module-level name.
    """

    def decorator(func):
        sig = inspect.signature(func)
        _validate_signature(func, name, sig)
        param_specs = _build_type_annotation_map(sig)

        param_cls = _make_parameter_class(func.__name__, param_specs)
        test_cls = _make_test_class(func.__name__, name, description, category, execute_on_host, param_cls, func)
        test_cls.negative = negative  # a pass asserts an absence (see BasicTest.negative)

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
