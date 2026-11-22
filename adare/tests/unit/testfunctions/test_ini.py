"""Unit tests for the ini testfunction collection (own tolerant line parser)."""

import zipfile
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
ini = import_module_from_pyfile(COLLECTIONS / 'ini' / 'ini.py')

SectionExists = ini.section_exists._test_class
ContainsKey = ini.contains_key._test_class
ValueMatches = ini.value_matches._test_class
ValueCount = ini.value_count._test_class

SAMPLE = """\
top = level
; a comment
# another comment
[General]
language = de_DE
port=8080
empty =
quoted = "x" ; note
url = http://host/?a=b=c
flag
[RecentFiles]
file = /home/user/Documents/a.txt
file = /home/user/Documents/b.txt
[General]
language = en_US
[Spaced Name] ; trailing comment
key = value
"""


def _run(test_class, **params):
    param_cls = {
        SectionExists: ini.section_exists._parameter_class,
        ContainsKey: ini.contains_key._parameter_class,
        ValueMatches: ini.value_matches._parameter_class,
        ValueCount: ini.value_count._parameter_class,
    }[test_class]
    return test_class(name='t', parameter=param_cls(**params)).test()


def _assert(result, status):
    assert result.status == status, f'{result.status}: {result.details}'


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / 'settings.ini'
    path.write_text(SAMPLE, encoding='utf-8')
    return str(path)


# --- parser ---------------------------------------------------------------------------


def test_parser_rules():
    parsed = ini.parse_ini(SAMPLE)

    assert parsed.sections == ('General', 'RecentFiles', 'General', 'Spaced Name')
    pairs = [(e.section, e.key, e.value) for e in parsed.entries]
    assert ('', 'top', 'level') in pairs
    assert ('General', 'port', '8080') in pairs
    assert ('General', 'empty', '') in pairs
    assert ('General', 'quoted', '"x" ; note') in pairs  # raw: no quote / comment stripping
    assert ('General', 'url', 'http://host/?a=b=c') in pairs  # first '=' splits
    assert not any(e.key == 'flag' for e in parsed.entries)  # line without '=' ignored
    assert ('Spaced Name', 'key', 'value') in pairs


def test_bracket_line_with_text_after_is_not_a_header():
    parsed = ini.parse_ini('[a] b = c\n')
    assert parsed.sections == ()
    assert [(e.section, e.key, e.value) for e in parsed.entries] == [('', '[a] b', 'c')]


# --- section_exists ---------------------------------------------------------------------


def test_section_exists(sample):
    _assert(_run(SectionExists, dst=sample, section='General'), StatusEnum.SUCCESS)
    _assert(_run(SectionExists, dst=sample, section='Spaced Name'), StatusEnum.SUCCESS)


def test_section_missing_fails(sample):
    result = _run(SectionExists, dst=sample, section='Other')
    _assert(result, StatusEnum.FAILED)
    assert 'General' in result.details[1]


def test_section_case_insensitive(sample):
    _assert(_run(SectionExists, dst=sample, section='general'), StatusEnum.FAILED)
    _assert(_run(SectionExists, dst=sample, section='general', case_sensitive=False), StatusEnum.SUCCESS)


# --- contains_key -----------------------------------------------------------------------


def test_contains_key(sample):
    _assert(_run(ContainsKey, dst=sample, section='General', key='port'), StatusEnum.SUCCESS)
    _assert(_run(ContainsKey, dst=sample, section='General', key='empty'), StatusEnum.SUCCESS)
    _assert(_run(ContainsKey, dst=sample, section='', key='top'), StatusEnum.SUCCESS)


def test_contains_key_missing_fails(sample):
    _assert(_run(ContainsKey, dst=sample, section='General', key='flag'), StatusEnum.FAILED)
    _assert(_run(ContainsKey, dst=sample, section='RecentFiles', key='port'), StatusEnum.FAILED)
    _assert(_run(ContainsKey, dst=sample, section='', key='port'), StatusEnum.FAILED)


def test_contains_key_case_insensitive(sample):
    _assert(_run(ContainsKey, dst=sample, section='GENERAL', key='PORT'), StatusEnum.FAILED)
    _assert(_run(ContainsKey, dst=sample, section='GENERAL', key='PORT', case_sensitive=False), StatusEnum.SUCCESS)


# --- value_matches ----------------------------------------------------------------------


def test_value_matches(sample):
    _assert(_run(ValueMatches, dst=sample, section='General', key='port', expected_value='8080'), StatusEnum.SUCCESS)


def test_value_matches_yaml_number_compares_as_text(sample):
    _assert(_run(ValueMatches, dst=sample, section='General', key='port', expected_value=8080), StatusEnum.SUCCESS)


def test_value_matches_mismatch_fails(sample):
    result = _run(ValueMatches, dst=sample, section='General', key='port', expected_value='9090')
    _assert(result, StatusEnum.FAILED)


def test_value_matches_missing_key_fails(sample):
    _assert(_run(ValueMatches, dst=sample, section='General', key='nope', expected_value='x'), StatusEnum.FAILED)


def test_value_matches_duplicate_section_any_occurrence(sample):
    # [General] appears twice; language = de_DE and en_US
    _assert(
        _run(ValueMatches, dst=sample, section='General', key='language', expected_value='en_US'), StatusEnum.SUCCESS
    )
    result = _run(ValueMatches, dst=sample, section='General', key='language', expected_value='fr_FR')
    _assert(result, StatusEnum.FAILED)
    assert '0/2' in result.details[0]


def test_value_matches_raw_value(sample):
    params = {'dst': sample, 'section': 'General', 'key': 'quoted'}
    _assert(_run(ValueMatches, expected_value='"x" ; note', **params), StatusEnum.SUCCESS)
    _assert(_run(ValueMatches, expected_value='x', **params), StatusEnum.FAILED)


def test_value_matches_regex(sample):
    params = {'dst': sample, 'section': 'RecentFiles', 'key': 'file', 'regex_match': True}
    _assert(_run(ValueMatches, expected_value=r'b\.txt$', **params), StatusEnum.SUCCESS)
    _assert(_run(ValueMatches, expected_value=r'c\.txt$', **params), StatusEnum.FAILED)


def test_value_matches_invalid_regex_is_error(sample):
    result = _run(ValueMatches, dst=sample, section='General', key='port', expected_value='[', regex_match=True)
    _assert(result, StatusEnum.ERROR)


def test_value_matches_values_stay_case_sensitive(sample):
    params = {'dst': sample, 'section': 'general', 'key': 'LANGUAGE', 'case_sensitive': False}
    _assert(_run(ValueMatches, expected_value='de_DE', **params), StatusEnum.SUCCESS)
    _assert(_run(ValueMatches, expected_value='DE_DE', **params), StatusEnum.FAILED)


@pytest.mark.parametrize(
    ('expected_value', 'regex_match', 'wildcard_mode', 'status'),
    [
        ('/home/user/Documents/a.txt', False, 'any', StatusEnum.SUCCESS),
        ('/home/user/Documents/a.txt', False, 'all', StatusEnum.FAILED),
        (r'^/home/user/Documents/', True, 'all', StatusEnum.SUCCESS),
        (r'b\.txt$', True, 'all', StatusEnum.FAILED),
        (r'c\.txt$', True, 'any', StatusEnum.FAILED),
    ],
)
def test_value_matches_wildcard_mode(sample, expected_value, regex_match, wildcard_mode, status):
    # [RecentFiles] has file = .../a.txt and file = .../b.txt
    result = _run(
        ValueMatches,
        dst=sample,
        section='RecentFiles',
        key='file',
        expected_value=expected_value,
        regex_match=regex_match,
        wildcard_mode=wildcard_mode,
    )
    _assert(result, status)
    assert f'(mode: {wildcard_mode})' in result.details[0]
    if status == StatusEnum.FAILED:
        assert result.details[2].startswith('non-matching values: line 1')


def test_value_matches_wildcard_all_with_re_placeholder(sample):
    variables = {'regex_0_resolved': {'raw_value': '.*_[A-Z]{2}$', 'resolved_value': '.*_[A-Z]{2}$', 'type': 'regex'}}
    param = ini.value_matches._parameter_class(
        dst=sample, section='General', key='language', expected_value='{{regex_0_resolved}}', wildcard_mode='all'
    )
    _assert(ValueMatches(name='t', parameter=param, variable_metadata=variables).test(), StatusEnum.SUCCESS)


def test_value_matches_single_occurrence_ignores_mode(sample):
    params = {'dst': sample, 'section': 'General', 'key': 'port', 'wildcard_mode': 'all'}
    _assert(_run(ValueMatches, expected_value=8080, **params), StatusEnum.SUCCESS)
    _assert(_run(ValueMatches, expected_value=9090, **params), StatusEnum.FAILED)


@pytest.mark.parametrize('wildcard_mode', ['some', 'ALL', None])
def test_value_matches_invalid_wildcard_mode_is_error(sample, wildcard_mode):
    result = _run(
        ValueMatches, dst=sample, section='General', key='port', expected_value='8080', wildcard_mode=wildcard_mode
    )
    _assert(result, StatusEnum.ERROR)
    assert 'Invalid wildcard_mode' in result.details[0]


# --- value_count ------------------------------------------------------------------------


def test_value_count_duplicates(sample):
    _assert(_run(ValueCount, dst=sample, section='RecentFiles', key='file', expected_count=2), StatusEnum.SUCCESS)
    _assert(_run(ValueCount, dst=sample, section='General', key='language', expected_count=2), StatusEnum.SUCCESS)


def test_value_count_mismatch_fails(sample):
    _assert(_run(ValueCount, dst=sample, section='RecentFiles', key='file', expected_count=3), StatusEnum.FAILED)


def test_value_count_with_value(sample):
    params = {'dst': sample, 'section': 'RecentFiles', 'key': 'file'}
    _assert(
        _run(ValueCount, expected_value='/home/user/Documents/a.txt', expected_count=1, **params), StatusEnum.SUCCESS
    )
    _assert(_run(ValueCount, expected_value='txt', regex_match=True, expected_count=2, **params), StatusEnum.SUCCESS)


def test_value_count_zero_asserts_absence(sample):
    _assert(_run(ValueCount, dst=sample, section='General', key='gone', expected_count=0), StatusEnum.SUCCESS)
    _assert(_run(ValueCount, dst=sample, section='General', key='port', expected_count=0), StatusEnum.FAILED)
    _assert(
        _run(ValueCount, dst=sample, section='General', key='port', expected_value='1', expected_count=0),
        StatusEnum.SUCCESS,
    )


def test_value_count_comparison_type(sample):
    params = {'dst': sample, 'section': 'RecentFiles', 'key': 'file', 'expected_count': 1}
    _assert(_run(ValueCount, comparison_type='greater', **params), StatusEnum.SUCCESS)
    _assert(_run(ValueCount, comparison_type='less', **params), StatusEnum.FAILED)


@pytest.mark.parametrize(
    'params',
    [
        {'expected_count': -1},
        {'expected_count': True},
        {'expected_count': 1, 'comparison_type': 'between'},
        {'expected_count': 1, 'expected_value': '[', 'regex_match': True},
    ],
)
def test_value_count_bad_parameters_are_errors(sample, params):
    _assert(_run(ValueCount, dst=sample, section='General', key='port', **params), StatusEnum.ERROR)


# --- encodings --------------------------------------------------------------------------


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be'])
def test_bom_and_utf16_are_detected(tmp_path, encoding):
    path = tmp_path / 'enc.ini'
    path.write_bytes('[Gruppe]\nname = Grüße\n'.encode(encoding))
    _assert(_run(ValueMatches, dst=str(path), section='Gruppe', key='name', expected_value='Grüße'), StatusEnum.SUCCESS)


def test_explicit_encoding(tmp_path):
    path = tmp_path / 'latin.ini'
    path.write_bytes('[a]\nname = Grüße\n'.encode('latin-1'))
    params = {'dst': str(path), 'section': 'a', 'key': 'name', 'expected_value': 'Grüße'}
    _assert(_run(ValueMatches, **params), StatusEnum.ERROR)  # not UTF-8
    _assert(_run(ValueMatches, encoding='latin-1', **params), StatusEnum.SUCCESS)


def test_unknown_encoding_is_error(sample):
    _assert(_run(SectionExists, dst=sample, section='General', encoding='no-such-codec'), StatusEnum.ERROR)


# --- errors: missing, glob, undecodable -----------------------------------------------

ALL = [
    (SectionExists, {'section': 'a'}),
    (ContainsKey, {'section': 'a', 'key': 'b'}),
    (ValueMatches, {'section': 'a', 'key': 'b', 'expected_value': 'c'}),
    (ValueCount, {'section': 'a', 'key': 'b', 'expected_count': 1}),
]
IDS = ['section_exists', 'contains_key', 'value_matches', 'value_count']


@pytest.mark.parametrize(('test_class', 'params'), ALL, ids=IDS)
def test_missing_file_is_error(tmp_path, test_class, params):
    result = _run(test_class, dst=str(tmp_path / 'missing.ini'), **params)
    _assert(result, StatusEnum.ERROR)
    assert 'does not exist' in result.details[0]


@pytest.mark.parametrize(('test_class', 'params'), ALL, ids=IDS)
def test_glob_without_match_is_error(tmp_path, test_class, params):
    _assert(_run(test_class, dst=str(tmp_path / 'none*.ini'), **params), StatusEnum.ERROR)


@pytest.mark.parametrize(('test_class', 'params'), ALL, ids=IDS)
def test_ambiguous_glob_is_error(tmp_path, test_class, params):
    (tmp_path / 'a1.ini').write_text('[a]\nb = c\n')
    (tmp_path / 'a2.ini').write_text('[a]\nb = c\n')
    _assert(_run(test_class, dst=str(tmp_path / 'a*.ini'), **params), StatusEnum.ERROR)


@pytest.mark.parametrize(('test_class', 'params'), ALL, ids=IDS)
def test_undecodable_file_is_error(tmp_path, test_class, params):
    path = tmp_path / 'bad.ini'
    path.write_bytes(b'[a]\nb = \xff\xfe\xfa\x80\n')
    _assert(_run(test_class, dst=str(path), **params), StatusEnum.ERROR)


def test_directory_is_error(tmp_path):
    _assert(_run(SectionExists, dst=str(tmp_path), section='a'), StatusEnum.ERROR)


def test_glob_with_one_match(tmp_path):
    (tmp_path / 'only.ini').write_text('[a]\nb = c\n')
    _assert(_run(ContainsKey, dst=str(tmp_path / 'on*.ini'), section='a', key='b'), StatusEnum.SUCCESS)


# --- archive member -------------------------------------------------------------------


def test_archive_member(tmp_path):
    archive = tmp_path / 'a.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr('x.ini', '[General]\nport = 8080\n')

    result = _run(ValueMatches, dst=f'{archive}!/x.ini', section='General', key='port', expected_value='8080')

    _assert(result, StatusEnum.SUCCESS)
    assert any('archive member: x.ini' in str(d) for d in result.details)


def test_missing_archive_member_is_error(tmp_path):
    archive = tmp_path / 'a.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr('x.ini', '[General]\n')

    _assert(_run(SectionExists, dst=f'{archive}!/y.ini', section='General'), StatusEnum.ERROR)
