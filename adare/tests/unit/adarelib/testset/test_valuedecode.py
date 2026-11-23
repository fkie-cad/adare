"""value_decode chains (adarelib.testset.valuedecode)."""

import base64
import json
import re

import pytest

from adarelib.constants import StatusEnum
from adarelib.testset.valuedecode import DecodedKeyPathMissing, ValueDecodeError, build_decoder, decoder_setup

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


@pytest.mark.parametrize(
    ('steps', 'key_path', 'value'),
    [
        ('json', 'a', '{"b": 1}'),
        ('json', 'a.b', '{"a": {"c": 1}}'),
        ('json', 'items[5]', '{"items": [1]}'),
        (['base64', 'json'], 'id', base64.b64encode(b'{"other": 1}').decode()),
        (['url', 'json'], 'a', '%7B%7D'),
    ],
)
def test_key_path_selecting_nothing_is_a_distinct_signal(steps, key_path, value):
    """The value decoded fine and the key is not in it: a subclass, so callers can say FAILED."""
    with pytest.raises(
        DecodedKeyPathMissing, match=f"step 'json'.*decoded_key_path {re.escape(repr(key_path))} selects nothing"
    ):
        build_decoder(steps, key_path)(value)


def test_missing_key_path_is_still_a_value_decode_error_for_old_callers():
    assert issubclass(DecodedKeyPathMissing, ValueDecodeError)


@pytest.mark.parametrize(
    ('key_path', 'value'),
    [
        ('*', '{"a": 1, "b": 2}'),  # selects two values: still an error
        ('a', 'not json'),  # the decode step fails
    ],
)
def test_other_json_problems_are_not_the_missing_signal(key_path, value):
    with pytest.raises(ValueDecodeError) as raised:
        build_decoder('json', key_path)(value)
    assert not isinstance(raised.value, DecodedKeyPathMissing)
