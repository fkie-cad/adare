"""json.value_decode and json.values_compare against another file (test_json.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import json
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
json_tf_module = import_module_from_pyfile(COLLECTIONS / 'json' / 'json.py')


def _r2_write(path, data):
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


def _r2_run(function, **params):
    testfunction = getattr(json_tf_module, function)
    return testfunction._test_class(name='t', parameter=testfunction._parameter_class(**params)).test()


@pytest.fixture
def r2_files(tmp_path):
    before = _r2_write(tmp_path / 'before.json', {'count': 3, 'saved': '2026-03-01T10:00:00Z', 'blob': 'eyJpZCI6IDd9'})
    after = _r2_write(tmp_path / 'after.json', {'count': 5, 'saved': '2026-03-01T10:05:00Z', 'blob': 'eyJpZCI6IDl9'})
    return before, after


def test_values_compare_other_dst(r2_files, tmp_path):
    before, after = r2_files
    run = _r2_run
    assert (
        run(
            'values_compare',
            dst=after,
            key_path='count',
            other_key_path='count',
            other_dst=before,
            comparison_type='greater',
        ).status
        == StatusEnum.SUCCESS
    )
    assert (
        run(
            'values_compare',
            dst=after,
            key_path='saved',
            other_key_path='saved',
            other_dst=before,
            comparison_type='less',
        ).status
        == StatusEnum.FAILED
    )
    assert (
        run('values_compare', dst=after, key_path='count', other_key_path='count', other_dst=before, offset=2).status
        == StatusEnum.SUCCESS
    )
    missing = run(
        'values_compare', dst=after, key_path='count', other_key_path='count', other_dst=str(tmp_path / 'gone.json')
    )
    assert missing.status == StatusEnum.ERROR and 'does not exist' in missing.details[0]


def test_values_compare_other_dst_archive_member(r2_files, tmp_path):
    import zipfile as _zipfile

    before, after = r2_files
    archive = tmp_path / 'backup.zip'
    with _zipfile.ZipFile(archive, 'w') as zf:
        zf.write(before, 'state/before.json')
    result = _r2_run(
        'values_compare',
        dst=after,
        key_path='count',
        other_key_path='count',
        other_dst=f'{archive}!/state/before.json',
        comparison_type='greater',
    )
    assert result.status == StatusEnum.SUCCESS, result.details


def test_value_decode(r2_files):
    _, after = r2_files
    ok = _r2_run(
        'value_matches',
        dst=after,
        key_path='blob',
        expected_value=9,
        value_decode=['base64', 'json'],
        decoded_key_path='id',
    )
    assert ok.status == StatusEnum.SUCCESS, ok.details
    ordered = _r2_run(
        'values_compare',
        dst=after,
        key_path='blob',
        other_key_path='count',
        value_decode=['base64', 'json'],
        decoded_key_path='id',
    )
    assert ordered.status == StatusEnum.ERROR  # the count is no base64: decoding both sides fails
    bad = _r2_run('value_matches', dst=after, key_path='count', expected_value=5, value_decode='base64')
    assert bad.status == StatusEnum.ERROR and "'base64'" in bad.details[0]
    unknown = _r2_run('value_matches', dst=after, key_path='count', expected_value=5, value_decode='rot13')
    assert unknown.status == StatusEnum.ERROR
    no_path = _r2_run('value_matches', dst=after, key_path='blob', expected_value=9, value_decode='json')
    assert no_path.status == StatusEnum.ERROR
    plain = _r2_run('value_matches', dst=after, key_path='count', expected_value=5)
    assert plain.status == StatusEnum.SUCCESS
