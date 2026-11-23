"""A test whose templates cannot be resolved is ERROR for that test, never run on the raw text.

Public path: ``TestActionsExecutor.execute_test`` (what the runner calls) -> ``TestLoader`` ->
``VariableResolver``. The resolver is real; a resolution failure is injected into ``process_data``
(a literal bad zone is already rejected when the playbook is parsed, and the resolver's own
template handling is not this module's), so what is under test is how the loader and the executor
turn that failure into a result. ``_replace_variables_for_tests`` is also tested directly.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from adare.backend.experiment import test_loader
from adare.backend.experiment.execution import test_actions
from adare.backend.experiment.variable_resolver import VariableResolver
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


@pytest.fixture
def parts(tmp_path):
    (tmp_path / 'playbook.yml').write_text(PLAYBOOK)
    playbook = parse_playbook(tmp_path / 'playbook.yml')
    automatic = AutomaticVariables.get_automatic_variables('linux', 'user')
    playbook.variables = AutomaticVariables.merge_with_user_variables(automatic, playbook.variables)
    jinja_env = test_loader.TestLoader(tmp_path, tmp_path, playbook=playbook)._create_jinja_environment()
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
def renderer(parts):
    tmp_path, playbook, jinja_env = parts
    resolver = VariableResolver(variable_registry=playbook.variables, jinja_env=jinja_env)
    return test_loader.TestLoader(tmp_path, tmp_path, playbook=playbook, variable_resolver=resolver)


def test_template_with_a_defined_variable_renders(renderer):
    assert renderer._replace_variables_for_tests('sum {{ 1 + 1 }}') == 'sum 2'
    assert renderer._replace_variables_for_tests('{{ started | timezone("UTC") }}') != ''


def test_undefined_variable_raises_naming_the_template(renderer):
    with pytest.raises(TemplateResolutionError) as info:
        renderer._replace_variables_for_tests('/tmp/{{ no_such_variable }}/x')

    assert '/tmp/{{ no_such_variable }}/x' in info.value.message
    assert 'no_such_variable' in info.value.message


def test_bad_timezone_filter_raises_naming_the_template(renderer):
    with pytest.raises(TemplateResolutionError) as info:
        renderer._replace_variables_for_tests("{{ started | timezone('Mars/Olympus') }}")

    assert "{{ started | timezone('Mars/Olympus') }}" in info.value.message
    assert "Unknown timezone 'Mars/Olympus'" in info.value.message


def test_template_syntax_error_raises(renderer):
    with pytest.raises(TemplateResolutionError):
        renderer._replace_variables_for_tests('{{ started | }}')
