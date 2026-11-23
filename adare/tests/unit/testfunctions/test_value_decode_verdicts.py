"""value_decode verdicts: a ``decoded_key_path`` that selects nothing is FAILED, a decode that fails is ERROR.

The value decoded fine and the key is simply not in it: FAILED, like a ``key_path`` that selects
nothing in the file. A step that cannot decode (invalid base64, JSON, ...), a ``decoded_key_path``
that selects several values or bad parameters stay ERROR. In ``values_compare`` a decoded side
without the key behaves like a side that selects nothing.

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import base64
import json
import plistlib
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
_modules = {}


def _b64(document) -> str:
    return base64.b64encode(json.dumps(document).encode()).decode()


HAS_ID = _b64({'id': 9})
NO_ID = _b64({'other': 1})
TWO_IDS = _b64({'a': {'id': 1}, 'b': {'id': 2}})
NOT_BASE64 = 'a$b'
STEPS = {'value_decode': ['base64', 'json'], 'decoded_key_path': 'id'}


def _run(dotted, **params):
    collection, name = dotted.split('.')
    if collection not in _modules:
        _modules[collection] = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
    function = getattr(_modules[collection], name)
    return function._test_class(name='t', parameter=function._parameter_class(**params)).test()


def _assert(result, status):
    assert result.status == status, f'expected {status.name}, got {result.status}: {result.details}'


def _write(tmp_path, name, content):
    path = tmp_path / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding='utf-8')
    return str(path)


@pytest.fixture
def files(tmp_path):
    """One file per format; the keys ``has_id``, ``no_id``, ``two_ids`` and ``bad`` hold the blobs above."""
    blobs = {'has_id': HAS_ID, 'no_id': NO_ID, 'two_ids': TWO_IDS, 'bad': NOT_BASE64}
    return {
        'yaml': _write(tmp_path, 'a.yaml', ''.join(f'{k}: {v}\n' for k, v in blobs.items())),
        'toml': _write(tmp_path, 'a.toml', ''.join(f'{k} = "{v}"\n' for k, v in blobs.items())),
        'json': _write(tmp_path, 'a.json', json.dumps(blobs)),
        'plist': _write(tmp_path, 'a.plist', plistlib.dumps(blobs)),
        'ini': _write(tmp_path, 'a.ini', '[s]\n' + ''.join(f'{k} = {v}\n' for k, v in blobs.items())),
        'xml': _write(tmp_path, 'a.xml', '<r>' + ''.join(f'<{k}>{v}</{k}>' for k, v in blobs.items()) + '</r>'),
        'jsonl': _write(tmp_path, 'a.jsonl', '\n'.join(json.dumps({'k': v}) for v in blobs.values()) + '\n'),
    }


# (function, file kind, parameters selecting one blob: key -> parameters)
VALUE_MATCHES = {
    'yaml.value_matches': ('yaml', lambda k: {'key_path': k, 'expected_value': 9}),
    'toml.value_matches': ('toml', lambda k: {'key_path': k, 'expected_value': 9}),
    'json.value_matches': ('json', lambda k: {'key_path': k, 'expected_value': 9}),
    'plist.value_matches': ('plist', lambda k: {'key_path': k, 'expected_value': 9}),
    'ini.value_matches': ('ini', lambda k: {'section': 's', 'key': k, 'expected_value': '9'}),  # text formats
    'xml.element_text_matches': ('xml', lambda k: {'xpath': f'./{k}', 'expected_value': '9'}),
}


@pytest.mark.parametrize('dotted', VALUE_MATCHES)
def test_value_matches_decoded_value_matches(files, dotted):
    kind, where = VALUE_MATCHES[dotted]

    _assert(_run(dotted, dst=files[kind], **where('has_id'), **STEPS), StatusEnum.SUCCESS)


@pytest.mark.parametrize('dotted', VALUE_MATCHES)
def test_value_matches_decoded_key_path_selecting_nothing_is_failed(files, dotted):
    kind, where = VALUE_MATCHES[dotted]

    result = _run(dotted, dst=files[kind], **where('no_id'), **STEPS)

    _assert(result, StatusEnum.FAILED)
    assert "decoded_key_path 'id' selects nothing" in ' '.join(map(str, result.details))


@pytest.mark.parametrize('dotted', VALUE_MATCHES)
def test_value_matches_decode_failure_and_several_values_stay_errors(files, dotted):
    kind, where = VALUE_MATCHES[dotted]

    _assert(_run(dotted, dst=files[kind], **where('bad'), **STEPS), StatusEnum.ERROR)
    several = _run(dotted, dst=files[kind], **where('two_ids'), **{**STEPS, 'decoded_key_path': '*.id'})
    _assert(several, StatusEnum.ERROR)
    assert 'selects 2 values' in ' '.join(map(str, several.details))
    # json without decoded_key_path is a parameter problem
    _assert(
        _run(dotted, dst=files[kind], **where('has_id'), value_decode=['base64', 'json']),
        StatusEnum.ERROR,
    )


def test_value_matches_attribute_decoded_key_path_selecting_nothing_is_failed(tmp_path):
    path = _write(tmp_path, 'a.xml', f'<r><e ref="{NO_ID}"/></r>')

    result = _run('xml.attribute_matches', dst=path, xpath='./e', attribute='ref', expected_value='9', **STEPS)

    _assert(result, StatusEnum.FAILED)


def test_jsonl_decoded_key_path_selecting_nothing_is_failed(tmp_path):
    path = _write(tmp_path, 'a.jsonl', json.dumps({'k': NO_ID}) + '\n' + json.dumps({'k': _b64({'x': 1})}) + '\n')

    result = _run('jsonl.value_in_any_line', dst=path, key_path='k', expected_value=9, **STEPS)

    _assert(result, StatusEnum.FAILED)
    assert "selected nothing in 2 value(s)" in ' '.join(map(str, result.details))


def test_jsonl_a_line_without_the_decoded_key_does_not_stop_a_later_match(tmp_path):
    path = _write(tmp_path, 'a.jsonl', json.dumps({'k': NO_ID}) + '\n' + json.dumps({'k': HAS_ID}) + '\n')

    _assert(_run('jsonl.value_in_any_line', dst=path, key_path='k', expected_value=9, **STEPS), StatusEnum.SUCCESS)


def test_jsonl_decode_failure_is_an_error(tmp_path):
    path = _write(tmp_path, 'a.jsonl', json.dumps({'k': NOT_BASE64}) + '\n')

    _assert(_run('jsonl.value_in_any_line', dst=path, key_path='k', expected_value=9, **STEPS), StatusEnum.ERROR)


# --- several values (a wildcard): a value without the key is a non-match of that value -----


def test_wildcard_any_matches_despite_a_value_without_the_decoded_key(tmp_path):
    path = _write(tmp_path, 'a.yaml', f'blobs: [{NO_ID}, {HAS_ID}]\n')

    _assert(_run('yaml.value_matches', dst=path, key_path='blobs[*]', expected_value=9, **STEPS), StatusEnum.SUCCESS)


def test_wildcard_all_fails_with_a_value_without_the_decoded_key(tmp_path):
    path = _write(tmp_path, 'a.yaml', f'blobs: [{NO_ID}, {HAS_ID}]\n')

    result = _run('yaml.value_matches', dst=path, key_path='blobs[*]', expected_value=9, wildcard_mode='all', **STEPS)

    _assert(result, StatusEnum.FAILED)


def test_wildcard_with_no_decoded_key_anywhere_is_failed(tmp_path):
    path = _write(tmp_path, 'a.yaml', f'blobs: [{NO_ID}, {NO_ID}]\n')

    _assert(_run('yaml.value_matches', dst=path, key_path='blobs[*]', expected_value=9, **STEPS), StatusEnum.FAILED)


# --- values_compare ---------------------------------------------------------------------

VALUES_COMPARE = {
    'yaml.values_compare': ('yaml', lambda a, b: {'key_path': a, 'other_key_path': b}),
    'toml.values_compare': ('toml', lambda a, b: {'key_path': a, 'other_key_path': b}),
    'json.values_compare': ('json', lambda a, b: {'key_path': a, 'other_key_path': b}),
    'plist.values_compare': ('plist', lambda a, b: {'key_path': a, 'other_key_path': b}),
    'xml.values_compare': ('xml', lambda a, b: {'xpath': f'./{a}', 'other_xpath': f'./{b}'}),
}


@pytest.mark.parametrize('dotted', VALUES_COMPARE)
def test_values_compare_decoded_sides_compare(files, dotted):
    kind, where = VALUES_COMPARE[dotted]

    _assert(_run(dotted, dst=files[kind], **where('has_id', 'has_id'), **STEPS), StatusEnum.SUCCESS)


@pytest.mark.parametrize('dotted', VALUES_COMPARE)
@pytest.mark.parametrize('sides', [('no_id', 'has_id'), ('has_id', 'no_id'), ('no_id', 'no_id')])
def test_values_compare_decoded_key_path_selecting_nothing_is_failed(files, dotted, sides):
    kind, where = VALUES_COMPARE[dotted]

    result = _run(dotted, dst=files[kind], **where(*sides), **STEPS)

    _assert(result, StatusEnum.FAILED)
    assert "decoded_key_path 'id' selects nothing" in ' '.join(map(str, result.details))


@pytest.mark.parametrize('dotted', VALUES_COMPARE)
@pytest.mark.parametrize('sides', [('bad', 'has_id'), ('has_id', 'bad'), ('bad', 'no_id'), ('no_id', 'bad')])
def test_values_compare_decode_failure_wins_over_a_missing_key(files, dotted, sides):
    kind, where = VALUES_COMPARE[dotted]

    _assert(_run(dotted, dst=files[kind], **where(*sides), **STEPS), StatusEnum.ERROR)


@pytest.mark.parametrize('dotted', VALUES_COMPARE)
def test_values_compare_several_decoded_values_is_an_error(files, dotted):
    kind, where = VALUES_COMPARE[dotted]

    _assert(
        _run(dotted, dst=files[kind], **where('two_ids', 'two_ids'), **{**STEPS, 'decoded_key_path': '*.id'}),
        StatusEnum.ERROR,
    )
