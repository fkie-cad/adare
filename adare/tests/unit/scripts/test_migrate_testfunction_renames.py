"""scripts/migrate_testfunction_renames.py rewrites renamed names and nothing else."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[4] / 'scripts' / 'migrate_testfunction_renames.py'
_SPEC = importlib.util.spec_from_file_location('migrate_testfunction_renames', _SCRIPT)
migrate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(migrate)

PLAYBOOK = """\
tests:
  # comment kept
  - name: sheet
    function: excel.sheet_exists
    parameter:
      dst: /x.xlsx
      sheet_name: Data   # trailing comment kept
      regex_match: false
  - name: other_function_keeps_its_key
    function: excel.contains_row
    parameter:
      dst: /x.xlsx
      sheet_name: kept
  - name: parameter_before_function
    parameter:
      query: SELECT 1
      expected_rows: 0
    function: sqlite.query_result
  - function: csv.line_count
    name: renamed_function
    parameter:
      dst: /x.csv
      entry: [a, !re '.*']
      expected_count: 1
  - name: nested_value_not_a_key
    function: json.array_contains
    parameter:
      dst: /x.json
      array_path: a
      expected_element:
        expected_element: inner
"""


def test_migrate_text_renames_only_the_affected_keys():
    text, changes = migrate.migrate_text(PLAYBOOK)

    assert 'sheet: Data   # trailing comment kept' in text
    assert 'sheet_name: kept' in text  # excel.contains_row has no such rename
    assert 'expected_count: 0' in text and 'expected_rows' not in text
    assert 'function: csv.row_count' in text
    assert "entry: [a, !re '.*']" in text
    assert '      expected_value:\n        expected_element: inner' in text  # only the parameter key
    assert '# comment kept' in text
    assert len(changes) == 4


def test_migrate_text_is_idempotent():
    once, _ = migrate.migrate_text(PLAYBOOK)
    twice, changes = migrate.migrate_text(once)
    assert twice == once and changes == []
