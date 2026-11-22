"""Built-in testfunctions read files inside archives (``dst: backup.tar.gz!/etc/app.json``).

No testfunction knows about archives: ``ctx.resolve_globfilepath`` extracts the member.
Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import gzip
import io
import json
import os
import sqlite3
import tarfile
import tempfile
import zipfile
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile
from adarelib.testset.archive import MAX_BYTES_ENV

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
CONFIG = {'name': 'app', 'port': 8080}

_modules = {}


def _run(dotted, **params):
    collection, name = dotted.split('.')
    if collection not in _modules:
        _modules[collection] = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
    testfunction = getattr(_modules[collection], name)
    test = testfunction._test_class(name='t', parameter=testfunction._parameter_class(**params))
    return test.test()


@pytest.fixture(autouse=True)
def private_tempdir(tmp_path, monkeypatch):
    """Extraction temp dirs go here, so tests can check they are removed."""
    d = tmp_path / 'tmp'
    d.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(d))
    return d


@pytest.fixture
def backup(tmp_path):
    path = tmp_path / 'backup.tar.gz'
    data = json.dumps(CONFIG).encode()
    with tarfile.open(path, 'w:gz') as tar:
        info = tarfile.TarInfo('etc/app/config.json')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return str(path)


def _details(result):
    return '\n'.join(str(d) for d in result.details)


def test_json_value_matches_member(backup, private_tempdir):
    result = _run('json.value_matches', dst=f'{backup}!/etc/app/config.json', key_path='port', expected_value=8080)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert f'archive member: etc/app/config.json from {backup} sha256=' in _details(result)
    assert not os.listdir(private_tempdir)  # extracted files removed after the test


def test_failed_result_keeps_provenance(backup):
    result = _run('json.value_matches', dst=f'{backup}!/etc/app/config.json', key_path='port', expected_value=1)
    assert result.status == StatusEnum.FAILED
    assert 'archive member: etc/app/config.json' in _details(result)


def test_mapping_form_is_normalized_before_dispatch(backup):
    from adarelib.testset.archive import normalize_dst

    dst = normalize_dst({'archive': backup, 'member': 'etc/app/config.json'})
    assert _run('json.value_matches', dst=dst, key_path='name', expected_value='app').status == StatusEnum.SUCCESS


def test_content_contains_in_rotated_log(tmp_path):
    path = tmp_path / 'syslog.2.gz'
    with gzip.open(path, 'wt') as f:
        f.write('Nov 22 10:00:00 host sshd[1]: Accepted password for alice\n')

    result = _run('standard.file_content_contains', dst=f'{path}!', content='Accepted password for alice')

    assert result.status == StatusEnum.SUCCESS, result.details
    assert 'decompressed content' in _details(result)


def test_sqlite_query_in_zip(tmp_path):
    db = tmp_path / 'places.sqlite'
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE moz_places (url TEXT)')
    con.execute("INSERT INTO moz_places VALUES ('https://example.org')")
    con.commit()
    con.close()
    archive = tmp_path / 'profile.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.write(db, 'profile/places.sqlite')

    result = _run(
        'sqlite.query_result',
        dst=f'{archive}!/profile/places.sqlite',
        query="SELECT url FROM moz_places WHERE url LIKE '%example%'",
        expected_rows=1,
    )

    assert result.status == StatusEnum.SUCCESS, result.details


def test_file_exists_reports_the_archive_path(backup):
    result = _run('standard.file_exists', dst=f'{backup}!/etc/app/config.json')
    assert result.status == StatusEnum.SUCCESS
    assert f'{backup}!/etc/app/config.json' in result.details[0]  # not the temp copy


def test_absent_member(backup):
    dst = f'{backup}!/etc/app/missing.json'
    assert _run('standard.file_does_not_exist', dst=dst).status == StatusEnum.SUCCESS
    assert _run('standard.file_exists', dst=dst).status == StatusEnum.FAILED
    content = _run('json.value_matches', dst=dst, key_path='port', expected_value=8080)
    assert content.status == StatusEnum.ERROR
    assert 'not found in' in _details(content)


def test_absent_archive_is_error_even_for_absence_tests(tmp_path):
    dst = f'{tmp_path}/gone.tar.gz!/etc/app/config.json'
    for dotted in ('standard.file_does_not_exist', 'standard.file_exists'):
        result = _run(dotted, dst=dst)
        assert result.status == StatusEnum.ERROR, (dotted, result.details)
        assert 'does not exist' in _details(result)


def test_ambiguous_member_glob_is_error(tmp_path):
    archive = tmp_path / 'logs.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr('logs/a.log', 'x')
        zf.writestr('logs/b.log', 'x')
    result = _run('standard.file_content_contains', dst=f'{archive}!/logs/*.log', content='x')
    assert result.status == StatusEnum.ERROR
    # match_mode any (file_exists' default) accepts several
    assert _run('standard.file_exists', dst=f'{archive}!/logs/*.log').status == StatusEnum.SUCCESS


def test_archive_glob(backup, tmp_path):
    dst = f'{tmp_path}/backup*.tar.gz!/etc/app/config.json'
    assert _run('json.value_matches', dst=dst, key_path='port', expected_value=8080).status == StatusEnum.SUCCESS


def test_size_cap_is_error(backup, monkeypatch):
    monkeypatch.setenv(MAX_BYTES_ENV, '10')
    result = _run('json.value_matches', dst=f'{backup}!/etc/app/config.json', key_path='port', expected_value=8080)
    assert result.status == StatusEnum.ERROR
    assert 'size cap' in _details(result)


def test_unsafe_member_is_error(tmp_path):
    archive = tmp_path / 'evil.tar'
    with tarfile.open(archive, 'w') as tar:
        info = tarfile.TarInfo('link')
        info.type = tarfile.SYMTYPE
        info.linkname = '/etc/shadow'
        tar.addfile(info)
    assert _run('standard.file_does_not_exist', dst=f'{archive}!/link').status == StatusEnum.ERROR
