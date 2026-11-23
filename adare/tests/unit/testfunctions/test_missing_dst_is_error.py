"""A content testfunction that cannot find its file reports ERROR, never FAILED.

FAILED means the test read the evidence and the condition does not hold. A missing
``dst`` or a glob that matches no file or several means the test never read anything.
``expect_to_fail`` inverts only SUCCESS/FAILED, so reporting such a case as FAILED would
let a wrong path or a failed host-mode pull pass a negative test.

Existence tests (``standard.file_exists``, ``standard.file_count`` and friends) are exempt: for them a missing
path is the finding.
"""

from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'

# Parameters that get each function past its own argument checks to the file read.
CASES = {
    'csv.contains_line': {'entry': ['a']},
    'csv.compare_rows': {'reference_rows': [['a']]},
    'csv.compare_files': {},
    'excel.sheet_exists': {'sheet': 'S'},
    'excel.cell_value_matches': {'row': 1, 'column': 1, 'expected_value': 'x'},
    'excel.contains_row': {'entry': ['a']},
    'excel.validate_columns': {'expected_columns': ['a']},
    'excel.compare_rows': {'reference_rows': [['a']]},
    'excel.compare_sheets': {},
    'excel.compare_files': {},
    'json.contains_key': {'key_path': 'a'},
    'json.value_matches': {'key_path': 'a', 'expected_value': 1},
    'json.array_contains': {'array_path': 'a', 'expected_value': 1},
    'jsonl.line_matches': {'conditions': {'a': 1}},
    'jsonl.line_count': {'expected_count': 1},
    'jsonl.value_in_any_line': {'key_path': 'a', 'expected_value': 1},
    'xml.element_exists': {'xpath': './/a'},
    'xml.element_text_matches': {'xpath': './/a', 'expected_value': 'x'},
    'xml.attribute_matches': {'xpath': './/a', 'attribute': 'b', 'expected_value': 'c'},
    'xml.element_count': {'xpath': './/a', 'expected_count': 1},
    'xml.xpath_result_matches': {'xpath': './/a', 'expected_value': 'x'},
    'xml.namespace_matches': {'expected_namespaces': {'a': 'urn:a'}},
    'standard.file_content_contains': {'content': 'a'},
    'standard.file_content_equals': {'content': 'a'},
    'standard.file_content_matches_regex': {'regex': 'a'},
    'standard.file_hash_matches': {'expected_hash': '0' * 64},
    'standard.file_timestamps': {'comparison_type': 'within_last', 'within_duration': '1h'},
    'standard.file_permissions': {'expected_permissions': '644'},
    'plist.contains_key': {'key_path': 'a'},
    'plist.value_matches': {'key_path': 'a', 'expected_value': 1},
    'plist.value_count': {'key_path': 'a', 'expected_count': 0},
    'yaml.contains_key': {'key_path': 'a'},
    'yaml.value_matches': {'key_path': 'a', 'expected_value': 1},
    'yaml.value_count': {'key_path': 'a', 'expected_count': 0},
    'toml.contains_key': {'key_path': 'a'},
    'toml.value_matches': {'key_path': 'a', 'expected_value': 1},
    'toml.value_count': {'key_path': 'a', 'expected_count': 0},
    'ini.section_exists': {'section': 'a'},
    'ini.contains_key': {'section': 'a', 'key': 'b'},
    'ini.value_matches': {'section': 'a', 'key': 'b', 'expected_value': 'c'},
    'ini.value_count': {'section': 'a', 'key': 'b', 'expected_count': 1},
    'image.png_text_matches': {'keyword': 'k'},
    'image.png_text_count': {'keyword': 'k', 'expected_count': 1},
    'image.exif_value_matches': {'tag': 'Make', 'expected_value': 'x'},
    'image.exif_value_count': {'tag': 'Make', 'expected_count': 1},
    'image.dimensions_match': {'width': 1},
    'csv.row_count': {'entry': ['a'], 'expected_count': 1},
    'json.value_count': {'key_path': 'a', 'expected_count': 1},
    'standard.file_size': {'expected_size': 1},
    'text.occurrence_count': {'content': 'a', 'expected_count': 1},
    'text.line_count': {'content': 'a', 'expected_count': 1},
    'sqlite.query_result': {'query': 'SELECT 1'},
    'sqlite.row_count': {'query': 'SELECT 1', 'expected_count': 1},
    'excel.row_count': {'entry': ['a'], 'expected_count': 1},
    'binary.struct_value_matches': {'offset': 0, 'value_format': 'u8', 'expected_value': 0},
    'binary.pattern_count': {'pattern': 'a', 'expected_count': 0},
    'binary.pair_value_matches': {'key': 'a', 'expected_value': 'b'},
    'binary.pair_count': {'key': 'a', 'expected_count': 0},
    # round 2: sqlite
    'sqlite.values_compare': {'query': 'SELECT 1'},
    'sqlite.free_space_pattern_count': {'pattern': 'a', 'expected_count': 0},
}
TWO_PATHS = {'csv.compare_files', 'excel.compare_sheets', 'excel.compare_files'}

_modules = {}


def _testfunction(dotted):
    collection, name = dotted.split('.')
    if collection not in _modules:
        _modules[collection] = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
    return getattr(_modules[collection], name)


def _run(dotted, path):
    testfunction = _testfunction(dotted)
    params = dict(CASES[dotted])
    if dotted in TWO_PATHS:
        params.update(actual=path, reference=path)
    else:
        params['dst'] = path
    test = testfunction._test_class(name='t', parameter=testfunction._parameter_class(**params))
    return test.test()


@pytest.mark.parametrize('dotted', sorted(CASES))
def test_missing_file_is_an_error(dotted, tmp_path):
    result = _run(dotted, str(tmp_path / 'missing.dat'))

    assert result.status == StatusEnum.ERROR, f'{result.status}: {result.details}'
    assert 'does not exist' in result.details[0]


@pytest.mark.parametrize('dotted', sorted(CASES))
def test_glob_without_match_is_an_error(dotted, tmp_path):
    result = _run(dotted, str(tmp_path / 'nothing*.dat'))

    assert result.status == StatusEnum.ERROR, f'{result.status}: {result.details}'


@pytest.mark.parametrize('dotted', sorted(CASES))
def test_ambiguous_glob_is_an_error(dotted, tmp_path):
    (tmp_path / 'a1.dat').write_text('a')
    (tmp_path / 'a2.dat').write_text('a')

    result = _run(dotted, str(tmp_path / 'a*.dat'))

    assert result.status == StatusEnum.ERROR, f'{result.status}: {result.details}'


@pytest.mark.parametrize('dotted', ['standard.file_exists', 'standard.dir_exists'])
def test_existence_tests_still_fail_on_a_missing_path(dotted, tmp_path):
    testfunction = _testfunction(dotted)
    param = testfunction._parameter_class(dst=str(tmp_path / 'missing'))

    result = testfunction._test_class(name='t', parameter=param).test()

    assert result.status == StatusEnum.FAILED, f'{result.status}: {result.details}'
