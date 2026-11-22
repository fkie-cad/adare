"""Text encodings in the json, csv and jsonl collections.

Without ``encoding`` a file is read as UTF-8/16/32 with or without BOM; with a name
(``latin-1``, ``cp1252``) BOM-less files are decoded with it, and a BOM always wins. An
unknown name or content that cannot be decoded is an ERROR; a decoded file whose value does
not match is FAILED.
"""

import json
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
_modules = {}


def _module(collection):
    if collection not in _modules:
        _modules[collection] = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
    return _modules[collection]


def _run(dotted, **params):
    collection, name = dotted.split('.')
    function = getattr(_module(collection), name)
    return function._test_class(name='t', parameter=function._parameter_class(**params)).test()


def _assert(result, status):
    assert result.status == status, f'expected {status.name}, got {result.status}: {result.details}'


# the BOM-less UTF-16 guess needs an ASCII first character, which '{' and 'M' are
UNICODE_ENCODINGS = {
    'utf-8': ('utf-8', b''),
    'utf-8-bom': ('utf-8', b'\xef\xbb\xbf'),
    'utf-16-le-bom': ('utf-16-le', b'\xff\xfe'),
    'utf-16-be-bom': ('utf-16-be', b'\xfe\xff'),
    'utf-16-le': ('utf-16-le', b''),
    'utf-16-be': ('utf-16-be', b''),
    'utf-32-le-bom': ('utf-32-le', b'\xff\xfe\x00\x00'),
}


def _write(path: Path, text: str, variant: str) -> str:
    codec, bom = UNICODE_ENCODINGS[variant]
    path.write_bytes(bom + text.encode(codec))
    return str(path)


# --- JSON -------------------------------------------------------------------------------

DOC = {'name': 'Müller', 'tags': ['café', 'straße', 'café'], 'größe': 3, 'city': 'Zürich'}
JSON_TEXT = json.dumps(DOC, ensure_ascii=False)


@pytest.mark.parametrize('variant', list(UNICODE_ENCODINGS))
def test_json_value_matches_in_every_unicode_encoding(tmp_path, variant):
    dst = _write(tmp_path / 'doc.json', JSON_TEXT, variant)

    _assert(_run('json.value_matches', dst=dst, key_path='name', expected_value='Müller'), StatusEnum.SUCCESS)
    _assert(_run('json.value_matches', dst=dst, key_path='größe', expected_value=3), StatusEnum.SUCCESS)


@pytest.mark.parametrize('variant', list(UNICODE_ENCODINGS))
def test_json_value_count_in_every_unicode_encoding(tmp_path, variant):
    dst = _write(tmp_path / 'doc.json', JSON_TEXT, variant)

    result = _run('json.value_count', dst=dst, key_path='tags[*]', expected_value='café', expected_count=2)

    _assert(result, StatusEnum.SUCCESS)
    assert result.details[0] == '2 value(s) at "tags[*]" match "café"'


@pytest.mark.parametrize('variant', ['utf-8-bom', 'utf-16-le-bom', 'utf-16-be'])
def test_json_mismatch_in_a_decoded_file_fails(tmp_path, variant):
    dst = _write(tmp_path / 'doc.json', JSON_TEXT, variant)

    _assert(_run('json.value_matches', dst=dst, key_path='name', expected_value='Mueller'), StatusEnum.FAILED)
    _assert(
        _run('json.value_count', dst=dst, key_path='tags[*]', expected_value='café', expected_count=3),
        StatusEnum.FAILED,
    )


def test_json_escaped_non_ascii_equals_the_literal_characters(tmp_path):
    dst = tmp_path / 'doc.json'
    dst.write_text(json.dumps(DOC, ensure_ascii=True))
    assert b'\\u00fc' in dst.read_bytes()

    _assert(_run('json.value_matches', dst=str(dst), key_path='name', expected_value='Müller'), StatusEnum.SUCCESS)


def test_json_regex_on_non_ascii_text(tmp_path):
    dst = _write(tmp_path / 'doc.json', JSON_TEXT, 'utf-16-le-bom')

    result = _run(
        'json.value_count', dst=dst, key_path='tags[*]', expected_value='^stra', regex_match=True, expected_count=1
    )

    _assert(result, StatusEnum.SUCCESS)


@pytest.fixture
def latin1_json(tmp_path):
    path = tmp_path / 'latin1.json'
    path.write_bytes(JSON_TEXT.encode('latin-1'))
    return str(path)


@pytest.mark.parametrize('encoding', ['latin-1', 'iso-8859-1', 'cp1252'])
def test_json_latin1_file_with_encoding(latin1_json, encoding):
    _assert(
        _run('json.value_matches', dst=latin1_json, key_path='city', expected_value='Zürich', encoding=encoding),
        StatusEnum.SUCCESS,
    )
    _assert(
        _run(
            'json.value_count',
            dst=latin1_json,
            key_path='tags[*]',
            expected_value='café',
            expected_count=2,
            encoding=encoding,
        ),
        StatusEnum.SUCCESS,
    )


@pytest.mark.parametrize('encoding', [None, 'utf-8'])
def test_json_latin1_file_read_as_utf8_is_an_error(latin1_json, encoding):
    params = {} if encoding is None else {'encoding': encoding}

    result = _run('json.value_matches', dst=latin1_json, key_path='city', expected_value='Zürich', **params)
    _assert(result, StatusEnum.ERROR)
    assert 'Cannot decode JSON file' in result.details[0]
    _assert(_run('json.value_count', dst=latin1_json, key_path='city', expected_count=1, **params), StatusEnum.ERROR)


@pytest.mark.parametrize('variant', ['utf-8-bom', 'utf-16-le-bom', 'utf-16-be-bom', 'utf-32-le-bom'])
def test_json_bom_wins_over_the_encoding_parameter(tmp_path, variant):
    dst = _write(tmp_path / 'doc.json', JSON_TEXT, variant)

    result = _run('json.value_matches', dst=dst, key_path='name', expected_value='Müller', encoding='latin-1')

    _assert(result, StatusEnum.SUCCESS)


def test_json_bomless_utf8_read_as_latin1_is_read_but_does_not_match(tmp_path):
    # the parameter is obeyed: UTF-8 bytes decoded as Latin-1 are mojibake, not an error
    dst = _write(tmp_path / 'doc.json', JSON_TEXT, 'utf-8')

    result = _run('json.value_matches', dst=dst, key_path='name', expected_value='Müller', encoding='latin-1')

    _assert(result, StatusEnum.FAILED)
    assert 'MÃ¼ller' in result.details[0]


@pytest.mark.parametrize(
    'dotted, params',
    [
        ('json.value_matches', {'key_path': 'name', 'expected_value': 'Müller'}),
        ('json.value_count', {'key_path': 'name', 'expected_count': 1}),
        ('json.contains_key', {'key_path': 'name'}),
        ('json.array_contains', {'array_path': 'tags', 'expected_value': 'café'}),
    ],
)
def test_json_unknown_encoding_is_an_error(tmp_path, dotted, params):
    dst = _write(tmp_path / 'doc.json', JSON_TEXT, 'utf-8')

    result = _run(dotted, dst=dst, encoding='no-such-codec', **params)

    _assert(result, StatusEnum.ERROR)
    assert 'unknown encoding' in result.details[0]


def test_json_utf16_without_bom_and_explicit_utf16_encoding(tmp_path):
    dst = _write(tmp_path / 'doc.json', JSON_TEXT, 'utf-16-le')

    result = _run('json.value_matches', dst=dst, key_path='name', expected_value='Müller', encoding='utf-16-le')

    _assert(result, StatusEnum.SUCCESS)


# --- CSV --------------------------------------------------------------------------------

CSV_TEXT = 'Müller,café\r\nSchmidt,straße\r\nMüller,café\r\n'


@pytest.mark.parametrize('variant', list(UNICODE_ENCODINGS))
def test_csv_in_every_unicode_encoding(tmp_path, variant):
    dst = _write(tmp_path / 'rows.csv', CSV_TEXT, variant)

    _assert(_run('csv.contains_line', dst=dst, entry=['Schmidt', 'straße']), StatusEnum.SUCCESS)
    _assert(_run('csv.row_count', dst=dst, entry=['Müller', 'café'], expected_count=2), StatusEnum.SUCCESS)


def test_csv_bom_is_not_part_of_the_first_field(tmp_path):
    dst = _write(tmp_path / 'rows.csv', CSV_TEXT, 'utf-8-bom')

    _assert(_run('csv.row_count', dst=dst, entry=['Müller', 'café'], expected_count=2), StatusEnum.SUCCESS)
    _assert(
        _run(
            'csv.compare_rows', dst=dst, reference_rows=[['Müller', 'café'], ['Schmidt', 'straße'], ['Müller', 'café']]
        ),
        StatusEnum.SUCCESS,
    )


@pytest.fixture
def cp1252_csv(tmp_path):
    path = tmp_path / 'cp1252.csv'
    path.write_bytes('Müller,5 €\r\nSchmidt,7 €\r\n'.encode('cp1252'))
    return str(path)


def test_csv_with_an_encoding(cp1252_csv):
    _assert(_run('csv.contains_line', dst=cp1252_csv, entry=['Müller', '5 €'], encoding='cp1252'), StatusEnum.SUCCESS)
    _assert(
        _run('csv.row_count', dst=cp1252_csv, entry=['Schmidt', '7 €'], expected_count=1, encoding='cp1252'),
        StatusEnum.SUCCESS,
    )
    _assert(
        _run('csv.contains_line', dst=cp1252_csv, entry=['Müller', '7 €'], encoding='cp1252'),
        StatusEnum.FAILED,
    )


def test_csv_latin1_reads_cp1252_bytes_differently(cp1252_csv):
    # the euro sign is 0x80 in cp1252, a C1 control in Latin-1: read, but no match
    _assert(_run('csv.contains_line', dst=cp1252_csv, entry=['Müller', '5 €'], encoding='latin-1'), StatusEnum.FAILED)


def test_csv_undecodable_without_encoding_is_an_error(cp1252_csv):
    result = _run('csv.contains_line', dst=cp1252_csv, entry=['Müller', '5 €'])

    _assert(result, StatusEnum.ERROR)
    _assert(_run('csv.row_count', dst=cp1252_csv, entry=['Müller', '5 €'], expected_count=1), StatusEnum.ERROR)


@pytest.mark.parametrize(
    'dotted, params',
    [
        ('csv.contains_line', {'entry': ['a', 'b']}),
        ('csv.row_count', {'entry': ['a', 'b'], 'expected_count': 1}),
        ('csv.compare_rows', {'reference_rows': [['a', 'b']]}),
    ],
)
def test_csv_unknown_encoding_is_an_error(tmp_path, dotted, params):
    dst = _write(tmp_path / 'rows.csv', 'a,b\r\n', 'utf-8')

    result = _run(dotted, dst=dst, encoding='no-such-codec', **params)

    _assert(result, StatusEnum.ERROR)
    assert 'unknown encoding' in result.details[0]


def test_csv_compare_files_reads_both_files_with_the_encoding(tmp_path, cp1252_csv):
    reference = tmp_path / 'reference.csv'
    reference.write_bytes(Path(cp1252_csv).read_bytes())

    _assert(
        _run('csv.compare_files', actual=cp1252_csv, reference=str(reference), encoding='cp1252'), StatusEnum.SUCCESS
    )
    _assert(_run('csv.compare_files', actual=cp1252_csv, reference=str(reference)), StatusEnum.ERROR)


def test_csv_compare_files_bom_differs_but_content_matches(tmp_path):
    actual = _write(tmp_path / 'a.csv', CSV_TEXT, 'utf-16-le-bom')
    reference = _write(tmp_path / 'r.csv', CSV_TEXT, 'utf-8')

    _assert(_run('csv.compare_files', actual=actual, reference=reference), StatusEnum.SUCCESS)


# --- JSONL ------------------------------------------------------------------------------

JSONL_TEXT = ''.join(
    json.dumps(line, ensure_ascii=False) + '\n'
    for line in [
        {'user': 'Müller', 'city': 'Zürich'},
        {'user': 'Schmidt', 'city': 'Köln'},
        {'user': 'Müller', 'city': 'Köln'},
    ]
)


@pytest.mark.parametrize('variant', list(UNICODE_ENCODINGS))
def test_jsonl_in_every_unicode_encoding(tmp_path, variant):
    dst = _write(tmp_path / 'events.jsonl', JSONL_TEXT, variant)

    _assert(_run('jsonl.value_in_any_line', dst=dst, key_path='city', expected_value='Zürich'), StatusEnum.SUCCESS)
    _assert(
        _run('jsonl.line_count', dst=dst, conditions={'user': 'Müller'}, expected_count=2, skip_malformed=False),
        StatusEnum.SUCCESS,
    )
    _assert(
        _run('jsonl.line_matches', dst=dst, conditions={'user': 'Schmidt', 'city': 'Köln'}, skip_malformed=False),
        StatusEnum.SUCCESS,
    )


@pytest.fixture
def latin1_jsonl(tmp_path):
    path = tmp_path / 'latin1.jsonl'
    path.write_bytes(JSONL_TEXT.encode('latin-1'))
    return str(path)


def test_jsonl_with_an_encoding(latin1_jsonl):
    _assert(
        _run('jsonl.value_in_any_line', dst=latin1_jsonl, key_path='city', expected_value='Köln', encoding='latin-1'),
        StatusEnum.SUCCESS,
    )
    _assert(
        _run('jsonl.line_count', dst=latin1_jsonl, conditions={'city': 'Köln'}, expected_count=2, encoding='latin-1'),
        StatusEnum.SUCCESS,
    )
    _assert(
        _run('jsonl.line_matches', dst=latin1_jsonl, conditions={'user': 'Müller'}, encoding='latin-1'),
        StatusEnum.SUCCESS,
    )
    _assert(
        _run('jsonl.value_in_any_line', dst=latin1_jsonl, key_path='city', expected_value='Bonn', encoding='latin-1'),
        StatusEnum.FAILED,
    )


@pytest.mark.parametrize(
    'dotted, params',
    [
        ('jsonl.value_in_any_line', {'key_path': 'city', 'expected_value': 'Köln'}),
        ('jsonl.line_count', {'conditions': {'city': 'Köln'}, 'expected_count': 2}),
        ('jsonl.line_matches', {'conditions': {'city': 'Köln'}}),
    ],
)
def test_jsonl_undecodable_without_encoding_is_an_error(latin1_jsonl, dotted, params):
    result = _run(dotted, dst=latin1_jsonl, **params)

    _assert(result, StatusEnum.ERROR)
    assert 'Cannot decode JSONL file' in result.details[0]


@pytest.mark.parametrize(
    'dotted, params',
    [
        ('jsonl.value_in_any_line', {'key_path': 'city', 'expected_value': 'Köln'}),
        ('jsonl.line_count', {'conditions': {'city': 'Köln'}, 'expected_count': 2}),
        ('jsonl.line_matches', {'conditions': {'city': 'Köln'}}),
    ],
)
def test_jsonl_unknown_encoding_is_an_error(tmp_path, dotted, params):
    dst = _write(tmp_path / 'events.jsonl', JSONL_TEXT, 'utf-8')

    result = _run(dotted, dst=dst, encoding='no-such-codec', **params)

    _assert(result, StatusEnum.ERROR)
    assert 'unknown encoding' in result.details[0]


def test_jsonl_bom_wins_over_the_encoding_parameter(tmp_path):
    dst = _write(tmp_path / 'events.jsonl', JSONL_TEXT, 'utf-16-be-bom')

    result = _run('jsonl.value_in_any_line', dst=dst, key_path='city', expected_value='Zürich', encoding='latin-1')

    _assert(result, StatusEnum.SUCCESS)
