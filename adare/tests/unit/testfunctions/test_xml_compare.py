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
