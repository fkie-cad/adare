"""jsonl: an invalid regex is an ERROR whether or not some record has the key.

A test-definition problem (an invalid pattern, an unknown or broken ``{{ placeholder }}``) is
never FAILED for "key not found": the pattern is checked before the file is read.

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import json
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
jsonl = import_module_from_pyfile(COLLECTIONS / 'jsonl' / 'jsonl.py')

BAD = '[unclosed'
RECORDS = [{'name': 'entry-42', 'kind': 'a'}, {'name': 'other', 'kind': 'b'}]


def _run(name, dst, variable_metadata=None, **params):
    function = getattr(jsonl, name)
    test = function._test_class(
        name='t', parameter=function._parameter_class(dst=str(dst), **params), variable_metadata=variable_metadata
    )
    return test.test()


@pytest.fixture
def events(tmp_path):
    path = tmp_path / 'events.jsonl'
    path.write_text(''.join(json.dumps(r) + '\n' for r in RECORDS), encoding='utf-8')
    return path


def _calls(key):
    """One call per regex-taking function; ``key`` is the key path of the pattern's condition."""
    return {
        'line_matches': lambda pattern, **extra: ('line_matches', {'conditions': {key: pattern}, **extra}),
        'line_count': lambda pattern, **extra: (
            'line_count',
            {'conditions': {key: pattern}, 'expected_count': 0, **extra},
        ),
        'value_in_any_line': lambda pattern, **extra: (
            'value_in_any_line',
            {'key_path': key, 'expected_value': pattern, **extra},
        ),
        'lines_in_order': lambda pattern, **extra: (
            'lines_in_order',
            {'conditions': [{'kind': 'a'}, {key: pattern}], **extra},
        ),
    }


FUNCTIONS = ['line_matches', 'line_count', 'value_in_any_line', 'lines_in_order']


@pytest.mark.parametrize('function', FUNCTIONS)
@pytest.mark.parametrize('key', ['name', 'missing'], ids=['key-present', 'key-in-no-record'])
def test_invalid_regex_is_an_error(events, function, key):
    name, params = _calls(key)[function](BAD, regex_match=True)

    result = _run(name, events, **params)

    assert result.status == StatusEnum.ERROR, result.details
    assert BAD in ' '.join(map(str, result.details))


@pytest.mark.parametrize('function', FUNCTIONS)
def test_invalid_regex_is_an_error_on_an_empty_file(tmp_path, function):
    empty = tmp_path / 'empty.jsonl'
    empty.write_text('', encoding='utf-8')
    name, params = _calls('name')[function](BAD, regex_match=True)

    assert _run(name, empty, **params).status == StatusEnum.ERROR


@pytest.mark.parametrize('function', FUNCTIONS)
def test_valid_regex_with_no_record_having_the_key_is_failed(events, function):
    """The baseline: a valid pattern on a missing key stays FAILED (line_count: 0 matches)."""
    name, params = _calls('missing')[function]('entry-.*', regex_match=True)
    if name == 'line_count':
        params['expected_count'] = 1

    assert _run(name, events, **params).status == StatusEnum.FAILED


@pytest.mark.parametrize('function', FUNCTIONS)
def test_invalid_pattern_is_plain_text_without_regex_match(events, function):
    """Without ``regex_match`` the value is compared literally, so it is no regex at all."""
    name, params = _calls('missing')[function](BAD)
    if name == 'line_count':
        params['expected_count'] = 0

    status = _run(name, events, **params).status

    assert status in (StatusEnum.FAILED, StatusEnum.SUCCESS)


def test_star_with_regex_match_is_not_a_pattern(events):
    result = _run('line_matches', events, conditions={'name': '*'}, regex_match=True)

    assert result.status == StatusEnum.SUCCESS, result.details


def test_second_invalid_condition_is_found_too(events):
    result = _run('line_matches', events, conditions={'name': 'entry-.*', 'missing': BAD}, regex_match=True)

    assert result.status == StatusEnum.ERROR


# --- !re tag / placeholder path -----------------------------------------------------------

INVALID_REGEX = {'P': {'type': 'regex', 'raw_value': BAD, 'resolved_value': BAD}}
VALID_REGEX = {'P': {'type': 'regex', 'raw_value': r'entry-\d+', 'resolved_value': r'entry-\d+'}}
UNRESOLVED_REGEX = {'P': {'type': 'regex', 'raw_value': 'a{{ Q }}', 'resolved_value': 'a{{ Q }}'}}


@pytest.mark.parametrize('function', FUNCTIONS)
@pytest.mark.parametrize('key', ['name', 'missing'], ids=['key-present', 'key-in-no-record'])
def test_invalid_regex_placeholder_is_an_error(events, function, key):
    name, params = _calls(key)[function]('{{ P }}')

    result = _run(name, events, INVALID_REGEX, **params)

    assert result.status == StatusEnum.ERROR, result.details
    assert BAD in ' '.join(map(str, result.details))


@pytest.mark.parametrize('function', FUNCTIONS)
def test_unresolved_variable_in_regex_placeholder_is_an_error_without_the_key(events, function):
    name, params = _calls('missing')[function]('{{ P }}')

    result = _run(name, events, UNRESOLVED_REGEX, **params)

    assert result.status == StatusEnum.ERROR
    assert 'Q' in ' '.join(map(str, result.details))


@pytest.mark.parametrize('function', FUNCTIONS)
def test_unknown_placeholder_is_an_error_without_the_key(events, function):
    name, params = _calls('missing')[function]('{{ NOPE }}')

    result = _run(name, events, VALID_REGEX, **params)

    assert result.status == StatusEnum.ERROR
    assert 'NOPE' in ' '.join(map(str, result.details))


@pytest.mark.parametrize('function', FUNCTIONS)
def test_valid_regex_placeholder_on_a_missing_key_is_failed(events, function):
    name, params = _calls('missing')[function]('{{ P }}')
    if name == 'line_count':
        params['expected_count'] = 1

    assert _run(name, events, VALID_REGEX, **params).status == StatusEnum.FAILED


def test_valid_regex_placeholder_matches(events):
    result = _run('line_matches', events, VALID_REGEX, conditions={'name': '{{ P }}'})

    assert result.status == StatusEnum.SUCCESS, result.details


@pytest.mark.parametrize('key', ['name', 'missing'], ids=['key-present', 'key-in-no-record'])
def test_invalid_re_tag_object_is_an_error(events, key):
    """A ``!re`` value that reaches the function as the tag object (not as a placeholder)."""
    customtags = pytest.importorskip('adarelib.testset.yaml.customtags')

    result = _run('line_matches', events, conditions={key: customtags.YamlRegexString(BAD)})

    assert result.status == StatusEnum.ERROR, result.details
    assert BAD in ' '.join(map(str, result.details))
