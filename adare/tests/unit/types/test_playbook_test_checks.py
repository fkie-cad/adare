"""Static checks of a playbook's tests: block (``adare exp playbook validate``)."""

import pytest

from adare.backend.testfunction.catalog import CatalogEntry, ParamSpec
from adare.types.playbook_test_checks import check_playbook_tests

pytestmark = pytest.mark.unit

CATALOG = [
    CatalogEntry(
        dotnotation='standard.file_exists',
        collection='standard',
        name='file_exists',
        summary='',
        category='',
        os='any',
        installed=True,
        path='',
        params=(ParamSpec('dst', 'str', True), ParamSpec('match_mode', 'str', False, 'any')),
    )
]


def _check(yaml_text):
    return check_playbook_tests(yaml_text, CATALOG)


def test_clean_playbook_has_no_findings():
    errors, warnings = _check('''
tests:
  - {name: a, function: standard.file_exists, parameter: {dst: /x}}
  - {name: b, function: file_exists, parameter: {dst: /y, match_mode: all}}   # bare = standard.<name>
actions:
  - test: a
  - block:
      actions:
        - test: {name: b, timeout: 5}
''')
    assert (errors, warnings) == ([], [])


def test_undefined_and_duplicate_tests_are_errors():
    errors, _ = _check('''
tests:
  - {name: a, function: standard.file_exists, parameter: {dst: /x}}
  - {name: a, function: standard.file_exists, parameter: {dst: /x}}
actions:
  - test: b
''')
    assert errors == ['duplicate test name "a" in `tests:`', '`- test: b` refers to no entry in `tests:`']


def test_catalog_findings_are_warnings_with_suggestions():
    errors, warnings = _check('''
tests:
  - {name: a, function: standard.file_exsts, parameter: {dst: /x}}
  - {name: b, function: standard.file_exists, parameter: {dsst: /x}}
actions: [{test: a}, {test: b}]
''')
    assert errors == []
    assert 'unknown testfunction "standard.file_exsts" (did you mean: standard.file_exists?)' in warnings[0]
    assert 'has no parameter "dsst" (did you mean: dst?)' in warnings[1]
    assert warnings[2] == 'test "b": missing required parameter "dst" for standard.file_exists'


def test_unparsable_or_empty_yaml_yields_nothing():
    assert _check('tests: [unclosed') == ([], [])
    assert _check('actions: []') == ([], [])


# ----------------------------------------------------------------------------- controls:


def _controls(tests_yaml, actions_yaml):
    return _check(f'tests:\n{tests_yaml}\nactions:\n{actions_yaml}')[0]


def test_valid_controls_have_no_errors():
    errors = _controls(
        '  - {name: before, function: standard.file_exists, parameter: {dst: /x}}\n'
        '  - {name: gone, function: standard.file_exists, parameter: {dst: /x}, controls: [before]}',
        '  - test: before\n  - test: gone',
    )
    assert errors == []


def test_unknown_control_is_an_error():
    errors = _controls(
        '  - {name: before, function: standard.file_exists, parameter: {dst: /x}}\n'
        '  - {name: gone, function: standard.file_exists, parameter: {dst: /x}, controls: [befor]}',
        '  - test: before\n  - test: gone',
    )
    assert any('control "befor" is not in `tests:`' in e and 'did you mean: before' in e for e in errors)


def test_control_running_after_its_test_is_an_error():
    errors = _controls(
        '  - {name: before, function: standard.file_exists, parameter: {dst: /x}}\n'
        '  - {name: gone, function: standard.file_exists, parameter: {dst: /x}, controls: [before]}',
        '  - test: gone\n  - test: before',
    )
    assert any('runs after the test it controls' in e for e in errors)


def test_control_that_never_runs_is_an_error():
    errors = _controls(
        '  - {name: before, function: standard.file_exists, parameter: {dst: /x}}\n'
        '  - {name: gone, function: standard.file_exists, parameter: {dst: /x}, controls: [before]}',
        '  - test: gone',
    )
    assert any('never runs' in e for e in errors)


def test_cyclic_controls_are_an_error():
    errors = _controls(
        '  - {name: a, function: standard.file_exists, parameter: {dst: /x}, controls: [b]}\n'
        '  - {name: b, function: standard.file_exists, parameter: {dst: /x}, controls: [a]}',
        '  - test: a\n  - test: b',
    )
    assert any('cycle' in e for e in errors)


def test_self_control_is_an_error():
    errors = _controls(
        '  - {name: a, function: standard.file_exists, parameter: {dst: /x}, controls: [a]}', '  - test: a'
    )
    assert any('its own control' in e for e in errors)


# ----------------------------------------------------------------------------- shipped idioms


@pytest.mark.parametrize('name', ['delete_file_and_verify', 'open_app_and_verify'])
def test_idiom_templates_parse_and_validate(name):
    from pathlib import Path

    from adare.backend.testfunction.catalog import load_catalog
    from adare.types.playbook import parse_playbook

    path = Path(__file__).resolve().parents[4] / 'templates' / 'idioms' / f'{name}.play.yaml'
    playbook = parse_playbook(path)
    assert any(type(a).__name__ == 'ActionTestAction' for a in playbook.actions)
    errors, warnings = check_playbook_tests(path.read_text(), load_catalog())
    assert errors == [] and warnings == []
