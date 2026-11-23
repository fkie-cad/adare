"""A test whose templates cannot be resolved is ERROR for that test, never run on the raw text.

Public path: ``TestActionsExecutor.execute_test`` (what the runner calls) -> ``TestLoader`` ->
``VariableResolver``. The first tests inject a resolution failure into ``process_data`` (a literal bad
zone is already rejected when the playbook is parsed), to test how the loader and the executor turn
it into a result; the ``real_run_test`` ones below use the real resolver and real failures.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from adare.backend.experiment import test_loader
from adare.backend.experiment.execution import test_actions
from adare.backend.experiment.variable_resolver import VariableResolver, create_jinja_environment
from adare.exceptions import TemplateResolutionError
from adare.types.playbook import ActionTestAction, parse_playbook
from adarelib.common.automatic_variables import AutomaticVariables
from adarelib.common.timezones import ValidationError

pytestmark = pytest.mark.unit

PLAYBOOK = """
variables:
  started: !timestamp {timestamp: '2024-01-02T03:04:05Z'}
actions: []
tests:
  - name: first_ok
    function: standard.file_exists
    parameter:
      dst: /tmp/first
  - name: broken
    function: standard.file_exists
    parameter:
      dst: /tmp/broken
  - name: last_ok
    function: standard.file_exists
    parameter:
      dst: /tmp/last
"""


class _FailingResolver(VariableResolver):
    """Resolves like the real one, but ``process_data`` fails for the test named in ``fail_for``."""

    fail_for = 'broken'

    def process_data(self, data, template_context=None):
        if data.get('name') == self.fail_for:
            raise ValidationError("Unknown timezone 'Mars/Olympus'")
        return super().process_data(data, template_context)


REAL_FAILURES_PLAYBOOK = """
variables:
  started: !timestamp {timestamp: '2024-01-02T03:04:05Z'}
actions: []
tests:
  - {name: good, function: standard.file_exists, parameter: {dst: '/tmp/{{ 1 + 1 }}'}}
  - {name: good_format, function: standard.file_exists, parameter: {dst: "/tmp/{{ started | format('%Y') }}"}}
  - {name: unknown_filter, function: standard.file_exists, parameter: {dst: '/tmp/{{ started | nosuchfilter }}'}}
  - {name: undefined_variable, function: standard.file_exists, parameter: {dst: '/tmp/{{ nope }}/x'}}
  - {name: runtime_variable, function: standard.file_exists, parameter: {dst: '/tmp/{{ saved_later }}/x'}}
  - {name: format_time, function: standard.file_exists, parameter: {dst: "/tmp/{{ started | format('%H:%M') }}"}}
  - {name: syntax_error, function: standard.file_exists, parameter: {dst: '/tmp/x-{{ started | }}-y'}}
  - {name: format_missing_variable, function: standard.file_exists, parameter: {dst: "{{ never_set | format('%Y') }}"}}
"""


@pytest.fixture
def parts(tmp_path):
    (tmp_path / 'playbook.yml').write_text(PLAYBOOK)
    playbook = parse_playbook(tmp_path / 'playbook.yml')
    automatic = AutomaticVariables.get_automatic_variables('linux', 'user')
    playbook.variables = AutomaticVariables.merge_with_user_variables(automatic, playbook.variables)
    jinja_env = create_jinja_environment(playbook.variables)
    return tmp_path, playbook, jinja_env


@pytest.fixture
def run_test(parts):
    """Run one playbook test by name through the executor; ``run_test.guest`` is the fake guest."""
    tmp_path, playbook, jinja_env = parts
    resolver = _FailingResolver(variable_registry=playbook.variables, jinja_env=jinja_env)
    loader = test_loader.TestLoader(tmp_path, tmp_path, playbook=playbook, variable_resolver=resolver)
    loader.get_test_class = lambda name: None  # no testfunction collection: the guest is a stub
    executor = test_actions.TestActionsExecutor(experiment_run_directory=tmp_path, playbook=playbook)
    executor.set_test_loader(loader)
    guest = AsyncMock()
    guest.run_test = AsyncMock(return_value={'status': 'success', 'result': {'status': 'SUCCESS', 'details': []}})

    def run(name):
        return asyncio.run(executor.execute_test(ActionTestAction(name=name), guest, None))

    run.guest = guest
    return run


def test_resolution_failure_is_error_naming_the_test_and_the_cause(run_test):
    result = run_test('broken')

    assert result.success is False
    assert result.data['test_status'] == 'ERROR'  # stored as ERROR, not FAILED
    assert result.data['result_category'] == 'execution_error'
    (detail,) = result.data['result']['details']
    assert "'broken'" in detail
    assert "Unknown timezone 'Mars/Olympus'" in detail
    assert "'broken'" in result.message
    assert not any(call.args[0] == 'broken' for call in run_test.guest.run_test.call_args_list)


def test_other_tests_still_run_before_and_after_the_failing_one(run_test):
    assert run_test('first_ok').success is True
    assert run_test('broken').data['test_status'] == 'ERROR'
    assert run_test('last_ok').success is True

    assert [call.args[0] for call in run_test.guest.run_test.call_args_list] == ['first_ok', 'last_ok']


def test_good_templates_still_resolve(run_test):
    result = run_test('first_ok')

    assert result.success is True
    sent = run_test.guest.run_test.call_args.args[1]
    assert sent['parameter']['dst'] == '/tmp/first'


@pytest.fixture
def real_run_test(tmp_path):
    """Like ``run_test``, but with the real resolver (no injected failure) and ``REAL_FAILURES_PLAYBOOK``."""
    (tmp_path / 'playbook.yml').write_text(REAL_FAILURES_PLAYBOOK)
    playbook = parse_playbook(tmp_path / 'playbook.yml')
    automatic = AutomaticVariables.get_automatic_variables('linux', 'user')
    playbook.variables = AutomaticVariables.merge_with_user_variables(automatic, playbook.variables)
    jinja_env = create_jinja_environment(playbook.variables)
    resolver = VariableResolver(variable_registry=playbook.variables, jinja_env=jinja_env)
    loader = test_loader.TestLoader(tmp_path, tmp_path, playbook=playbook, variable_resolver=resolver)
    loader.get_test_class = lambda name: None
    executor = test_actions.TestActionsExecutor(experiment_run_directory=tmp_path, playbook=playbook)
    executor.set_test_loader(loader)
    guest = AsyncMock()
    guest.run_test = AsyncMock(return_value={'status': 'success', 'result': {'status': 'SUCCESS', 'details': []}})

    def run(name, context=None):
        return asyncio.run(executor.execute_test(ActionTestAction(name=name), guest, None, execution_context=context))

    run.guest = guest
    run.loader = loader
    run.registry = playbook.variables
    return run


@pytest.mark.parametrize(
    'name, template',
    [
        ('unknown_filter', '{{ started | nosuchfilter }}'),
        ('syntax_error', '{{ started | }}'),
        ('undefined_variable', '{{ nope }}'),
        ('format_missing_variable', "{{ never_set | format('%Y') }}"),
    ],
)
def test_unrenderable_template_is_error_naming_the_template(real_run_test, name, template):
    result = real_run_test(name)

    assert result.success is False
    assert result.data['test_status'] == 'ERROR'
    (detail,) = result.data['result']['details']
    assert template in detail  # names the template, not just the test
    assert not any(call.args[0] == name for call in real_run_test.guest.run_test.call_args_list)


def test_resolver_raises_instead_of_returning_the_raw_text(real_run_test):
    for name in ('unknown_filter', 'syntax_error', 'format_missing_variable', 'undefined_variable'):
        with pytest.raises(TemplateResolutionError) as info:
            asyncio.run(real_run_test.loader.resolve_test_with_runtime_context(name, {}))
        assert info.value.message.startswith('Cannot render test template')


def test_format_filter_on_a_bad_value_raises(real_run_test):
    with pytest.raises(TemplateResolutionError) as info:
        asyncio.run(real_run_test.loader.resolve_test_with_runtime_context('good_format', {'started': 'not a date'}))

    assert "{{ started | format('%Y') }}" in info.value.message


def test_good_templates_resolve_as_before(real_run_test):
    assert real_run_test('good').success is True
    assert real_run_test('good_format').success is True

    sent = {call.args[0]: call.args[1] for call in real_run_test.guest.run_test.call_args_list}
    assert sent['good']['parameter']['dst'] == '/tmp/2'
    assert sent['good_format']['parameter']['dst'] == '/tmp/2024'


def test_format_filter_with_a_bad_stored_zone_raises_instead_of_ignoring_it(real_run_test):
    real_run_test.registry.get('started').structured_metadata.timezone = 'Mars/Olympus'  # past the parse-time check

    with pytest.raises(TemplateResolutionError) as info:
        asyncio.run(real_run_test.loader.resolve_test_with_runtime_context('good_format', {'started': 1704164645}))

    assert "{{ started | format('%Y') }}" in info.value.message
    assert "Unknown timezone 'Mars/Olympus'" in info.value.message


def test_undefined_variable_error_names_the_variable(real_run_test):
    (detail,) = real_run_test('undefined_variable').data['result']['details']

    assert "'nope' is undefined" in detail
    assert '/tmp/{{ nope }}/x' not in detail.replace("'{{ nope }}'", '')  # not run on the raw text either


def test_variable_saved_during_the_run_still_resolves(real_run_test):
    assert real_run_test('runtime_variable').data['test_status'] == 'ERROR'  # not saved (yet)

    result = real_run_test('runtime_variable', {'saved_later': 'abc'})

    assert result.success is True
    assert real_run_test.guest.run_test.call_args.args[1]['parameter']['dst'] == '/tmp/abc/x'


@pytest.mark.parametrize('zone, expected', [('+0200', '05:04'), ('+02', '05:04'), ('Europe/Berlin', '04:04')])
def test_format_filter_applies_a_good_stored_zone(real_run_test, zone, expected):
    real_run_test.registry.get('started').structured_metadata.timezone = zone
    test = asyncio.run(real_run_test.loader.resolve_test_with_runtime_context('format_time', {'started': 1704164645}))

    assert test['parameter']['dst'] == f'/tmp/{expected}'
