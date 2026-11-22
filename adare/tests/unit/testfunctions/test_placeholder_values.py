"""``!re`` / ``!timestamp`` placeholders in the value tests of the key/value collections.

A playbook's ``expected_value: !re 'entry-\\d+'`` reaches the testfunction as the string
``{{ name }}`` plus ``variable_metadata[name]``. For every value_matches / value_count of ini,
yaml, toml, plist, image (PNG text, EXIF) and json:

- a matching placeholder passes, a placeholder the value does not match FAILS (the file was read);
- an invalid regular expression and an unknown placeholder are an ERROR: the test definition
  is broken, nothing was learnt about the artifact (and an absence count must not pass on it).
"""

import json
import plistlib
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
VALUE = 'entry-42'  # the value every fixture file holds at the tested location

_modules = {}


def _module(collection):
    if collection not in _modules:
        _modules[collection] = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
    return _modules[collection]


def _run(dotted, variable_metadata, **params):
    collection, name = dotted.split('.')
    testfunction = getattr(_module(collection), name)
    test = testfunction._test_class(
        name='t', parameter=testfunction._parameter_class(**params), variable_metadata=variable_metadata
    )
    return test.test()


def _assert(result, status):
    assert result.status == status, f'expected {status.name}, got {result.status}: {result.details}'


# --- one file per format, all holding VALUE ------------------------------------------------


def _png_chunk(ctype: bytes, body: bytes) -> bytes:
    return struct.pack('>I', len(body)) + ctype + body + struct.pack('>I', zlib.crc32(ctype + body) & 0xFFFFFFFF)


def _png_with_text(keyword: str, text: str) -> bytes:
    ihdr = _png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0))
    idat = _png_chunk(b'IDAT', zlib.compress(b'\x00\x80'))
    text_chunk = _png_chunk(b'tEXt', keyword.encode('latin-1') + b'\x00' + text.encode('latin-1'))
    return b'\x89PNG\r\n\x1a\n' + ihdr + text_chunk + idat + _png_chunk(b'IEND', b'')


@pytest.fixture(scope='module')
def files(tmp_path_factory):
    root = tmp_path_factory.mktemp('placeholder_values')
    paths = {
        'json': root / 'a.json',
        'yaml': root / 'a.yaml',
        'toml': root / 'a.toml',
        'plist': root / 'a.plist',
        'ini': root / 'a.ini',
        'png': root / 'a.png',
        'jpeg': root / 'a.jpg',
    }
    paths['json'].write_text(json.dumps({'a': {'name': VALUE}}))
    paths['yaml'].write_text(f'a:\n  name: {VALUE}\n')
    paths['toml'].write_text(f'[a]\nname = "{VALUE}"\n')
    paths['plist'].write_bytes(plistlib.dumps({'a': {'name': VALUE}}))
    paths['ini'].write_text(f'[a]\nname = {VALUE}\n')
    paths['png'].write_bytes(_png_with_text('name', VALUE))
    exif = Image.Exif()
    exif[0x010F] = VALUE  # Make
    Image.new('RGB', (4, 4), 'red').save(paths['jpeg'], 'JPEG', exif=exif)
    return {kind: str(path) for kind, path in paths.items()}


# (testfunction, file kind, parameters without expected_value; a count expects 1 match)
VALUE_TESTS = [
    ('json.value_matches', 'json', {'key_path': 'a.name'}),
    ('json.value_count', 'json', {'key_path': 'a.name', 'expected_count': 1}),
    ('yaml.value_matches', 'yaml', {'key_path': 'a.name'}),
    ('yaml.value_count', 'yaml', {'key_path': 'a.name', 'expected_count': 1}),
    ('toml.value_matches', 'toml', {'key_path': 'a.name'}),
    ('toml.value_count', 'toml', {'key_path': 'a.name', 'expected_count': 1}),
    ('plist.value_matches', 'plist', {'key_path': 'a.name'}),
    ('plist.value_count', 'plist', {'key_path': 'a.name', 'expected_count': 1}),
    ('ini.value_matches', 'ini', {'section': 'a', 'key': 'name'}),
    ('ini.value_count', 'ini', {'section': 'a', 'key': 'name', 'expected_count': 1}),
    ('image.png_text_matches', 'png', {'keyword': 'name'}),
    ('image.png_text_count', 'png', {'keyword': 'name', 'expected_count': 1}),
    ('image.exif_value_matches', 'jpeg', {'tag': 'Make'}),
    ('image.exif_value_count', 'jpeg', {'tag': 'Make', 'expected_count': 1}),
]
IDS = [t[0] for t in VALUE_TESTS]


def _regex(pattern):
    return {'P': {'type': 'regex', 'raw_value': pattern, 'resolved_value': pattern}}


CASES = [
    pytest.param('{{ P }}', _regex(r'entry-\d+'), StatusEnum.SUCCESS, id='regex-match'),
    pytest.param('{{P}}', _regex(r'entry-\d+'), StatusEnum.SUCCESS, id='regex-match-no-spaces'),
    pytest.param('{{ P }}', {'P': {'type': 'string', 'resolved_value': VALUE}}, StatusEnum.SUCCESS, id='string'),
    pytest.param('{{ P }}', _regex(r'other-\d+'), StatusEnum.FAILED, id='regex-mismatch'),
    pytest.param('{{ P }}', _regex(r'\d+'), StatusEnum.FAILED, id='regex-anchored-at-start'),
    pytest.param('{{ P }}', {'P': {'type': 'string', 'resolved_value': 'entry'}}, StatusEnum.FAILED, id='string-diff'),
    pytest.param('{{ P }}', _regex('[unclosed'), StatusEnum.ERROR, id='invalid-regex'),
    pytest.param('{{ P }}', _regex('(?P<x>a)(?P<x>b)'), StatusEnum.ERROR, id='invalid-regex-group'),
    pytest.param('{{ NOPE }}', _regex(r'entry-\d+'), StatusEnum.ERROR, id='unknown-placeholder'),
    pytest.param('{{ P }}', None, StatusEnum.ERROR, id='no-metadata-at-all'),
    pytest.param('{{ P }}', {}, StatusEnum.ERROR, id='empty-metadata'),
    pytest.param('{{ P }}', {'P': {'type': 'regex'}}, StatusEnum.ERROR, id='regex-without-pattern'),
]


@pytest.mark.parametrize(('expected_value', 'metadata', 'status'), CASES)
@pytest.mark.parametrize(('dotted', 'kind', 'params'), VALUE_TESTS, ids=IDS)
def test_placeholder_value(files, dotted, kind, params, expected_value, metadata, status):
    result = _run(dotted, metadata, dst=files[kind], expected_value=expected_value, **params)

    _assert(result, status)


@pytest.mark.parametrize(('dotted', 'kind', 'params'), VALUE_TESTS, ids=IDS)
def test_error_names_the_problem(files, dotted, kind, params):
    invalid = _run(dotted, _regex('[unclosed'), dst=files[kind], expected_value='{{ P }}', **params)
    unknown = _run(dotted, _regex('x'), dst=files[kind], expected_value='{{ NOPE }}', **params)

    assert 'invalid regular expression' in ' '.join(map(str, invalid.details))
    assert 'NOPE' in ' '.join(map(str, unknown.details))


@pytest.mark.parametrize(('dotted', 'kind', 'params'), VALUE_TESTS, ids=IDS)
def test_two_placeholders_in_one_value_are_an_error(files, dotted, kind, params):
    metadata = {**_regex('entry'), 'Q': {'type': 'regex', 'resolved_value': r'\d+'}}

    result = _run(dotted, metadata, dst=files[kind], expected_value='{{ P }}-{{ Q }}', **params)

    _assert(result, StatusEnum.ERROR)


@pytest.mark.parametrize(
    ('dotted', 'kind', 'params'), [t for t in VALUE_TESTS if 'count' in t[0]], ids=[i for i in IDS if 'count' in i]
)
def test_absence_count_does_not_pass_on_a_broken_placeholder(files, dotted, kind, params):
    """``expected_count: 0`` asserts absence: an unusable placeholder must not count as "none matched"."""
    params = {**params, 'expected_count': 0}

    for metadata, value in ((_regex('[unclosed'), '{{ P }}'), (_regex('x'), '{{ NOPE }}')):
        _assert(_run(dotted, metadata, dst=files[kind], expected_value=value, **params), StatusEnum.ERROR)


# --- !timestamp placeholders (the value is a time) ------------------------------------------

UNIX_S = 1704164645  # 2024-01-02 03:04:05 UTC


def _timestamp(**extra):
    return {
        'T': {
            'type': 'timestamp',
            'raw_value': str(UNIX_S),
            'resolved_value': str(UNIX_S),
            'tolerance': [-2, 2],
            **extra,
        }
    }


@pytest.fixture(scope='module')
def time_files(tmp_path_factory):
    root = tmp_path_factory.mktemp('placeholder_times')
    iso = '2024-01-02T03:04:06+00:00'
    filetime = (UNIX_S + 1 + 11644473600) * 10_000_000
    paths = {
        'json': root / 't.json',
        'yaml': root / 't.yaml',
        'toml': root / 't.toml',
        'ini': root / 't.ini',
    }
    paths['json'].write_text(json.dumps({'a': {'iso': iso, 'ft': filetime}}))
    paths['yaml'].write_text(f"a:\n  iso: '{iso}'\n  ft: {filetime}\n")
    paths['toml'].write_text(f'[a]\niso = "{iso}"\nft = {filetime}\n')
    paths['ini'].write_text(f'[a]\niso = {iso}\nft = {filetime}\n')
    return {kind: str(path) for kind, path in paths.items()}


def _time_params(dotted, field):
    if dotted.startswith('ini.'):
        return {'section': 'a', 'key': field}
    return {'key_path': f'a.{field}'}


TIME_TESTS = [t for t in VALUE_TESTS if t[1] in ('json', 'yaml', 'toml', 'ini')]


@pytest.mark.parametrize(
    ('field', 'metadata', 'status'),
    [
        pytest.param('iso', _timestamp(), StatusEnum.SUCCESS, id='iso-within-tolerance'),
        pytest.param('iso', _timestamp(tolerance=[0, 0]), StatusEnum.FAILED, id='iso-outside-tolerance'),
        pytest.param('ft', _timestamp(epoch=1601, unit='100ns'), StatusEnum.SUCCESS, id='filetime'),
        pytest.param('ft', _timestamp(epoch=1970, unit='s'), StatusEnum.FAILED, id='filetime-read-as-unix'),
    ],
)
@pytest.mark.parametrize(('dotted', 'kind', 'params'), TIME_TESTS, ids=[t[0] for t in TIME_TESTS])
def test_timestamp_placeholder_value(time_files, dotted, kind, params, field, metadata, status):
    count = {'expected_count': 1} if 'count' in dotted else {}

    result = _run(
        dotted, metadata, dst=time_files[kind], expected_value='{{ T }}', **_time_params(dotted, field), **count
    )

    _assert(result, status)
