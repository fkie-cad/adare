"""Unit tests for jsonl.lines_in_order (kept apart from test_jsonl.py, which is near the size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import io
import json
import tarfile
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
jsonl = import_module_from_pyfile(COLLECTIONS / 'jsonl' / 'jsonl.py')
LinesInOrder = jsonl.lines_in_order._test_class
LinesInOrderParameter = jsonl.lines_in_order._parameter_class

EVENTS = [
    {'event': 'login', 'user': {'name': 'alice'}},  # line 1
    {'event': 'file_opened', 'path': '/data/report.txt', 'tags': ['doc', 'work']},  # line 2
    {'event': 'heartbeat'},  # line 3
    {'event': 'file_deleted', 'path': '/data/report.txt'},  # line 4
    {'event': 'file_opened', 'path': '/data/notes.txt'},  # line 5
    {'event': 'logout', 'user': {'name': 'alice'}},  # line 6
]


def _write(tmp_path, records, name='events.jsonl') -> Path:
    path = tmp_path / name
    path.write_text(''.join((r if isinstance(r, str) else json.dumps(r)) + '\n' for r in records), encoding='utf-8')
    return path


def _in_order(dst, **params):
    return LinesInOrder(name='t', parameter=LinesInOrderParameter(dst=str(dst), **params)).test()


@pytest.fixture
def events(tmp_path):
    return _write(tmp_path, EVENTS)


def test_conditions_in_order_pass_and_report_line_numbers(events):
    result = _in_order(
        events,
        conditions=[{'event': 'login', 'user.name': 'alice'}, {'event': 'file_deleted'}, {'event': 'logout'}],
    )

    assert result.status == StatusEnum.SUCCESS, result.details
    assert result.details[0] == '3 condition set(s) met in order on lines 1, 4, 6'
    assert "condition 2 {'event': 'file_deleted'} matched line 4" in result.details


def test_each_condition_takes_the_earliest_later_record(events):
    result = _in_order(events, conditions=[{'event': 'file_opened'}, {'event': 'file_opened'}])

    assert result.status == StatusEnum.SUCCESS, result.details
    assert 'lines 2, 5' in result.details[0]


def test_out_of_order_names_the_condition_and_its_earlier_lines(events):
    result = _in_order(events, conditions=[{'event': 'file_deleted'}, {'path': '/data/report.txt'}])

    assert result.status == StatusEnum.FAILED, result.details
    assert result.details[0] == (
        "condition 2 {'path': '/data/report.txt'} is met by no record after line 4 (6 record(s)); "
        'it is met only earlier, on line(s) 2, 4: out of order'
    )
    assert result.details[1] == "condition 1 {'event': 'file_deleted'} matched line 4"


def test_missing_condition_fails(events):
    result = _in_order(events, conditions=[{'event': 'login'}, {'event': 'file_renamed'}])

    assert result.status == StatusEnum.FAILED, result.details
    assert 'is met by no record after line 1' in result.details[0]
    assert 'earlier' not in result.details[0]
    first = _in_order(events, conditions=[{'event': 'file_renamed'}])
    assert 'is met by no record in the file' in first.details[0]


def test_condition_matching_is_the_one_of_line_matches(events):
    # wildcard over an array, regex values and "*" (key exists) behave as in jsonl.line_matches
    assert _in_order(events, conditions=[{'tags[*]': 'work'}, {'event': 'logout'}]).status == StatusEnum.SUCCESS
    result = _in_order(events, conditions=[{'path': r'report\.txt$'}, {'user': '*'}], regex_match=True)
    assert result.status == StatusEnum.SUCCESS, result.details
    assert 'lines 2, 6' in result.details[0]
    assert _in_order(events, conditions=[{'event': 'login', 'user.name': 'bob'}]).status == StatusEnum.FAILED


def test_blank_and_malformed_lines(tmp_path):
    path = _write(tmp_path, [EVENTS[0], '', '{not json', EVENTS[3]])

    result = _in_order(path, conditions=[{'event': 'login'}, {'event': 'file_deleted'}])
    assert result.status == StatusEnum.SUCCESS, result.details
    assert 'lines 1, 4' in result.details[0]  # physical line numbers
    strict = _in_order(path, conditions=[{'event': 'login'}], skip_malformed=False)
    assert strict.status == StatusEnum.ERROR, strict.details
    assert 'Malformed JSON on line 3' in strict.details[0]


def test_non_object_records_do_not_match(tmp_path):
    path = _write(tmp_path, [[1, 2], 'null', '"text"', EVENTS[0]])

    assert _in_order(path, conditions=[{'event': 'login'}]).status == StatusEnum.SUCCESS


def test_empty_file_fails(tmp_path):
    path = tmp_path / 'empty.jsonl'
    path.write_bytes(b'')

    assert _in_order(path, conditions=[{'event': 'login'}]).status == StatusEnum.FAILED


def test_archive_member(tmp_path):
    data = ''.join(json.dumps(r) + '\n' for r in EVENTS).encode()
    archive = tmp_path / 'logs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        info = tarfile.TarInfo('logs/events.jsonl')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    result = _in_order(f'{archive}!/logs/events.jsonl', conditions=[{'event': 'login'}, {'event': 'logout'}])

    assert result.status == StatusEnum.SUCCESS, result.details


def test_utf16_file(tmp_path):
    path = tmp_path / 'events.jsonl'
    path.write_bytes(''.join(json.dumps(r) + '\n' for r in EVENTS).encode('utf-16'))

    assert _in_order(path, conditions=[{'event': 'login'}, {'event': 'logout'}]).status == StatusEnum.SUCCESS


@pytest.mark.parametrize(
    'params',
    [
        {'conditions': []},
        {'conditions': None},
        {'conditions': {'event': 'login'}},
        {'conditions': [{'event': 'login'}, {}]},
        {'conditions': [{'event': 'login'}, 'logout']},
        {'conditions': [{1: 'login'}]},
        {'conditions': [{'event': '[unclosed'}], 'regex_match': True},
        {'conditions': [{'event': 'login'}], 'encoding': 'no-such-codec'},
    ],
)
def test_bad_parameters_are_errors(events, params):
    result = _in_order(events, **params)

    assert result.status == StatusEnum.ERROR, result.details


def test_missing_file_is_an_error(tmp_path):
    result = _in_order(tmp_path / 'missing.jsonl', conditions=[{'event': 'login'}])

    assert result.status == StatusEnum.ERROR
    assert 'does not exist' in result.details[0]
