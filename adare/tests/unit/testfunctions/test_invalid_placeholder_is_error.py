"""Contract: a placeholder the test cannot evaluate is an ERROR, never FAILED or SUCCESS.

``expected_value: !re 'x'`` reaches a testfunction as ``{{ name }}`` plus
``variable_metadata[name]``. When the metadata holds an invalid regular expression, or the
name has no metadata at all, nothing can be said about the artifact: ``compare_with_placeholder``
raises ``PlaceholderError`` and the ``@testfunction`` decorator reports ERROR. Each collection
function that accepts a value is run with both broken placeholders, on a file in which the
value is present (so a silent fallback to "no match" or to a literal comparison shows).

Functions that search for ``content`` (text.occurrence_count/line_count,
standard.file_content_contains) do not support placeholders at all: one there is an ERROR,
even a valid one, since it would otherwise be searched for literally.

A literal ``!re`` pattern is compiled when the playbook YAML is loaded, so an invalid one is
already a YAML error.
"""

import json
import plistlib
import sqlite3
import struct
import zlib
from pathlib import Path

import pandas as pd
import pytest
import yaml
from PIL import Image

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile
from adarelib.testset.yaml.customloader import get_custom_loader

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
VALUE = 'entry-42'

INVALID_REGEX = {'P': {'type': 'regex', 'raw_value': '[unclosed', 'resolved_value': '[unclosed'}}
VALID = {'P': {'type': 'regex', 'raw_value': r'entry-\d+', 'resolved_value': r'entry-\d+'}}
# 'P' is known, the value names 'NOPE'
UNKNOWN = VALID

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


def _png_chunk(ctype: bytes, body: bytes) -> bytes:
    return struct.pack('>I', len(body)) + ctype + body + struct.pack('>I', zlib.crc32(ctype + body) & 0xFFFFFFFF)


def _png_with_text(keyword: str, text: str) -> bytes:
    ihdr = _png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0))
    idat = _png_chunk(b'IDAT', zlib.compress(b'\x00\x80'))
    text_chunk = _png_chunk(b'tEXt', keyword.encode('latin-1') + b'\x00' + text.encode('latin-1'))
    return b'\x89PNG\r\n\x1a\n' + ihdr + text_chunk + idat + _png_chunk(b'IEND', b'')


@pytest.fixture(scope='module')
def files(tmp_path_factory):
    """One readable file per format, each holding VALUE where the tests look."""
    root = tmp_path_factory.mktemp('invalid_placeholder')
    paths = {kind: root / f'a.{kind}' for kind in ('csv', 'json', 'jsonl', 'xml', 'txt', 'yaml', 'toml', 'ini')}
    paths['csv'].write_text(f'id,name\n1,{VALUE}\n')
    paths['json'].write_text(json.dumps({'name': VALUE, 'names': [VALUE, 'other'], 'n': {'name': VALUE}}))
    paths['jsonl'].write_text(f'{{"name": "{VALUE}"}}\n{{"name": "other"}}\n')
    paths['xml'].write_text(f'<root><item id="{VALUE}">{VALUE}</item></root>')
    paths['txt'].write_text(f'{VALUE}\n')
    paths['yaml'].write_text(f'n:\n  name: {VALUE}\n')
    paths['toml'].write_text(f'[n]\nname = "{VALUE}"\n')
    paths['ini'].write_text(f'[n]\nname = {VALUE}\n')
    paths['plist'] = root / 'a.plist'
    paths['plist'].write_bytes(plistlib.dumps({'n': {'name': VALUE}}))
    paths['png'] = root / 'a.png'
    paths['png'].write_bytes(_png_with_text('name', VALUE))
    paths['jpeg'] = root / 'a.jpg'
    exif = Image.Exif()
    exif[0x010F] = VALUE  # Make
    Image.new('RGB', (4, 4), 'red').save(paths['jpeg'], 'JPEG', exif=exif)
    paths['xlsx'] = root / 'a.xlsx'
    with pd.ExcelWriter(paths['xlsx'], engine='openpyxl') as writer:
        pd.DataFrame([['id', 'name'], ['1', VALUE]]).to_excel(writer, sheet_name='S', index=False, header=False)
    paths['sqlite'] = root / 'a.sqlite'
    conn = sqlite3.connect(paths['sqlite'])
    conn.execute('CREATE TABLE t (name TEXT)')
    conn.execute('INSERT INTO t VALUES (?)', (VALUE,))
    conn.commit()
    conn.close()
    return {kind: str(path) for kind, path in paths.items()}


# (testfunction, file kind, parameters builder: placeholder text -> parameters)
VALUE_FUNCTIONS = [
    ('csv.contains_line', 'csv', lambda p: {'entry': ['1', p]}),
    ('csv.row_count', 'csv', lambda p: {'entry': ['1', p], 'expected_count': 1}),
    ('excel.cell_value_matches', 'xlsx', lambda p: {'row': 1, 'column': 1, 'expected_value': p}),
    ('excel.contains_row', 'xlsx', lambda p: {'entry': ['1', p]}),
    ('json.value_matches', 'json', lambda p: {'key_path': 'name', 'expected_value': p}),
    ('json.value_count', 'json', lambda p: {'key_path': 'names[*]', 'expected_value': p, 'expected_count': 1}),
    ('json.array_contains', 'json', lambda p: {'array_path': 'names', 'expected_value': p}),
    ('jsonl.line_matches', 'jsonl', lambda p: {'conditions': {'name': p}}),
    ('jsonl.line_count', 'jsonl', lambda p: {'conditions': {'name': p}, 'expected_count': 1}),
    ('jsonl.value_in_any_line', 'jsonl', lambda p: {'key_path': 'name', 'expected_value': p}),
    ('xml.element_text_matches', 'xml', lambda p: {'xpath': './/item', 'expected_value': p}),
    ('xml.attribute_matches', 'xml', lambda p: {'xpath': './/item', 'attribute': 'id', 'expected_value': p}),
    ('ini.value_matches', 'ini', lambda p: {'section': 'n', 'key': 'name', 'expected_value': p}),
    ('ini.value_count', 'ini', lambda p: {'section': 'n', 'key': 'name', 'expected_value': p, 'expected_count': 1}),
    ('yaml.value_matches', 'yaml', lambda p: {'key_path': 'n.name', 'expected_value': p}),
    ('yaml.value_count', 'yaml', lambda p: {'key_path': 'n.name', 'expected_value': p, 'expected_count': 1}),
    ('toml.value_matches', 'toml', lambda p: {'key_path': 'n.name', 'expected_value': p}),
    ('toml.value_count', 'toml', lambda p: {'key_path': 'n.name', 'expected_value': p, 'expected_count': 1}),
    ('plist.value_matches', 'plist', lambda p: {'key_path': 'n.name', 'expected_value': p}),
    ('plist.value_count', 'plist', lambda p: {'key_path': 'n.name', 'expected_value': p, 'expected_count': 1}),
    ('image.png_text_matches', 'png', lambda p: {'keyword': 'name', 'expected_value': p}),
    ('image.png_text_count', 'png', lambda p: {'keyword': 'name', 'expected_value': p, 'expected_count': 1}),
    ('image.exif_value_matches', 'jpeg', lambda p: {'tag': 'Make', 'expected_value': p}),
    ('image.exif_value_count', 'jpeg', lambda p: {'tag': 'Make', 'expected_value': p, 'expected_count': 1}),
    ('sqlite.query_result', 'sqlite', lambda p: {'query': 'SELECT name FROM t', 'expected_result': [{'name': p}]}),
    ('standard.file_content_equals', 'txt', lambda p: {'content': p}),
]
IDS = [f[0] for f in VALUE_FUNCTIONS]


@pytest.mark.parametrize(('dotted', 'kind', 'build'), VALUE_FUNCTIONS, ids=IDS)
def test_valid_placeholder_passes(files, dotted, kind, build):
    """The baseline: the same call with a usable placeholder passes, so the ERRORs below come
    from the placeholder alone."""
    _assert(_run(dotted, VALID, dst=files[kind], **build('{{ P }}')), StatusEnum.SUCCESS)


@pytest.mark.parametrize(('dotted', 'kind', 'build'), VALUE_FUNCTIONS, ids=IDS)
def test_invalid_regex_placeholder_is_an_error(files, dotted, kind, build):
    result = _run(dotted, INVALID_REGEX, dst=files[kind], **build('{{ P }}'))

    _assert(result, StatusEnum.ERROR)
    assert '[unclosed' in ' '.join(map(str, result.details))


@pytest.mark.parametrize(('dotted', 'kind', 'build'), VALUE_FUNCTIONS, ids=IDS)
def test_unknown_placeholder_is_an_error(files, dotted, kind, build):
    result = _run(dotted, UNKNOWN, dst=files[kind], **build('{{ NOPE }}'))

    _assert(result, StatusEnum.ERROR)
    assert 'NOPE' in ' '.join(map(str, result.details))


@pytest.mark.parametrize(('dotted', 'kind', 'build'), VALUE_FUNCTIONS, ids=IDS)
def test_placeholder_without_any_metadata_is_an_error(files, dotted, kind, build):
    """No ``variable_metadata`` at all (``None``): the placeholder is unknown too."""
    _assert(_run(dotted, None, dst=files[kind], **build('{{ P }}')), StatusEnum.ERROR)


# --- content searches: no placeholder support, so any placeholder is an ERROR ---------------

CONTENT_FUNCTIONS = [
    ('text.occurrence_count', {'expected_count': 1}),
    ('text.line_count', {'expected_count': 1}),
    ('standard.file_content_contains', {}),
]


@pytest.mark.parametrize('metadata', [VALID, INVALID_REGEX, None], ids=['valid', 'invalid-regex', 'no-metadata'])
@pytest.mark.parametrize(('dotted', 'params'), CONTENT_FUNCTIONS, ids=[f[0] for f in CONTENT_FUNCTIONS])
def test_placeholder_in_content_is_an_error(files, dotted, params, metadata):
    result = _run(dotted, metadata, dst=files['txt'], content='{{ P }}', **params)

    _assert(result, StatusEnum.ERROR)
    assert 'placeholder' in ' '.join(map(str, result.details))


@pytest.mark.parametrize(('dotted', 'params'), CONTENT_FUNCTIONS, ids=[f[0] for f in CONTENT_FUNCTIONS])
def test_placeholder_inside_longer_content_is_an_error(files, dotted, params):
    _assert(_run(dotted, VALID, dst=files['txt'], content='entry-{{ P }}', **params), StatusEnum.ERROR)


# --- a literal !re is checked when the YAML loads -------------------------------------------


@pytest.mark.parametrize('pattern', ['[unclosed', '(open', '*start', '(?P<x>a)(?P<x>b)'])
def test_invalid_literal_regex_is_a_yaml_error(pattern):
    with pytest.raises(yaml.YAMLError, match='invalid regular expression'):
        yaml.load(f"expected_value: !re '{pattern}'\n", Loader=get_custom_loader())


def test_valid_literal_regex_loads():
    loaded = yaml.load("expected_value: !re 'entry-\\d+'\n", Loader=get_custom_loader())

    assert loaded['expected_value'].string == r'entry-\d+'


def test_regex_with_a_variable_is_compiled_later():
    """``{{ var }}`` is resolved after loading, so the pattern cannot be checked yet."""
    loaded = yaml.load("expected_value: !re '{{ prefix }}[unclosed'\n", Loader=get_custom_loader())

    assert loaded['expected_value'].string == '{{ prefix }}[unclosed'
