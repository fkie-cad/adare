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
