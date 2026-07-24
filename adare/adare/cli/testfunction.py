# internal imports
# configure logging
import logging

from adare.api import AdareAPI
from adare.backend.basics import determine_projectdirectory
from adare.cli.utils import handle_api_error
from adare.console import print_success_message
from adare.core.dto.testfunction import TestfunctionCreateRequest, TestfunctionLoadRequest
from adare.exceptions import NoProjectFoundError, TestFunctionNotFoundError
from adare.helperfunctions.path_resolution import resolve_testfunction_path

log = logging.getLogger(__name__)


def exec_create_testfunction(arguments):
    """Create a new testfunction using AdareAPI."""
    if project_directory := determine_projectdirectory(arguments.project):
        testfunction_name = resolve_testfunction_path(arguments.name, project_directory)

        api = AdareAPI()
        result = api.testfunction.create(TestfunctionCreateRequest(
            project_path=project_directory,
            name=testfunction_name
        ))

        if result.success:
            print_success_message(
                title=f'Testfunction "{result.data.name}" created successfully!',
                location=str(result.data.file_path) if result.data.file_path else None,
                next_steps=result.data.next_steps,
                tip=result.data.tip
            )
        else:
            handle_api_error(result)
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_remove_testfunction(arguments):
    """Remove a testfunction using AdareAPI."""
    api = AdareAPI()

    # Check if force flag is set
    force = getattr(arguments, 'force', False)

    result = api.testfunction.remove(arguments.name, force=force)

    if result.success:
        print_success_message(
            title=f'Testfunction "{result.data.name}" removed successfully!'
        )
    else:
        handle_api_error(result)


def exec_load_testfunction(arguments):
    """Load a testfunction using AdareAPI."""
    from pathlib import Path

    # Get force flag if provided
    force = getattr(arguments, 'force', False)

    # Resolve the testfunction path
    testfunction_path = Path(arguments.name)

    # Resolve appdata via APPDATA_DIR (matching exec_sync_testfunctions); the
    # source layout is <APPDATA_DIR>/adare/adare/appdata/testfunctions/<name>.
    from adare.config.configdirectory import APPDATA_DIR
    appdata_testfunctions_root = APPDATA_DIR / 'adare' / 'adare' / 'appdata' / 'testfunctions'

    # If it's an absolute path or exists as given, use it directly
    if testfunction_path.is_absolute() or testfunction_path.exists():
        resolved_path = testfunction_path
    else:
        resolved_path = None

        # Try to find in adare appdata testfunctions directory
        appdata_testfunction_path = appdata_testfunctions_root / arguments.name
        if appdata_testfunction_path.exists():
            resolved_path = appdata_testfunction_path

        # Handle special case for "examples/testfunctions/xxx" pattern
        if resolved_path is None and arguments.name.startswith('examples/testfunctions/'):
            testfunction_name = arguments.name.split('/')[-1]  # Get the last part (e.g., "json")
            appdata_testfunction_path = appdata_testfunctions_root / testfunction_name
            if appdata_testfunction_path.exists():
                resolved_path = appdata_testfunction_path

        # Last fallback - try to resolve as relative to current directory
        if resolved_path is None:
            cwd_path = Path.cwd() / arguments.name
            if cwd_path.exists():
                resolved_path = cwd_path

    # If we couldn't resolve the path, error out
    if resolved_path is None:
        raise TestFunctionNotFoundError(log, message=f'testfunction "{arguments.name}" not found in any accessible location')

    # Use the API to load
    api = AdareAPI()
    result = api.testfunction.load(TestfunctionLoadRequest(
        path=resolved_path,
        force=force
    ))

    if result.success:
        print_success_message(
            title=f'Testfunction "{result.data.name}" loaded successfully!',
            next_steps=result.data.next_steps,
            tip=result.data.tip
        )
    else:
        handle_api_error(result)


def exec_list_testfunctions(arguments):
    """List testfunctions in the configured output format."""
    from adare.frontend.terminal.testfunction_list import print_testfunction_list
    from adare.run import get_formatter_from_context

    # Get formatter from CLI context
    formatter, output_file, dual_output = get_formatter_from_context()

    # Call enhanced frontend function with output format support
    testfunction_set = getattr(arguments, 'set', None)
    # Handle string 'None' that might come from Click
    if testfunction_set == 'None':
        testfunction_set = None
    print_testfunction_list(
        testfunction_file=testfunction_set,
        formatter=formatter,
        output_file=output_file,
        dual_output=dual_output
    )


def exec_sync_testfunctions(arguments):
    """Sync all testfunctions from appdata: hash-based create/update/skip."""
    from adare.backend.testfunction.commands import testfunction_sync_all
    from adare.config.configdirectory import APPDATA_DIR

    root = APPDATA_DIR / 'adare' / 'adare' / 'appdata' / 'testfunctions'
    if not root.is_dir():
        raise TestFunctionNotFoundError(log, message=f'testfunctions appdata directory not found: {root}')
    summary = testfunction_sync_all(root)

    print_success_message(
        title='Testfunction sync complete',
        next_steps=[
            f"created:   {', '.join(summary['created']) or '—'}",
            f"updated:   {', '.join(summary['updated']) or '—'}",
            f"unchanged: {', '.join(summary['unchanged']) or '—'}",
            f"skipped:   {', '.join(summary['skipped']) or '—'}",
        ],
    )


def _locate_collection_pyfile(lib: str, explicit_path: str | None):
    """Find a collection's <lib>/<lib>.py across known locations (offline).

    Search order: explicit --path, cwd testfunctions/, loaded global dir,
    shipped appdata source tree.
    """
    from pathlib import Path

    from adare.config.configdirectory import APPDATA_DIR, STATE_DIR

    candidates = []
    if explicit_path:
        p = Path(explicit_path)
        if p.is_file() and p.suffix == '.py':
            candidates.append(p)
        elif p.is_dir():
            candidates.append(p / f'{p.name}.py')
            candidates.append(p / f'{lib}.py')

    candidates.extend([
        Path.cwd() / 'testfunctions' / lib / f'{lib}.py',
        STATE_DIR / 'testfunctions' / lib / f'{lib}.py',
        APPDATA_DIR / 'adare' / 'adare' / 'appdata' / 'testfunctions' / lib / f'{lib}.py',
    ])

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _parse_param_value(raw: str):
    """Best-effort scalar coercion for --param k=v values (int/float/bool/None/str)."""
    lowered = raw.strip().lower()
    if lowered in ('true', 'false'):
        return lowered == 'true'
    if lowered in ('none', 'null'):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def exec_validate_testfunction(arguments):
    """Validate a candidate testfunction collection offline (no VM, no DB).

    Reports every authoring-contract violation with an actionable message:
    filename≠dirname, missing 'ctx', unannotated params, duplicate testnames,
    import/syntax errors, and missing dependencies.
    """
    from pathlib import Path

    from adarelib.testset.testfunction import (
        clear_module_load_failures,
        get_module_load_failures,
        import_basictest_subclasses,
    )

    path = Path(arguments.path)
    if not path.exists():
        raise TestFunctionNotFoundError(log, message=f'path "{arguments.path}" does not exist')

    issues: list[str] = []
    py_file = None

    if path.is_file() and path.suffix == '.py':
        py_file = path
        collection_dir = path.parent
        name = path.stem
    elif path.is_dir():
        collection_dir = path
        name = collection_dir.name
        expected = collection_dir / f'{name}.py'
        py_candidates = sorted(collection_dir.glob('*.py'))
        if expected.is_file():
            py_file = expected
        elif py_candidates:
            py_file = py_candidates[0]
            issues.append(
                f"filename ≠ dirname: expected '{name}.py' but found "
                f"{[p.name for p in py_candidates]}. The .py file must be named exactly "
                f"like its directory, or the collection is silently skipped on load."
            )
        else:
            issues.append(f"no .py file found in {collection_dir}")
    else:
        raise TestFunctionNotFoundError(
            log, message=f'"{arguments.path}" must be a testfunction directory or .py file'
        )

    discovered: dict = {}
    if py_file is not None:
        clear_module_load_failures()
        result = import_basictest_subclasses(source=[(name, py_file)])
        failures = get_module_load_failures()
        if name in failures:
            issues.append(failures[name].get_user_friendly_message())
        discovered = result.get(name, {})

    # requirements.txt sanity note (not an error — just informational)
    req = collection_dir / 'requirements.txt'
    req_note = None
    if req.is_file():
        deps = [
            ln.strip() for ln in req.read_text(encoding='utf-8').splitlines()
            if ln.strip() and not ln.strip().startswith('#')
        ]
        if deps:
            req_note = f"declares {len(deps)} dependency(ies): {', '.join(deps)}"

    if issues:
        from adare.console import console
        console.print(f'\n[bold red]✗ Validation failed for {name}[/bold red] ({len(issues)} issue(s)):')
        for i, issue in enumerate(issues, 1):
            console.print(f'  [red]({i})[/red] {issue}')
        if discovered:
            console.print(f'\n  Loadable tests despite issues: {", ".join(sorted(discovered))}')
        console.print()
        exit(1)

    from adare.console import console
    console.print(f'\n[bold green]✓ {name} is valid[/bold green]')
    console.print(f'  tests: {", ".join(sorted(discovered)) or "—"}')
    if req_note:
        console.print(f'  requirements.txt {req_note}')
    console.print()


def exec_dry_run_testfunction(arguments):
    """Execute a single testfunction against a local sample path (no VM).

    Scope: FILE_BASED / FILE_CONTENT only — host/async and QGA tests need a live
    ctx.host / guest and are out of scope for this offline harness.
    """
    import cattrs

    from adarelib.testset.basictest import HostModeCategory
    from adarelib.testset.testfunction import (
        clear_module_load_failures,
        get_module_load_failures,
        get_testclass_from_testfunction,
        import_basictest_subclasses,
    )

    target = arguments.target
    if '.' not in target:
        raise TestFunctionNotFoundError(
            log, message=f'target "{target}" must be in <collection>.<function> form (e.g. mycollection.file_contains_word)'
        )
    lib, func = target.split('.', 1)

    py_file = _locate_collection_pyfile(lib, getattr(arguments, 'path', None))
    if py_file is None:
        raise TestFunctionNotFoundError(
            log,
            message=f'could not locate collection "{lib}" — pass --path <collection dir> or load it first',
        )

    clear_module_load_failures()
    collection = import_basictest_subclasses(source=[(lib, py_file)])
    failures = get_module_load_failures()
    if lib in failures:
        from adare.console import console
        console.print(f'[red]✗ {failures[lib].get_user_friendly_message()}[/red]')
        exit(1)

    testclass = get_testclass_from_testfunction(target, collection)
    if testclass is None:
        available = ', '.join(sorted(collection.get(lib, {}))) or '—'
        raise TestFunctionNotFoundError(
            log, message=f'function "{func}" not found in collection "{lib}". Available: {available}'
        )

    category = getattr(testclass, 'host_mode_category', HostModeCategory.AGENT_ONLY)
    if category not in (HostModeCategory.FILE_BASED, HostModeCategory.FILE_CONTENT):
        raise TestFunctionNotFoundError(
            log,
            message=(
                f'dry-run supports FILE_BASED / FILE_CONTENT tests only; '
                f'"{target}" is {category.value} and needs a live host/guest context.'
            ),
        )

    # Build parameters from --param k=v (repeatable) and --file (as dst default).
    params: dict = {}
    for pair in getattr(arguments, 'param', None) or ():
        if '=' not in pair:
            raise TestFunctionNotFoundError(log, message=f'invalid --param "{pair}" (expected key=value)')
        key, value = pair.split('=', 1)
        params[key.strip()] = _parse_param_value(value)

    sample = getattr(arguments, 'file', None)
    if sample and 'dst' not in params:
        params['dst'] = sample

    test_dict = {
        'name': f'dryrun_{func}',
        'parameter': params,
        'description': '',
        'variable_metadata': None,
    }

    from adare.console import console
    try:
        test_instance = cattrs.structure(test_dict, testclass)
    except cattrs.errors.ClassValidationError as e:
        console.print(f'[red]✗ parameter validation failed for {target}:[/red] {e}')
        console.print('[yellow]  check --param names/types against the function signature[/yellow]')
        exit(1)

    result = test_instance.test()

    from adarelib.constants import StatusEnum
    status_name = StatusEnum(result.status).name
    color = StatusEnum.get_color(result.status) or 'white'
    console.print(f'\n[bold]{target}[/bold] (sample: {sample or params.get("dst", "—")})')
    console.print(f'  status: [{color}]{status_name}[/{color}]')
    if result.details:
        console.print('  details:')
        for detail in result.details:
            console.print(f'    - {detail}')
    console.print()


def exec_check_testfunction_exists(arguments):
    """Check if a testfunction exists in the database using AdareAPI."""
    from pathlib import Path

    # Extract testfunction name from path if it's a directory
    testfunction_name = Path(arguments.name).name if Path(arguments.name).is_dir() else arguments.name

    api = AdareAPI()
    result = api.testfunction.exists(testfunction_name)

    if result.success:
        if result.data.exists:
            print("exists")
            exit(0)
        else:
            print("not_found")
            exit(1)
    else:
        handle_api_error(result)
