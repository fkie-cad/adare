"""Shared comparison helpers used by the csv/excel/json/jsonl/xml collections."""

import pytest

from adarelib.constants import StatusEnum
from adarelib.testset.compare import (
    compare_row_sequences,
    compare_row_sets,
    extract_columns,
    format_diff_report,
    get_nested_value,
)

pytestmark = pytest.mark.unit


class _PlainCtx:
    def has_placeholders(self, text):
        return False


def test_extract_columns_ignores_out_of_range_indices():
    assert extract_columns(['a', 'b'], [0, 5]) == ['a']
    assert extract_columns(['a', 'b'], None) == ['a', 'b']


def test_get_nested_value_walks_dicts_and_lists():
    data = {'user': {'tags': ['x', 'y']}}
    assert get_nested_value(data, 'user.tags') == (['x', 'y'], True)
    assert get_nested_value(data, 'user.missing')[1] is False


def test_diff_report_carries_the_collection_label():
    report = format_diff_report([(1, ['a'])], [], [], actual_count=0, reference_count=1, columns=None, label='Excel')
    assert report[0] == 'Excel comparison failed: 1 missing row'


@pytest.mark.parametrize('compare', [compare_row_sets, compare_row_sequences])
def test_row_comparisons(compare):
    ctx = _PlainCtx()
    same = compare(ctx, [['a', '1']], [['a', '1']], None, False, False)
    assert same.status == StatusEnum.SUCCESS

    differs = compare(ctx, [['a', '1']], [['a', '2']], None, False, False, label='Excel')
    assert differs.status == StatusEnum.FAILED
    assert differs.details[0].startswith('Excel comparison failed')
