"""CLI output foundation: format precedence, plain rendering, errors, exit codes, status.

These pin the conventions every read-only command builds on (see
``adare/cli/output.py`` and ``adare/cli/errors.py``):

* format precedence: subcommand --json/--format > global --format > $ADARE_FORMAT > auto;
* plain (TSV) output when stdout is not a terminal;
* one error message on stderr, a JSON document in json mode;
* exit codes 0 ok / 1 error / 2 usage / 3 not found.
"""
import json
import logging
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from adare.cli.errors import (
    EXIT_ERROR,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_USAGE,
    error_code_for,
    exit_code_for,
)
from adare.cli.output import OUTPUT_EPILOG, output_options, resolve_output_format
from adare.helperfunctions.output_formatter import OutputFormat, get_formatter
from adare.helperfunctions.plain_output import render_plain

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# A miniature CLI with the same root options as `adare`, so precedence can be
# exercised end to end through the real decorator.
# ---------------------------------------------------------------------------

def _make_cli():
    from adare.run import AliasedGroup

    @click.group(cls=AliasedGroup)
    @click.option('--output-format', '--format', 'output_format', default=None,
                  type=click.Choice(['rich', 'plain', 'json', 'yaml']))
    @click.pass_context
    def root(ctx, output_format):
        ctx.ensure_object(SimpleNamespace)
        ctx.obj.output_format = output_format
        ctx.obj.output_file = None
        ctx.obj.very_verbose = False

    @root.command(name='show')
    @output_options
    def show():
        click.echo(resolve_output_format())

    @root.command(name='table-only')
    @output_options(structured=False)
    def table_only():
        click.echo('table')

    return root


@pytest.fixture
def mini_cli(monkeypatch):
    monkeypatch.delenv('ADARE_FORMAT', raising=False)
    return _make_cli()


class TestFormatPrecedence:
    def test_auto_is_plain_when_stdout_is_not_a_tty(self, mini_cli):
        result = CliRunner().invoke(mini_cli, ['show'])
        assert result.exit_code == 0
        assert result.stdout.strip() == 'plain'

    def test_auto_is_rich_on_a_tty(self, monkeypatch):
        monkeypatch.delenv('ADARE_FORMAT', raising=False)
        monkeypatch.setattr('adare.cli.output._stdout_is_tty', lambda: True)
        ctx = click.Context(click.Command('x'), obj=SimpleNamespace(output_format=None))
        assert resolve_output_format(ctx) == 'rich'

    def test_env_var_beats_auto(self, mini_cli, monkeypatch):
        monkeypatch.setenv('ADARE_FORMAT', 'yaml')
        assert CliRunner().invoke(mini_cli, ['show']).stdout.strip() == 'yaml'

    def test_invalid_env_var_is_ignored(self, mini_cli, monkeypatch):
        monkeypatch.setenv('ADARE_FORMAT', 'xml')
        assert CliRunner().invoke(mini_cli, ['show']).stdout.strip() == 'plain'

    def test_global_flag_beats_env_var(self, mini_cli, monkeypatch):
        monkeypatch.setenv('ADARE_FORMAT', 'yaml')
        result = CliRunner().invoke(mini_cli, ['--format', 'rich', 'show'])
        assert result.stdout.strip() == 'rich'

    def test_subcommand_flag_beats_global_flag(self, mini_cli, monkeypatch):
        monkeypatch.setenv('ADARE_FORMAT', 'plain')
        result = CliRunner().invoke(mini_cli, ['--format', 'yaml', 'show', '--format', 'rich'])
        assert result.stdout.strip() == 'rich'

    def test_json_shorthand(self, mini_cli):
        result = CliRunner().invoke(mini_cli, ['--format', 'yaml', 'show', '--json'])
        assert result.stdout.strip() == 'json'

    def test_json_conflicting_with_other_format_is_a_usage_error(self, mini_cli):
        result = CliRunner().invoke(mini_cli, ['show', '--json', '--format', 'yaml'])
        assert result.exit_code == EXIT_USAGE

    def test_json_with_matching_format_is_fine(self, mini_cli):
        result = CliRunner().invoke(mini_cli, ['show', '--json', '--format', 'json'])
        assert result.exit_code == 0
        assert result.stdout.strip() == 'json'

    def test_no_context_keeps_rich_for_library_callers(self, monkeypatch):
        monkeypatch.setenv('ADARE_FORMAT', 'json')
        assert resolve_output_format() == 'rich'

    def test_unstructured_command_refuses_json(self, mini_cli):
        result = CliRunner().invoke(mini_cli, ['table-only', '--json'])
        assert result.exit_code == EXIT_USAGE
        assert 'does not support structured output' in result.stderr

    def test_unstructured_command_allows_plain(self, mini_cli):
        result = CliRunner().invoke(mini_cli, ['table-only', '--format', 'plain'])
        assert result.exit_code == 0
        assert result.stdout.strip() == 'table'

    def test_decorated_command_gets_the_help_epilog(self, mini_cli):
        result = CliRunner().invoke(mini_cli, ['show', '--help'])
        assert '--json' in result.stdout
        assert mini_cli.commands['show'].epilog == OUTPUT_EPILOG


# ---------------------------------------------------------------------------
# Plain rendering
# ---------------------------------------------------------------------------

class TestPlainRendering:
    ULID = '01KMX521675QWFY2PJ7VD9RVZB'

    def test_list_envelope_renders_tsv_with_header(self):
        data = {'environments': [
            {'ulid': self.ULID, 'name': 'ubuntu', 'published': False, 'tags': ['a', 'b']},
            {'ulid': '01KN0687A86EBMP7ND5AAH7G4A', 'name': 'win', 'published': True, 'tags': []},
        ]}
        lines = render_plain(data).split('\n')
        assert lines[0] == 'ulid\tname\tpublished\ttags'
        assert lines[1] == f'{self.ULID}\tubuntu\tfalse\ta,b'
        assert lines[2] == '01KN0687A86EBMP7ND5AAH7G4A\twin\ttrue\t'

    def test_ids_are_never_truncated(self):
        long_value = 'x' * 300
        assert long_value in render_plain([{'id': long_value}])

    def test_nested_flat_dicts_become_dotted_columns(self):
        out = render_plain([{'vm': {'id': 'V1', 'name': 'vm1'}, 'disk': {'present': True}}])
        assert out.split('\n')[0] == 'vm.id\tvm.name\tdisk.present'
        assert out.split('\n')[1] == 'V1\tvm1\ttrue'

    def test_tabs_and_newlines_inside_values_stay_in_one_cell(self):
        out = render_plain([{'a': 'one\ttwo\nthree', 'b': 'x'}])
        assert out.split('\n')[1] == 'one two three\tx'

    def test_single_record_is_key_value_lines_with_nested_tables(self):
        out = render_plain({'name': 'exp', 'ok': True, 'none': None,
                            'tests': {'t1': {'name': 't1', 'missing': True}}})
        assert 'name\texp' in out
        assert 'ok\ttrue' in out
        assert 'none\t' in out.split('\n')
        assert '# tests\nname\tmissing\nt1\ttrue' in out

    def test_empty_list_prints_nothing(self):
        assert render_plain({'environments': []}) == ''

    def test_formatter_plain_has_no_markup_colour_or_box_drawing(self):
        formatter = get_formatter('plain')
        assert formatter.format_type is OutputFormat.PLAIN
        assert formatter.format_type.is_structured
        out = formatter.format({'items': [{'name': '[bold]x[/bold]', 'status': ':white_check_mark: ok'}]})
        assert out == 'name\tstatus\nx\tok'
        assert '\x1b[' not in out
        assert not any(ch in out for ch in '─│╭╮╰╯┃━')

    def test_brackets_and_colons_in_data_survive(self):
        out = get_formatter('json').format({'d': '[WIP] a:b:c', 'p': 'C:\\x'})
        assert json.loads(out) == {'d': '[WIP] a:b:c', 'p': 'C:\\x'}

    def test_numpy_bools_and_int_enums_serialize_as_real_types(self):
        import numpy as np

        from adarelib.constants import StatusEnum
        out = json.loads(get_formatter('json').format(
            {'present': np.bool_(True), 'status': StatusEnum.FINISHED, 'n': np.int64(3)}))
        assert out == {'present': True, 'status': 'finished', 'n': 3}


# ---------------------------------------------------------------------------
# Error codes, exit codes, error rendering
# ---------------------------------------------------------------------------

class TestExitCodeMapping:
    @pytest.mark.parametrize('name, code', [
        ('TestFunctionNotFoundError', 'TESTFUNCTION_NOT_FOUND'),
        ('VMNotFoundError', 'VM_NOT_FOUND'),
        ('RunNotFoundError', 'RUN_NOT_FOUND'),
        ('ArgumentsError', 'ARGUMENTS'),
        ('EnvironmentDoesNotExistInDatabase', 'ENVIRONMENT_DOES_NOT_EXIST_IN_DATABASE'),
        ('SESSION_NOT_FOUND', 'SESSION_NOT_FOUND'),
        ('HypervisorException', 'HYPERVISOR'),
    ])
    def test_error_code_for(self, name, code):
        assert error_code_for(name) == code

    @pytest.mark.parametrize('code, exit_code', [
        ('RUN_NOT_FOUND', EXIT_NOT_FOUND),
        ('ENVIRONMENT_DOES_NOT_EXIST_IN_DATABASE', EXIT_NOT_FOUND),
        ('ARGUMENTS', EXIT_USAGE),
        ('INVALID_PATH', EXIT_USAGE),
        ('VM_OPERATION_FAILED', EXIT_ERROR),
    ])
    def test_exit_code_for(self, code, exit_code):
        assert exit_code_for(code) == exit_code

    def _exit_code(self, exc_factory):
        from adare.run import exec_with_error_printing

        def boom(_args):
            raise exc_factory()

        with pytest.raises(SystemExit) as excinfo:
            exec_with_error_printing(boom, SimpleNamespace())
        return excinfo.value.code

    def test_not_found_exits_3(self):
        from adare.exceptions import RunNotFoundError
        assert self._exit_code(lambda: RunNotFoundError(log, 'NOSUCH')) == EXIT_NOT_FOUND

    def test_generic_error_exits_1_not_255(self):
        from adare.exceptions import LoggedErrorException
        assert self._exit_code(lambda: LoggedErrorException(log, 'boom')) == EXIT_ERROR

    def test_plain_logged_exception_is_a_failure(self):
        from adare.exceptions import LoggedException
        assert self._exit_code(lambda: LoggedException(log, 'boom')) == EXIT_ERROR

    def test_arguments_error_exits_2(self):
        from adare.exceptions import ArgumentsError
        assert self._exit_code(lambda: ArgumentsError(log, 'bad')) == EXIT_USAGE

    def test_informational_message_exits_0(self):
        from adare.backend.project.exceptions import NoProjectsFoundMessage
        assert self._exit_code(lambda: NoProjectsFoundMessage(log, 'no projects found')) == EXIT_OK

    def test_handle_api_error_maps_not_found(self):
        from adare.cli.utils import handle_api_error
        from adare.core.result import Result
        with pytest.raises(SystemExit) as excinfo:
            handle_api_error(Result.fail('SESSION_NOT_FOUND', 'no such session'))
        assert excinfo.value.code == EXIT_NOT_FOUND


def _error_cli():
    from adare.exceptions import TestFunctionNotFoundError
    from adare.run import exec_with_error_printing

    @click.group()
    @click.pass_context
    def root(ctx):
        ctx.ensure_object(SimpleNamespace)
        ctx.obj.output_format = None
        ctx.obj.output_file = None
        ctx.obj.very_verbose = False

    @root.command(name='fail')
    @output_options
    def fail_cmd():
        def run(_args):
            raise TestFunctionNotFoundError(log, 'testfunction "x.y" not found',
                                            possible_solutions=['Run `adare test list`', 'Check spelling'])
        exec_with_error_printing(run, SimpleNamespace())

    return root


class TestErrorOutput:
    def test_json_mode_prints_error_document_on_stderr(self, monkeypatch):
        monkeypatch.delenv('ADARE_FORMAT', raising=False)
        result = CliRunner().invoke(_error_cli(), ['fail', '--json'])
        assert result.exit_code == EXIT_NOT_FOUND
        assert result.stdout == ''
        payload = json.loads(result.stderr.strip().splitlines()[-1])
        assert payload == {'error': {
            'code': 'TESTFUNCTION_NOT_FOUND',
            'message': 'testfunction "x.y" not found',
            'hint': 'Run `adare test list`',
            'solutions': ['Run `adare test list`', 'Check spelling'],
        }}

    def test_text_mode_prints_one_concise_message_on_stderr(self, monkeypatch):
        monkeypatch.delenv('ADARE_FORMAT', raising=False)
        monkeypatch.setenv('NO_COLOR', '1')
        result = CliRunner().invoke(_error_cli(), ['fail'])
        assert result.exit_code == EXIT_NOT_FOUND
        assert result.stdout == ''
        assert result.stderr.count('testfunction "x.y" not found') == 1
        assert 'Error: testfunction "x.y" not found' in result.stderr
        assert 'Run `adare test list`' in result.stderr
        assert 'Traceback' not in result.stderr

    def test_hint_is_null_without_solutions(self):
        from adare.cli.errors import report_error
        from adare.run import cli  # noqa: F401  (ensures CLI modules import cleanly)

        @click.command()
        @click.argument('code')
        @output_options
        def cmd(code):
            raise SystemExit(report_error(code, 'gone'))

        result = CliRunner().invoke(cmd, ['SnapshotNotFoundException', '--json'])
        assert result.exit_code == EXIT_NOT_FOUND
        assert json.loads(result.stderr) == {
            'error': {'code': 'SNAPSHOT_NOT_FOUND', 'message': 'gone', 'hint': None, 'solutions': []}}

        # Common resources get a default "list them" hint when the error has none.
        result = CliRunner().invoke(cmd, ['VMNotFoundError', '--json'])
        assert json.loads(result.stderr)['error']['hint'].startswith('Run `adare vm list`')


# ---------------------------------------------------------------------------
# `adare status`
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, data=None, success=True, message=''):
        self.success = success
        self.data = data
        self.error = SimpleNamespace(message=message)


def _fake_api(sessions=None, instances=None, db_ok=True):
    from pathlib import Path

    db_status = SimpleNamespace(global_db_exists=True, global_db_accessible=db_ok,
                                global_db_location=Path('/tmp/global.db'), valid=db_ok,
                                pending_migrations=[], errors=[] if db_ok else ['broken'])
    return SimpleNamespace(
        devmode=SimpleNamespace(list_sessions=lambda request: _FakeResult(sessions or [])),
        vm=SimpleNamespace(list_instances=lambda: _FakeResult(instances or [])),
        manage=SimpleNamespace(get_db_status=lambda: _FakeResult(db_status)),
    )


class TestStatus:
    def test_collect_status_counts_sessions_and_vms(self, monkeypatch, tmp_path):
        from adare.cli import status
        monkeypatch.setattr('adare.backend.basics.determine_projectdirectory',
                            lambda project, silent=False: tmp_path)
        api = _fake_api(sessions=[SimpleNamespace(status='running'), SimpleNamespace(status='stopped'),
                                  SimpleNamespace(status='stopped')],
                        instances=[object(), object()])
        data = status.collect_status(api)
        assert data['project'] == {'available': True, 'name': tmp_path.name, 'path': str(tmp_path),
                                   'error': None}
        assert data['sessions'] == {'available': True, 'total': 3, 'running': 1, 'stopped': 2,
                                    'other': 0, 'error': None}
        assert data['vms'] == {'available': True, 'instances': 2, 'error': None}
        assert data['database']['available'] is True
        assert data['database']['pending_migrations'] == []

    def test_a_failing_section_does_not_blank_the_others(self, monkeypatch):
        from sqlalchemy.exc import OperationalError

        from adare.cli import status

        def broken(project, silent=False):
            raise OperationalError('select', {}, Exception('db locked'))

        monkeypatch.setattr('adare.backend.basics.determine_projectdirectory', broken)
        data = status.collect_status(_fake_api(instances=[object()]))
        assert data['project']['available'] is False
        assert 'db locked' in data['project']['error']
        assert data['vms']['instances'] == 1

    def test_status_json_is_parseable(self, monkeypatch):
        from adare.run import cli
        monkeypatch.delenv('ADARE_FORMAT', raising=False)
        fake = {'project': {'available': True, 'name': 'P', 'path': '/p', 'error': None},
                'sessions': {'available': True, 'total': 0, 'running': 0, 'stopped': 0, 'other': 0,
                             'error': None},
                'vms': {'available': True, 'instances': 0, 'error': None},
                'database': {'available': True, 'initialized': True, 'valid': True, 'location': None,
                             'pending_migrations': [], 'errors': []}}
        monkeypatch.setattr('adare.cli.status.collect_status', lambda api=None: fake)
        result = CliRunner().invoke(cli, ['status', '--json'])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == fake

    def test_status_plain_when_piped(self, monkeypatch):
        from adare.run import cli
        monkeypatch.delenv('ADARE_FORMAT', raising=False)
        fake = {'project': {'available': True, 'name': 'P', 'path': '/p', 'error': None}}
        monkeypatch.setattr('adare.cli.status.collect_status', lambda api=None: fake)
        result = CliRunner().invoke(cli, ['status'])
        assert result.exit_code == 0, result.output
        assert result.stdout.splitlines()[:2] == ['project.available\ttrue', 'project.name\tP']


# ---------------------------------------------------------------------------
# Regressions fixed alongside the foundation
# ---------------------------------------------------------------------------

def test_raw_text_is_emitted_verbatim():
    from adare.helperfunctions.output_formatter import RawText
    doc = 'tests:\n  - content: |\n      [b]keep[/b]\n'
    assert json.loads(get_formatter('json').format({'yaml': RawText(doc)})) == {'yaml': doc}


def test_abstract_tests_render_a_missing_testfunction_instead_of_crashing():
    """`experiment info` crashed with 'NoneType' has no attribute 'dotnotation'."""
    from unittest.mock import MagicMock

    from adare.database.api.frontend.test_queries import TestQueryMixin

    parameter = SimpleNamespace(parameter=SimpleNamespace(name='dst', dtype='str'), parameter_id='p',
                                value='/tmp/x')
    test = SimpleNamespace(name='t1', description=None, testfunction=None, testfunction_id='01TF',
                           testfunction_file_name=None, parameters=[parameter])
    api = TestQueryMixin()
    api._project_api = MagicMock()
    api._project_api._session.query.return_value.filter_by.return_value.one.return_value = (
        SimpleNamespace(abstract_tests=[test]))
    data = api.get_abstract_tests('01EXP')
    assert data['t1']['testfunction_missing'] is True
    assert data['t1']['testfunction_name'] == '01TF (missing)'
    assert data['t1']['parameters'] == [{'name': 'dst', 'dtype': 'str', 'value': '/tmp/x'}]
