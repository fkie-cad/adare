"""An invalid regular expression is an ERROR, never FAILED for "key / element / row not found".

A test-definition problem (an invalid pattern, an unknown or broken ``{{ placeholder }}``) is an
ERROR; FAILED means the evidence was read and the condition does not hold. A regex that is only
compiled when some value is compared lets a missing key, element or row hide the problem: the
test reports FAILED, which a negative test (``expect_to_fail``) turns into a pass. Every function
that takes a regex expected value therefore validates it before it reads the file
(``adarelib.testset.compare.regex_expected_problem``).

Each case below runs a function on a file that exists but cannot match (missing key, section,
element, keyword, row; wrong column count). The jsonl collection has its own file,
``test_jsonl_regex.py``. A new function with a ``regex_match`` parameter (or ``!re`` in its
docstring) must get a case here; ``test_every_regex_function_is_covered`` fails until it does.

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import inspect
import plistlib
import struct
import zlib
from pathlib import Path

import attrs
import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'

BAD = '[unclosed'
PAT = '@PAT@'  # where a case's regex goes (substituted inside strings, lists and dicts)
ROW = ['x', PAT, 'z']  # three columns; the files below have two or none
REGEX_MATCH = {'regex_match': True}
INVALID_REGEX = {'P': {'type': 'regex', 'raw_value': BAD, 'resolved_value': BAD}}
UNRESOLVED_REGEX = {'P': {'type': 'regex', 'raw_value': 'a{{ Q }}', 'resolved_value': 'a{{ Q }}'}}
VALID_REGEX = {'P': {'type': 'regex', 'raw_value': 'x.*', 'resolved_value': 'x.*'}}


# --- files that exist but hold none of what the cases look for ------------------------------


def _text(path, content):
    path.write_text(content, encoding='utf-8')


def _binary(path, data):
    path.write_bytes(data)


def _xlsx(path):
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.active.title = 'Data'
    workbook.active.append(['a', 'b'])
    workbook.save(path)


def _png(path):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)

    header = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0))
    data = chunk(b'IDAT', zlib.compress(b'\x00\x80'))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + header + chunk(b'tEXt', b'Comment\x00hello') + data + chunk(b'IEND', b''))


def _jpeg(path):
    from PIL import Image

    Image.new('RGB', (4, 4)).save(path, 'JPEG')


FILES = {
    'json': lambda p: _text(p, '{"a": 1}'),
    'yaml': lambda p: _text(p, 'a: 1\n'),
    'toml': lambda p: _text(p, 'a = 1\n'),
    'plist': lambda p: _binary(p, plistlib.dumps({'a': 1})),
    'ini': lambda p: _text(p, '[s]\nk = v\n'),
    'xml': lambda p: _text(p, '<r><a>x</a></r>'),
    'csv': lambda p: _text(p, 'a,b\n'),
    'xlsx': _xlsx,
    'png': _png,
    'jpeg': _jpeg,
    'table': lambda p: _binary(p, b'k\x00v\x00'),
    'text': lambda p: _text(p, 'hello\n'),
}
# Kinds for which an empty file is a valid file.
EMPTY_OK = ('csv', 'text')


# --- cases ---------------------------------------------------------------------------------


@attrs.define
class Case:
    """``params`` hold ``PAT`` where the regex goes.

    ``regex``: parameters that make that value a regex (``None``: only ``!re`` tags and
    placeholders can be regexes there). ``placeholder``: whether ``{{ P }}`` is evaluated.
    """

    kind: str
    params: dict
    regex: dict | None = None
    placeholder: bool = True


CASES = {
    # structured formats: the key path selects nothing
    **{
        f'{fmt}.value_matches': Case(fmt, {'key_path': 'missing', 'expected_value': PAT}, REGEX_MATCH)
        for fmt in ('json', 'yaml', 'toml', 'plist')
    },
    **{
        f'{fmt}.value_count': Case(
            fmt, {'key_path': 'missing', 'expected_count': 1, 'expected_value': PAT}, REGEX_MATCH
        )
        for fmt in ('json', 'yaml', 'toml', 'plist')
    },
    'json.array_contains': Case('json', {'array_path': 'missing', 'expected_value': PAT}),
    'ini.value_matches': Case('ini', {'section': 'none', 'key': 'k', 'expected_value': PAT}, REGEX_MATCH),
    'ini.value_count': Case(
        'ini', {'section': 'none', 'key': 'k', 'expected_count': 1, 'expected_value': PAT}, REGEX_MATCH
    ),
    'xml.element_text_matches': Case('xml', {'xpath': './/none', 'expected_value': PAT}, REGEX_MATCH),
    'xml.attribute_matches': Case('xml', {'xpath': './/none', 'attribute': 'b', 'expected_value': PAT}, REGEX_MATCH),
    # rows: placeholders only; the row has another column count (or the file is empty)
    'csv.contains_line': Case('csv', {'entry': ROW}),
    'csv.row_count': Case('csv', {'entry': ROW, 'expected_count': 1}),
    'csv.compare_rows': Case('csv', {'reference_rows': [ROW]}),
    'excel.contains_row': Case('xlsx', {'entry': ROW}),
    'excel.row_count': Case('xlsx', {'entry': ROW, 'expected_count': 1}),
    'excel.compare_rows': Case('xlsx', {'reference_rows': [ROW]}),
    'excel.cell_value_matches': Case('xlsx', {'row': 99, 'column': 0, 'expected_value': PAT}, REGEX_MATCH),
    'excel.sheet_exists': Case('xlsx', {'sheet': PAT}, REGEX_MATCH, placeholder=False),
    # images: no such keyword / tag
    'image.png_text_matches': Case('png', {'keyword': 'Missing', 'expected_value': PAT}, REGEX_MATCH),
    'image.png_text_count': Case(
        'png', {'keyword': 'Missing', 'expected_count': 1, 'expected_value': PAT}, REGEX_MATCH
    ),
    'image.exif_value_matches': Case('jpeg', {'tag': 'Make', 'expected_value': PAT}, REGEX_MATCH),
    'image.exif_value_count': Case('jpeg', {'tag': 'Make', 'expected_count': 1, 'expected_value': PAT}, REGEX_MATCH),
    # binary: no such key in the table
    'binary.pair_value_matches': Case('table', {'key': 'none', 'expected_value': PAT}, REGEX_MATCH),
    'binary.pair_count': Case('table', {'key': 'none', 'expected_count': 1, 'expected_value': PAT}, REGEX_MATCH),
    'binary.struct_value_matches': Case(
        'table', {'offset': 0, 'value_format': 'u8', 'expected_value': PAT}, REGEX_MATCH
    ),
    'binary.pattern_count': Case(
        'table', {'pattern': PAT, 'expected_count': 1}, {'pattern_type': 'regex'}, placeholder=False
    ),
    # text and plain files: the regex is the main parameter
    'text.line_count': Case('text', {'content': PAT, 'expected_count': 1}, REGEX_MATCH, placeholder=False),
    'text.lines_in_order': Case('text', {'patterns': [PAT]}, {'regex': True}, placeholder=False),
    'linux.log_entry_exists': Case('text', {'content': PAT}, REGEX_MATCH, placeholder=False),
    'standard.file_content_matches_regex': Case('text', {'regex': PAT}, {}, placeholder=False),
    'standard.file_content_equals': Case('text', {'content': 'a ' + PAT + ' b'}),
}

# Functions with a regex_match parameter or `!re` in their docstring that need no case here.
ELSEWHERE = {
    'jsonl.line_matches': 'test_jsonl_regex.py',
    'jsonl.line_count': 'test_jsonl_regex.py',
    'jsonl.value_in_any_line': 'test_jsonl_regex.py',
    'jsonl.lines_in_order': 'test_jsonl_regex.py',
    'standard.file_content_contains': 'content is plain text; a placeholder is rejected before the file is read',
    'text.occurrence_count': 'content is plain text; a placeholder is rejected before the file is read',
}


def _function(dotted):
    collection, name = dotted.split('.')
    module = import_module_from_pyfile(COLLECTIONS / collection / f'{collection}.py')
    return getattr(module, name)


def _fill(value, replacement):
    """``value`` with ``PAT`` replaced by ``replacement``, in strings, lists and dicts."""
    if isinstance(value, str):
        return value.replace(PAT, replacement)
    if isinstance(value, list):
        return [_fill(v, replacement) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, replacement) for k, v in value.items()}
    return value


def _run(dotted, tmp_path, pattern, extra=None, metadata=None, empty=False):
    case = CASES[dotted]
    path = tmp_path / 'data.bin'
    FILES[case.kind](path)
    if empty:
        path.write_bytes(b'')
    params = {**_fill(case.params, pattern), **(extra or {}), 'dst': str(path)}
    function = _function(dotted)
    test = function._test_class(name='t', parameter=function._parameter_class(**params), variable_metadata=metadata)
    return test.test()


def _regex_cases():
    return [pytest.param(d, id=d) for d, case in sorted(CASES.items()) if case.regex is not None]


def _placeholder_cases():
    return [pytest.param(d, id=d) for d, case in sorted(CASES.items()) if case.placeholder]


def _message(result):
    return ' '.join(map(str, result.details))


# --- an invalid regex ----------------------------------------------------------------------


@pytest.mark.parametrize('dotted', _regex_cases())
def test_invalid_regex_is_an_error(dotted, tmp_path):
    result = _run(dotted, tmp_path, BAD, CASES[dotted].regex)

    assert result.status == StatusEnum.ERROR, result.details
    assert BAD in _message(result)


@pytest.mark.parametrize('dotted', _placeholder_cases())
def test_invalid_regex_placeholder_is_an_error(dotted, tmp_path):
    result = _run(dotted, tmp_path, '{{ P }}', metadata=INVALID_REGEX)

    assert result.status == StatusEnum.ERROR, result.details
    assert BAD in _message(result)


@pytest.mark.parametrize('dotted', _placeholder_cases())
def test_unresolved_variable_in_regex_placeholder_is_an_error(dotted, tmp_path):
    result = _run(dotted, tmp_path, '{{ P }}', metadata=UNRESOLVED_REGEX)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'Q' in _message(result)


@pytest.mark.parametrize('dotted', _placeholder_cases())
def test_unknown_placeholder_is_an_error(dotted, tmp_path):
    result = _run(dotted, tmp_path, '{{ NOPE }}', metadata=VALID_REGEX)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'NOPE' in _message(result)


@pytest.mark.parametrize('dotted', sorted(d for d, case in CASES.items() if case.kind in EMPTY_OK))
def test_invalid_regex_is_an_error_on_an_empty_file(dotted, tmp_path):
    case = CASES[dotted]
    if case.regex is not None:
        result = _run(dotted, tmp_path, BAD, case.regex, empty=True)
    else:
        result = _run(dotted, tmp_path, '{{ P }}', metadata=INVALID_REGEX, empty=True)

    assert result.status == StatusEnum.ERROR, result.details


# --- the baseline: a valid pattern that finds nothing is still FAILED ------------------------


@pytest.mark.parametrize('dotted', _regex_cases())
def test_valid_regex_that_finds_nothing_is_failed(dotted, tmp_path):
    result = _run(dotted, tmp_path, 'x.*', CASES[dotted].regex)

    assert result.status == StatusEnum.FAILED, result.details


@pytest.mark.parametrize('dotted', _placeholder_cases())
def test_valid_regex_placeholder_that_finds_nothing_is_failed(dotted, tmp_path):
    result = _run(dotted, tmp_path, '{{ P }}', metadata=VALID_REGEX)

    assert result.status == StatusEnum.FAILED, result.details


# --- no function is missed -------------------------------------------------------------------


def _regex_taking_functions():
    """Every testfunction with a ``regex_match`` parameter or ``!re`` in its docstring."""
    found = []
    for path in sorted(COLLECTIONS.glob('*/*.py')):
        if path.stem != path.parent.name:
            continue
        module = import_module_from_pyfile(path)
        for name, obj in vars(module).items():
            parameter_class = getattr(obj, '_parameter_class', None)
            if parameter_class is None:
                continue
            fields = {f.name for f in attrs.fields(parameter_class)}
            if 'regex_match' in fields or '!re' in (inspect.getdoc(obj) or ''):
                found.append(f'{path.parent.name}.{name}')
    return found


def test_every_regex_function_is_covered():
    """A function that takes a regex expected value needs a case here (or a reason in ELSEWHERE)."""
    uncovered = [name for name in _regex_taking_functions() if name not in CASES and name not in ELSEWHERE]

    assert not uncovered, (
        'these functions take a regex but have no test that an invalid one is an ERROR even when '
        'nothing matches: validate it before reading the file (adarelib.testset.compare.'
        f'regex_expected_problem) and add a case to CASES: {uncovered}'
    )


def test_cases_and_exceptions_name_real_functions():
    for dotted in [*CASES, *ELSEWHERE]:
        assert hasattr(_function(dotted), '_test_class'), dotted
