"""value_decode chains (adarelib.testset.valuedecode)."""

import base64
import json

import pytest

from adarelib.constants import StatusEnum
from adarelib.testset.valuedecode import ValueDecodeError, build_decoder, decoder_setup

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ('steps', 'key_path', 'value', 'expected'),
    [
        ('url', None, 'a%2Fb%20c+d', 'a/b c+d'),
        (['url'], None, b'%C3%A4', 'ä'),
        ('base64', None, base64.b64encode(b'hello').decode(), 'hello'),
        ('base64', None, 'aGVsbG8', 'hello'),  # padding missing
        ('base64', None, 'aGVs\nbG8=', 'hello'),  # whitespace
        ('base64', None, base64.urlsafe_b64encode(b'\xfb\xff').decode(), 'fbff'),  # no UTF-8: hex
        ('hex', None, '68 69', 'hi'),
        (['hex', 'utf16'], None, '680069000000', 'hi'),  # little-endian, trailing NUL dropped
        (['hex', 'utf16'], None, 'feff00680069', 'hi'),  # BOM: big-endian
        (['base64', 'utf16'], None, base64.b64encode('ab'.encode('utf-16-le')).decode(), 'ab'),
        ('json', 'a.b', '{"a": {"b": 5}}', 5),
        (['url', 'json'], 'items[1]', '%5B%5D'.replace('%5B%5D', '%7B%22items%22%3A%5B1%2C2%5D%7D'), 2),
        (['base64', 'json'], 'id', base64.b64encode(json.dumps({'id': 'x'}).encode()).decode(), 'x'),
        ('url', None, 42, '42'),
    ],
)
def test_chains(steps, key_path, value, expected):
    assert build_decoder(steps, key_path)(value) == expected


def test_as_text_gives_json_text_for_non_strings():
    decoder = build_decoder('json', 'a')
    assert decoder('{"a": 5}', as_text=True) == '5'
    assert decoder('{"a": true}', as_text=True) == 'true'
    assert decoder('{"a": "x"}', as_text=True) == 'x'


def test_no_decoding_by_default():
    assert build_decoder() is None
    assert build_decoder([]) is None
    assert decoder_setup() == (None, None)


@pytest.mark.parametrize(
    ('steps', 'key_path', 'value', 'step'),
    [
        ('base64', None, 'a$b', 'base64'),
        ('hex', None, 'xyz', 'hex'),
        ('utf16', None, 'text', 'utf16'),  # needs bytes
        (['hex', 'utf16'], None, '00d8', 'utf16'),  # lone surrogate
        ('json', 'a', 'not json', 'json'),
        ('json', 'a', '{"b": 1}', 'json'),  # selects nothing
        ('json', '*', '{"a": 1, "b": 2}', 'json'),  # selects two
        ('url', None, {'a': 1}, 'url'),
        (['url', 'json'], 'a', '%FF', 'json'),  # no UTF-8 text
    ],
)
def test_decode_failure_names_the_step(steps, key_path, value, step):
    with pytest.raises(ValueDecodeError, match=f"step '{step}'"):
        build_decoder(steps, key_path)(value)


@pytest.mark.parametrize(
    ('steps', 'key_path', 'message'),
    [
        ('rot13', None, 'unknown value_decode step'),
        (['url', 5], None, 'unknown value_decode step'),
        ('json', None, 'needs decoded_key_path'),
        (['json', 'json'], 'a', 'only once'),
        ('url', 'a', "needs a 'json' step"),
        (None, 'a', "needs a 'json' step"),
        ({'a': 1}, None, 'step name or a list'),
    ],
)
def test_bad_parameters(steps, key_path, message):
    with pytest.raises(ValueDecodeError, match=message):
        build_decoder(steps, key_path)
    decoder, problem = decoder_setup(steps, key_path)
    assert decoder is None and problem.status == StatusEnum.ERROR
