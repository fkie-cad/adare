"""Ordered comparisons in xml.element_text_matches / xml.attribute_matches and xml.values_compare.

test_xml.py is at its size budget. Runs on the guests' Python 3.10 too
(``make test-testfunctions-guest``).
"""

from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile
from adarelib.testset.yaml.customtags import YamlRegexString

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
xml_tf = import_module_from_pyfile(COLLECTIONS / 'xml' / 'xml.py')
ElementTextMatches = xml_tf.element_text_matches._test_class
AttributeMatches = xml_tf.attribute_matches._test_class
ValuesCompare = xml_tf.values_compare._test_class

SUCCESS, FAILED, ERROR = StatusEnum.SUCCESS, StatusEnum.FAILED, StatusEnum.ERROR

DOCUMENT = """<?xml version="1.0"?>
<list xmlns:x="urn:example:x">
  <entry ref="item-1" created="2026-03-01T10:00:00Z" modified="2026-03-01T10:00:04Z" visits="3"/>
  <entry ref="item-2" created="2026-03-02T08:00:00Z" modified="2026-03-01T23:00:00Z" visits="12"/>
  <stats>
    <opened>41</opened>
    <saved>42</saved>
    <title>Example</title>
    <stamp>1772359200</stamp>
    <x:when>2026-03-01T10:00:00Z</x:when>
  </stats>
</list>
"""
NS = {'x': 'urn:example:x'}


@pytest.fixture
def dst(tmp_path):
    path = tmp_path / 'list.xml'
    path.write_text(DOCUMENT, encoding='utf-8')
    return str(path)


def _run(test_class, function, **params):
    return test_class(name='t', parameter=function._parameter_class(**params)).test()


def _text(dst, xpath, expected_value, **params):
    return _run(
        ElementTextMatches, xml_tf.element_text_matches, dst=dst, xpath=xpath, expected_value=expected_value, **params
    )


def _attribute(dst, xpath, attribute, expected_value, **params):
    return _run(
        AttributeMatches,
        xml_tf.attribute_matches,
        dst=dst,
        xpath=xpath,
        attribute=attribute,
        expected_value=expected_value,
        **params,
    )


def _compare(dst, xpath, other_xpath, **params):
    return _run(ValuesCompare, xml_tf.values_compare, dst=dst, xpath=xpath, other_xpath=other_xpath, **params)


def _assert(result, status):
    assert result.status == status, f'{result.status}: {result.details}'


# --- element_text_matches / attribute_matches --------------------------------------------


@pytest.mark.parametrize(
    ('xpath', 'expected_value', 'params', 'status'),
    [
        ('./stats/saved', 40, {'comparison_type': 'greater'}, SUCCESS),
        ('./stats/saved', '42.0', {'value_type': 'number'}, SUCCESS),
        ('./stats/saved', 42, {'comparison_type': 'less'}, FAILED),
        ('./stats/stamp', '2026-03-01T10:00:00Z', {'timestamp_epoch': 1970}, SUCCESS),
        ('./stats/x:when', '2026-03-01T10:00:02Z', {'tolerance': 2, 'namespaces': NS}, SUCCESS),
        ('./stats/*', 41, {'comparison_type': 'greater_equal', 'value_type': 'number'}, ERROR),  # Example: no number
        ('./stats/title', 3, {'comparison_type': 'greater'}, ERROR),
        ('./stats/missing', 3, {'comparison_type': 'greater'}, FAILED),
        ('./stats/saved', '4', {'comparison_type': 'greater', 'regex_match': True}, ERROR),
    ],
)
def test_element_text_ordered(dst, xpath, expected_value, params, status):
    _assert(_text(dst, xpath, expected_value, **params), status)


def test_element_text_default_behaviour_unchanged(dst):
    _assert(_text(dst, './stats/saved', '42'), SUCCESS)
    _assert(_text(dst, './stats/saved', '42.0'), FAILED)
    _assert(_text(dst, './stats/title', 'EXAMPLE', case_sensitive=False), SUCCESS)


def test_element_text_ordered_wildcard_modes(dst):
    _assert(
        _text(dst, './stats/opened', 41, wildcard_mode='all', comparison_type='equals', value_type='number'), SUCCESS
    )
    _assert(_text(dst, '//entry', '', comparison_type='greater'), ERROR)  # empty text is no number


@pytest.mark.parametrize(
    ('expected_value', 'params', 'status'),
    [
        ('2026-03-01T09:00:00Z', {'comparison_type': 'greater'}, SUCCESS),
        ('2026-03-01T10:00:00Z', {'comparison_type': 'greater'}, FAILED),
        ('2026-03-01T10:00:00Z', {'comparison_type': 'greater_equal'}, SUCCESS),
        ('01.03.2026 11:00', {'comparison_type': 'equals', 'time_format': '%d.%m.%Y %H:%M'}, ERROR),  # value is ISO
        (YamlRegexString('^2026'), {'comparison_type': 'greater'}, ERROR),
        ('{{start}}', {'comparison_type': 'greater'}, ERROR),
    ],
)
def test_attribute_ordered(dst, expected_value, params, status):
    _assert(_attribute(dst, "//entry[@ref='item-1']", 'created', expected_value, **params), status)


def test_attribute_default_behaviour_unchanged(dst):
    _assert(_attribute(dst, "//entry[@ref='item-1']", 'visits', '3'), SUCCESS)
    _assert(_attribute(dst, "//entry[@ref='item-1']", 'visits', '^\\d$', regex_match=True), SUCCESS)
    _assert(_attribute(dst, "//entry[@ref='item-1']", 'visits', 'x'), FAILED)


# --- values_compare -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ('xpath', 'other_xpath', 'params', 'status'),
    [
        # A earlier than B: two attributes of one element
        (
            "//entry[@ref='item-1']",
            "//entry[@ref='item-1']",
            {'attribute': 'created', 'other_attribute': 'modified', 'comparison_type': 'less'},
            SUCCESS,
        ),
        (
            "//entry[@ref='item-2']",
            "//entry[@ref='item-2']",
            {'attribute': 'created', 'other_attribute': 'modified', 'comparison_type': 'less'},
            FAILED,
        ),
        # within 5 s
        (
            "//entry[@ref='item-1']",
            "//entry[@ref='item-1']",
            {'attribute': 'modified', 'other_attribute': 'created', 'tolerance': 5},
            SUCCESS,
        ),
        (
            "//entry[@ref='item-1']",
            "//entry[@ref='item-1']",
            {'attribute': 'modified', 'other_attribute': 'created', 'tolerance': 3},
            FAILED,
        ),
        # attributes of two elements
        (
            "//entry[@ref='item-2']",
            "//entry[@ref='item-1']",
            {'attribute': 'visits', 'other_attribute': 'visits', 'comparison_type': 'greater'},
            SUCCESS,
        ),
        # A = B + 1: element texts
        ('./stats/saved', './stats/opened', {'offset': 1}, SUCCESS),
        ('./stats/saved', './stats/opened', {'offset': 2}, FAILED),
        # text vs attribute, epoch seconds vs ISO
        ('./stats/stamp', "//entry[@ref='item-1']", {'other_attribute': 'created', 'timestamp_epoch': 1970}, SUCCESS),
        (
            './stats/x:when',
            './stats/stamp',
            {'namespaces': NS, 'timestamp_epoch': 1970, 'comparison_type': 'greater_equal'},
            SUCCESS,
        ),
    ],
)
def test_values_compare(dst, xpath, other_xpath, params, status):
    _assert(_compare(dst, xpath, other_xpath, **params), status)


@pytest.mark.parametrize(
    ('xpath', 'other_xpath', 'params'),
    [
        ('./stats/missing', './stats/saved', {}),
        ('./stats/saved', "//entry[@ref='item-1']", {'other_attribute': 'deleted'}),  # attribute missing
    ],
)
def test_values_compare_missing_side_fails(dst, xpath, other_xpath, params):
    _assert(_compare(dst, xpath, other_xpath, **params), FAILED)


@pytest.mark.parametrize(
    ('xpath', 'other_xpath', 'params'),
    [
        ('//entry', './stats/saved', {'attribute': 'visits'}),  # two elements with the attribute
        ('./stats/saved', './stats/*', {}),
        ('//entry', './stats/missing', {'attribute': 'visits'}),  # ambiguity wins over missing
    ],
)
def test_values_compare_ambiguous_side_is_error(dst, xpath, other_xpath, params):
    result = _compare(dst, xpath, other_xpath, **params)
    _assert(result, ERROR)
    assert 'exactly one value' in result.details[0]


@pytest.mark.parametrize(
    ('xpath', 'other_xpath', 'params'),
    [
        ('./stats/title', './stats/saved', {}),  # no number
        ("//entry[@ref='item-1']", './stats/saved', {}),  # empty element text
        ('./stats/saved', './stats/opened', {'comparison_type': 'earlier'}),
        ('./stats/saved', './stats/opened', {'timestamp_unit': 'ms'}),
        ('./stats/saved', 'stats/text()', {}),  # XPath outside ElementPath
    ],
)
def test_values_compare_errors(dst, xpath, other_xpath, params):
    _assert(_compare(dst, xpath, other_xpath, **params), ERROR)


def test_values_compare_missing_file_is_error(tmp_path):
    _assert(_compare(str(tmp_path / 'absent.xml'), './a', './b'), ERROR)


# --- round 2: value_decode, values_compare with other_dst --------------------------------


def _r2_run(function, **params):
    testfunction = getattr(xml_tf, function)
    return testfunction._test_class(name='t', parameter=testfunction._parameter_class(**params)).test()


@pytest.fixture
def r2_files(tmp_path):
    before, after = tmp_path / 'before.xml', tmp_path / 'after.xml'
    before.write_text('<state count="3"><saved>2026-03-01T10:00:00Z</saved><ref>a%2Fb</ref></state>')
    after.write_text('<state count="5"><saved>2026-03-01T10:05:00Z</saved><ref>eyJpZCI6IDl9</ref></state>')
    return str(before), str(after)


def test_values_compare_other_dst(r2_files, tmp_path):
    before, after = r2_files
    result = _r2_run(
        'values_compare',
        dst=after,
        xpath='.',
        attribute='count',
        other_xpath='.',
        other_attribute='count',
        other_dst=before,
        comparison_type='greater',
    )
    _assert(result, SUCCESS)
    assert any(before in d for d in result.details)
    _assert(
        _r2_run(
            'values_compare',
            dst=after,
            xpath='./saved',
            other_xpath='./saved',
            other_dst=before,
            comparison_type='less',
        ),
        FAILED,
    )
    missing = _r2_run(
        'values_compare', dst=after, xpath='./saved', other_xpath='./saved', other_dst=str(tmp_path / 'gone.xml')
    )
    _assert(missing, ERROR)
    assert 'does not exist' in missing.details[0]


def test_value_decode(r2_files):
    before, after = r2_files
    _assert(
        _r2_run(
            'element_text_matches',
            dst=after,
            xpath='./ref',
            expected_value='9',
            value_decode=['base64', 'json'],
            decoded_key_path='id',
        ),
        SUCCESS,
    )
    _assert(
        _r2_run(
            'element_text_matches',
            dst=before,
            xpath='./ref',
            expected_value='A/B',
            case_sensitive=False,
            value_decode='url',
        ),
        SUCCESS,
    )
    _assert(
        _r2_run('attribute_matches', dst=after, xpath='.', attribute='count', expected_value='5', value_decode='url'),
        SUCCESS,
    )
    _assert(
        _r2_run(
            'element_text_matches',
            dst=after,
            xpath='./ref',
            expected_value=8,
            comparison_type='greater',
            value_decode=['base64', 'json'],
            decoded_key_path='id',
        ),
        SUCCESS,
    )
    _assert(_r2_run('element_text_matches', dst=after, xpath='./saved', expected_value='x', value_decode='hex'), ERROR)
    _assert(
        _r2_run('attribute_matches', dst=after, xpath='.', attribute='count', expected_value='5', value_decode='json'),
        ERROR,
    )
    _assert(
        _r2_run(
            'values_compare', dst=after, xpath='./ref', other_xpath='./ref', other_dst=before, value_decode='base64'
        ),
        ERROR,
    )


# --- bug fixes: numeric expected_value, parameter validation, absence, prefixed namespaces -------

XpathResultMatches = xml_tf.xpath_result_matches._test_class
NamespaceMatches = xml_tf.namespace_matches._test_class

PREFIXED = """<?xml version="1.0"?>
<cp:core xmlns:cp="urn:example:cp" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:creator xmlns:extra="urn:example:extra">Alice</dc:creator>
</cp:core>
"""


@pytest.fixture
def prefixed(tmp_path):
    path = tmp_path / 'core.xml'
    path.write_text(PREFIXED, encoding='utf-8')
    return str(path)


def _xpath_result(dst, xpath, expected_value, **params):
    return _run(
        XpathResultMatches,
        xml_tf.xpath_result_matches,
        dst=dst,
        xpath=xpath,
        expected_value=expected_value,
        **params,
    )


def _namespaces(dst, **params):
    return _run(NamespaceMatches, xml_tf.namespace_matches, dst=dst, **params)


def test_unquoted_number_equals_element_text(dst):
    _assert(_text(dst, './stats/opened', 41), SUCCESS)
    _assert(_text(dst, './stats/opened', '41'), SUCCESS)
    _assert(_text(dst, './stats/opened', 42), FAILED)
    _assert(_text(dst, './stats/opened', 41.0), FAILED)  # text form of 41.0 is '41.0'
    _assert(_text(dst, './stats/stamp', 1772359200), SUCCESS)
    _assert(_text(dst, './stats/opened', 41, case_sensitive=False), SUCCESS)
    _assert(_text(dst, './stats/*', 41, wildcard_mode='any'), SUCCESS)


def test_unquoted_number_equals_attribute_text(dst):
    _assert(_attribute(dst, "//entry[@ref='item-1']", 'visits', 3), SUCCESS)
    _assert(_attribute(dst, "//entry[@ref='item-1']", 'visits', 4), FAILED)


def test_bool_expected_value_is_not_treated_as_number(dst):
    _assert(_text(dst, './stats/opened', True), FAILED)


@pytest.mark.parametrize('xpath', ['./stats/opened', './stats/*', './stats/missing'])
def test_invalid_wildcard_mode_is_an_error_for_any_match_count(dst, xpath):
    result = _text(dst, xpath, '41', wildcard_mode='some')
    _assert(result, ERROR)
    assert 'wildcard_mode' in ' '.join(result.details)


def test_valid_wildcard_modes_unaffected(dst):
    _assert(_text(dst, './stats/opened', '41', wildcard_mode='all'), SUCCESS)
    _assert(_text(dst, './stats/opened', '41', wildcard_mode='any'), SUCCESS)


def test_missing_expected_namespaces_is_an_error(dst):
    for mode in ('contains', 'exact'):
        result = _namespaces(dst, check_mode=mode)
        _assert(result, ERROR)
        assert 'expected_namespaces' in ' '.join(result.details)
        assert 'AttributeError' not in ' '.join(result.details)


def test_missing_element_never_passes_number_or_text(dst):
    for expected in (0, 0.0, '0'):
        result = _xpath_result(dst, './stats/printed', expected, result_type='number')
        _assert(result, FAILED)
        assert 'no element' in ' '.join(result.details)
    _assert(_xpath_result(dst, './stats/printed', '', result_type='text'), FAILED)
    _assert(_xpath_result(dst, './stats/printed', False, result_type='boolean'), SUCCESS)  # absence stays testable


def test_xpath_result_real_values_still_pass(tmp_path):
    path = tmp_path / 'v.xml'
    path.write_text('<r><zero>0</zero><empty></empty><n>42</n></r>', encoding='utf-8')
    _assert(_xpath_result(str(path), './zero', 0, result_type='number'), SUCCESS)
    _assert(_xpath_result(str(path), './n', 42, result_type='number'), SUCCESS)
    _assert(_xpath_result(str(path), './empty', '', result_type='text'), SUCCESS)
    _assert(_xpath_result(str(path), './empty', 0, result_type='number'), ERROR)  # empty text is no number


def test_prefixed_namespace_declarations_are_found(prefixed):
    _assert(_namespaces(prefixed, expected_namespaces={'dc': 'http://purl.org/dc/elements/1.1/'}), SUCCESS)
    _assert(
        _namespaces(prefixed, expected_namespaces={'cp': 'urn:example:cp', 'dc': 'http://purl.org/dc/elements/1.1/'}),
        SUCCESS,
    )
    # a declaration on a nested element is found as well
    _assert(_namespaces(prefixed, expected_namespaces={'extra': 'urn:example:extra'}), SUCCESS)
    _assert(_namespaces(prefixed, expected_namespaces={'dc': 'urn:wrong'}), FAILED)
    _assert(_namespaces(prefixed, expected_namespaces={'nope': 'urn:x'}), FAILED)


def test_prefixed_namespaces_exact_mode(prefixed):
    everything = {
        'cp': 'urn:example:cp',
        'dc': 'http://purl.org/dc/elements/1.1/',
        'extra': 'urn:example:extra',
    }
    _assert(_namespaces(prefixed, expected_namespaces=everything, check_mode='exact'), SUCCESS)
    _assert(_namespaces(prefixed, expected_namespaces={'cp': 'urn:example:cp'}, check_mode='exact'), FAILED)


def test_default_namespace_still_found_with_prefixed_ones(tmp_path):
    path = tmp_path / 's.xml'
    path.write_text('<svg xmlns="urn:svg" xmlns:xlink="urn:xlink"><a/></svg>', encoding='utf-8')
    _assert(_namespaces(str(path), expected_namespaces={'': 'urn:svg', 'xlink': 'urn:xlink'}), SUCCESS)


def test_namespaces_read_through_archive_dst(tmp_path):
    import zipfile

    archive_path = tmp_path / 'report.docx'
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.writestr('docProps/core.xml', PREFIXED)
    result = _namespaces(
        f'{archive_path}!/docProps/core.xml', expected_namespaces={'dc': 'http://purl.org/dc/elements/1.1/'}
    )
    _assert(result, SUCCESS)


def test_malformed_xml_is_an_error_for_namespaces(tmp_path):
    path = tmp_path / 'bad.xml'
    path.write_text('<a xmlns:x="urn:x"><b></a>', encoding='utf-8')
    _assert(_namespaces(str(path), expected_namespaces={'x': 'urn:x'}), ERROR)
