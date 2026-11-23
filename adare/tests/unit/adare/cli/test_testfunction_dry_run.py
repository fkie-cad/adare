"""`adare test dry-run` structures parameters like a real run and reads archive members."""

import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from adare.cli.testfunction import exec_dry_run_testfunction

pytestmark = pytest.mark.unit

JSON_COLLECTION = Path(__file__).resolve().parents[4] / 'appdata' / 'testfunctions' / 'json'


def _dry_run(capsys, dst, *params):
    args = SimpleNamespace(target='json.value_matches', path=str(JSON_COLLECTION), param=list(params), file=dst)
    exec_dry_run_testfunction(args)
    return capsys.readouterr().out


def test_union_typed_parameter(tmp_path, capsys):
    # expected_value is `str | int | float | bool | None`: cattrs needs the scalar-union hook
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'port': 8080}))
    assert 'SUCCESS' in _dry_run(capsys, str(path), 'key_path=port', 'expected_value=8080')


def test_archive_member(tmp_path, capsys):
    data = json.dumps({'port': 8080}).encode()
    archive = tmp_path / 'backup.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        info = tarfile.TarInfo('etc/app/config.json')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    out = _dry_run(capsys, f'{archive}!/etc/app/config.json', 'key_path=port', 'expected_value=8080')

    assert 'SUCCESS' in out
    assert 'archive member' in out


def test_values_compare_other_dst_archive_member(tmp_path, capsys):
    before = json.dumps({'count': 3}).encode()
    archive = tmp_path / 'backup.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        info = tarfile.TarInfo('state.json')
        info.size = len(before)
        tar.addfile(info, io.BytesIO(before))
    after = tmp_path / 'state.json'
    after.write_text(json.dumps({'count': 5}))
    args = SimpleNamespace(
        target='json.values_compare',
        path=str(JSON_COLLECTION),
        param=['key_path=count', 'other_key_path=count', 'comparison_type=greater', f'other_dst={archive}!/state.json'],
        file=str(after),
    )

    exec_dry_run_testfunction(args)
    out = capsys.readouterr().out

    assert 'SUCCESS' in out
    assert 'other_dst:' in out  # the console wraps the long temp path
    assert 'archive member' in out
