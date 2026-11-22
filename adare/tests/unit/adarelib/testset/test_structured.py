"""Shared key-path testfunction bodies (structured.py) and content helpers (content.py)."""

import datetime
import json

import pytest

from adarelib.constants import StatusEnum
from adarelib.testset import content, structured
from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.testset.structured import StructuredFormat

pytestmark = pytest.mark.unit


def _load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


JSON = StructuredFormat('JSON', _load_json, (json.JSONDecodeError,))


def _ctx():
    return BasicTest(name='t', parameter=Parameter(), description='', variable_metadata=None)


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / 'doc.json'
    path.write_text(
        json.dumps({'a': {'b': 1, 'n': None}, 'tags': ['x', 'y', 'x'], 'items': [{'k': 1}, {'k': 2}, {'k': 1}]})
    )
    return str(path)


# --- contains_key ----------------------------------------------------------------


def test_contains_key(doc):
    assert structured.contains_key(_ctx(), doc, 'a.b', JSON).status == StatusEnum.SUCCESS
    assert structured.contains_key(_ctx(), doc, 'a.n', JSON).status == StatusEnum.SUCCESS  # null counts
    assert structured.contains_key(_ctx(), doc, 'a.c', JSON).status == StatusEnum.FAILED


def test_missing_file_is_error_does_not_exist(tmp_path):
    result = structured.contains_key(_ctx(), str(tmp_path / 'none.json'), 'a', JSON)
    assert result.status == StatusEnum.ERROR
    assert 'does not exist' in result.details[0]


@pytest.mark.parametrize('names', [[], ['one.json', 'two.json']])
def test_glob_zero_or_several_is_error(tmp_path, names):
    for name in names:
        (tmp_path / name).write_text('{}')
    result = structured.contains_key(_ctx(), str(tmp_path / '*.json'), 'a', JSON)
    assert result.status == StatusEnum.ERROR


def test_invalid_content_is_error(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{not json')
    assert structured.contains_key(_ctx(), str(path), 'a', JSON).status == StatusEnum.ERROR


def test_undecodable_content_is_error(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_bytes(b'{"a": "\xff"}')
    assert structured.contains_key(_ctx(), str(path), 'a', JSON).status == StatusEnum.ERROR


def test_directory_is_error(tmp_path):
    assert structured.contains_key(_ctx(), str(tmp_path), 'a', JSON).status == StatusEnum.ERROR


# --- value_matches -----------------------------------------------------------------


def test_value_matches(doc):
    assert structured.value_matches(_ctx(), doc, 'a.b', 1, JSON).status == StatusEnum.SUCCESS
    assert structured.value_matches(_ctx(), doc, 'a.b', '1', JSON).status == StatusEnum.FAILED  # type-sensitive
    assert structured.value_matches(_ctx(), doc, 'a.zz', 1, JSON).status == StatusEnum.FAILED


def test_value_matches_array_elements_and_modes(doc):
    assert structured.value_matches(_ctx(), doc, 'tags', 'y', JSON).status == StatusEnum.SUCCESS
    assert structured.value_matches(_ctx(), doc, 'items[*].k', 1, JSON).status == StatusEnum.SUCCESS
    result = structured.value_matches(_ctx(), doc, 'items[*].k', 1, JSON, wildcard_mode='all')
    assert result.status == StatusEnum.FAILED


def test_value_matches_regex(doc):
    assert structured.value_matches(_ctx(), doc, 'tags[0]', '^x$', JSON, regex_match=True).status == StatusEnum.SUCCESS
    result = structured.value_matches(_ctx(), doc, 'tags[0]', '(', JSON, regex_match=True)
    assert result.status == StatusEnum.ERROR


def test_value_matches_bad_wildcard_mode_is_error(doc):
    assert structured.value_matches(_ctx(), doc, 'a.b', 1, JSON, wildcard_mode='some').status == StatusEnum.ERROR


# --- value_count ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ('key_path', 'kwargs', 'status'),
    [
        ('a.b', {'expected_count': 1}, StatusEnum.SUCCESS),
        ('a.zz', {'expected_count': 0}, StatusEnum.SUCCESS),  # absence
        ('a.b', {'expected_count': 0}, StatusEnum.FAILED),
        ('items[*].k', {'expected_count': 3}, StatusEnum.SUCCESS),
        ('items[*].k', {'expected_count': 2, 'expected_value': 1}, StatusEnum.SUCCESS),
        ('tags', {'expected_count': 2, 'expected_value': 'x'}, StatusEnum.SUCCESS),  # array elements
        ('tags', {'expected_count': 0, 'expected_value': 'z'}, StatusEnum.SUCCESS),
        ('tags', {'expected_count': 1, 'expected_value': '^y', 'regex_match': True}, StatusEnum.SUCCESS),
        ('items[*].k', {'expected_count': 2, 'comparison_type': 'greater'}, StatusEnum.SUCCESS),
        ('items[*].k', {'expected_count': 3, 'comparison_type': 'less'}, StatusEnum.FAILED),
        ('items[*].k', {'expected_count': 3, 'comparison_type': 'less_equal'}, StatusEnum.SUCCESS),
        ('items[*].k', {'expected_count': 4, 'comparison_type': 'greater_equal'}, StatusEnum.FAILED),
    ],
)
def test_value_count(doc, key_path, kwargs, status):
    assert structured.value_count(_ctx(), doc, key_path, fmt=JSON, **kwargs).status == status


@pytest.mark.parametrize(
    'kwargs',
    [
        {'expected_count': -1},
        {'expected_count': 'two'},
        {'expected_count': True},
        {'expected_count': 1, 'comparison_type': 'eq'},
    ],
)
def test_value_count_bad_parameters_are_error(doc, kwargs):
    assert structured.value_count(_ctx(), doc, 'a.b', fmt=JSON, **kwargs).status == StatusEnum.ERROR


def test_value_count_missing_file_is_error_even_for_zero(tmp_path):
    result = structured.value_count(_ctx(), str(tmp_path / 'none.json'), 'a', 0, JSON)
    assert result.status == StatusEnum.ERROR


# --- helpers ---------------------------------------------------------------------------


def test_normalize():
    data = {
        1: datetime.date(2024, 1, 2),
        'when': datetime.datetime(2024, 1, 2, 3, 4, 5),
        'raw': b'\x01\xff',
        'seq': (1, 2),
    }
    assert structured.normalize(data) == {
        '1': '2024-01-02',
        'when': '2024-01-02T03:04:05',
        'raw': '01ff',
        'seq': [1, 2],
    }


def test_compare_count_rejects_unknown_type():
    with pytest.raises(ValueError):
        structured.compare_count(1, 1, 'eq')


@pytest.mark.parametrize(
    ('raw', 'encoding', 'text'),
    [
        (b'\xef\xbb\xbfa=1', None, 'a=1'),
        ('a=1'.encode('utf-16'), None, 'a=1'),
        ('a=1'.encode('utf-16-le'), None, 'a=1'),  # BOM-less UTF-16 guessed
        ('a=1'.encode('utf-16-be'), None, 'a=1'),
        ('ä=1'.encode('latin-1'), 'latin-1', 'ä=1'),
        (b'a=1', None, 'a=1'),
    ],
)
def test_decode_text(raw, encoding, text):
    assert content.decode_text(raw, encoding) == text


def test_read_bytes_capped(tmp_path):
    path = tmp_path / 'f'
    path.write_bytes(b'x' * 10)
    assert content.read_bytes_capped(str(path), 10) == b'x' * 10
    with pytest.raises(content.FileTooLargeError):
        content.read_bytes_capped(str(path), 9)
    with pytest.raises(FileNotFoundError):
        content.read_bytes_capped(str(tmp_path / 'none'))


def test_normalize_keeps_shared_and_cyclic_containers():
    leaf = ['x'] * 10
    level = leaf
    for _ in range(30):  # 10**30 leaves if expanded
        level = [level] * 10
    assert structured.normalize({'root': level})['root'][0][0] is not None

    cyclic: list = [1]
    cyclic.append(cyclic)
    out = structured.normalize(cyclic)
    assert out[1] is out


def test_alias_bomb_messages_stay_small(tmp_path):
    yaml = pytest.importorskip('yaml')
    lines = ['a: &a ["x", "x", "x", "x", "x", "x", "x", "x", "x"]']
    for i, name in enumerate('bcdefgh'):
        prev = 'abcdefgh'[i]
        lines.append(
            f'{name}: &{name} [*{prev}, *{prev}, *{prev}, *{prev}, *{prev}, *{prev}, *{prev}, *{prev}, *{prev}]'
        )
    path = tmp_path / 'bomb.yaml'
    path.write_text('\n'.join(lines) + '\n')

    def _load(p):
        with open(p, 'rb') as f:
            return yaml.safe_load(f)

    fmt = StructuredFormat('YAML', _load, (yaml.YAMLError,))
    result = structured.contains_key(_ctx(), str(path), 'h', fmt)
    assert result.status == StatusEnum.SUCCESS
    assert sum(len(d) for d in result.details) < 20_000  # unbounded: ~300 MB
    result = structured.value_matches(_ctx(), str(path), 'h', 'nope', fmt, regex_match=True)
    assert result.status == StatusEnum.FAILED
    assert sum(len(d) for d in result.details) < 20_000  # unbounded: ~300 MB
