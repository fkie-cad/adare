"""The rename table (adarelib.testset.renames) matches the collections' real signatures."""

from pathlib import Path

import attrs
import pytest

from adarelib.helper.module import import_module_from_pyfile
from adarelib.testset.renames import RENAMED_FUNCTIONS, RENAMED_PARAMETERS, rename_problems

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'


def _parameter_names(dotted: str) -> set[str] | None:
    collection, name = dotted.split('.')
    module = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
    function = getattr(module, name, None)
    if function is None or not hasattr(function, '_parameter_class'):
        return None
    return {f.name for f in attrs.fields(function._parameter_class)}


@pytest.mark.parametrize('old, new', sorted(RENAMED_FUNCTIONS.items()))
def test_renamed_function_is_gone_and_its_new_name_exists(old, new):
    assert _parameter_names(old) is None
    assert _parameter_names(new) is not None


@pytest.mark.parametrize('function, renames', sorted(RENAMED_PARAMETERS.items()))
def test_renamed_parameters_match_the_signature(function, renames):
    names = _parameter_names(function)
    assert names is not None, f'{function} does not exist'
    for old, new in renames.items():
        assert old not in names, f'{function} still has {old}'
        assert new in names, f'{function} has no {new}'


def test_rename_problems():
    assert rename_problems('csv.line_count', {}) == ['testfunction csv.line_count was renamed to csv.row_count']
    assert rename_problems('sqlite.query_result', {'query': 'q', 'expected_rows': 0}) == [
        'sqlite.query_result: parameter "expected_rows" was renamed to "expected_count"'
    ]
    assert rename_problems('sqlite.query_result', {'query': 'q', 'expected_count': 0}) == []
    assert rename_problems('file_exists', {'dst': '/x'}) == []  # bare name = standard.<name>
    assert rename_problems(None, None) == []
