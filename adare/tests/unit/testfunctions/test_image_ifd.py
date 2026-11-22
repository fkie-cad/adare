"""image.exif_value_matches / exif_value_count when a tag occurs in several IFDs.

A main-table name (``Make``) is looked up in IFD0 and the Exif IFD, a number (``0x010f``)
in IFD0, the Exif IFD and the GPS IFD, a GPS name only in the GPS IFD. Each IFD holding
the tag is one occurrence: ``*_matches`` passes when one occurrence matches, ``*_count``
counts every occurrence.
"""

from pathlib import Path

import pytest
from PIL import Image

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
image = import_module_from_pyfile(COLLECTIONS / 'image' / 'image.py')

MAKE = 0x010F
GPS_LATITUDE_REF = 0x0001  # GPSLatitudeRef in the GPS IFD, InteropIndex in the main table


def _run(function, **params):
    return function._test_class(name='t', parameter=function._parameter_class(**params)).test()


def _assert(result, status):
    assert result.status == status, f'expected {status.name}, got {result.status}: {result.details}'


@pytest.fixture
def multi_ifd(tmp_path):
    """A JPEG with tag 0x010f in IFD0 ('ACME'), the Exif IFD ('Other') and the GPS IFD ('Gps'),
    and tag 0x0001 in IFD0 ('R98') and the GPS IFD ('N')."""
    exif = Image.Exif()
    exif[MAKE] = 'ACME'
    exif[GPS_LATITUDE_REF] = 'R98'
    exif.get_ifd(image.EXIF_IFD)[MAKE] = 'Other'
    gps = exif.get_ifd(image.GPS_IFD)
    gps[MAKE] = 'Gps'
    gps[GPS_LATITUDE_REF] = 'N'
    path = tmp_path / 'multi.jpg'
    Image.new('RGB', (8, 8), 'blue').save(path, 'JPEG', exif=exif)
    return str(path)


def test_fixture_has_the_tag_in_every_ifd(multi_ifd):
    found, error = image._exif_values((multi_ifd, ''), multi_ifd, '0x010f')
    assert error is None
    assert found == [
        ('IFD0 tag 0x010f', 'ACME'),
        ('Exif IFD tag 0x010f', 'Other'),
        ('GPS IFD tag 0x010f', 'Gps'),
    ]


# --- exif_value_matches -------------------------------------------------------------------


@pytest.mark.parametrize('expected', ['ACME', 'Other'])
def test_name_matches_when_one_of_two_ifds_matches(multi_ifd, expected):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag='Make', expected_value=expected)

    _assert(result, StatusEnum.SUCCESS)
    assert result.details[0].startswith('EXIF tag Make: 1/2 occurrences match')
    assert result.details[1].endswith(f': {expected}')


def test_name_does_not_reach_the_gps_ifd(multi_ifd):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag='Make', expected_value='Gps')

    _assert(result, StatusEnum.FAILED)
    assert result.details[0].startswith('EXIF tag Make: 0/2 occurrences match')


@pytest.mark.parametrize('tag', ['0x010f', 271, '271'])
def test_number_reaches_all_three_ifds(multi_ifd, tag):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag=tag, expected_value='Gps')

    _assert(result, StatusEnum.SUCCESS)
    assert result.details[0].startswith(f'EXIF tag {tag}: 1/3 occurrences match')
    assert result.details[1] == 'GPS IFD tag 0x010f: Gps'


def test_no_occurrence_matches_fails_with_every_value(multi_ifd):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag='0x010f', expected_value='Nikon')

    _assert(result, StatusEnum.FAILED)
    assert result.details[0].startswith('EXIF tag 0x010f: 0/3 occurrences match')
    assert result.details[1] == 'expected: "Nikon"'
    for shown in ('IFD0 tag 0x010f: ACME', 'Exif IFD tag 0x010f: Other', 'GPS IFD tag 0x010f: Gps'):
        assert shown in result.details[2]


def test_regex_over_several_ifds(multi_ifd):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag='0x010f', expected_value='^Ot', regex_match=True)

    _assert(result, StatusEnum.SUCCESS)
    assert result.details[1] == 'Exif IFD tag 0x010f: Other'


def test_first_matching_occurrence_is_reported(multi_ifd):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag='0x010f', expected_value='.', regex_match=True)

    _assert(result, StatusEnum.SUCCESS)
    assert result.details[0].startswith('EXIF tag 0x010f: 3/3 occurrences match')
    assert result.details[1] == 'IFD0 tag 0x010f: ACME'


def test_invalid_regex_over_several_ifds_is_an_error(multi_ifd):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag='0x010f', expected_value='[x', regex_match=True)

    _assert(result, StatusEnum.ERROR)


def test_gps_name_and_number_of_the_same_id(multi_ifd):
    by_name = _run(image.exif_value_matches, dst=multi_ifd, tag='GPSLatitudeRef', expected_value='N')
    by_number = _run(image.exif_value_matches, dst=multi_ifd, tag=1, expected_value='R98')

    _assert(by_name, StatusEnum.SUCCESS)
    assert by_name.details == ['EXIF tag GPSLatitudeRef (GPS IFD tag 0x0001): value matches expected: N']
    _assert(by_number, StatusEnum.SUCCESS)
    assert by_number.details[0].startswith('EXIF tag 1: 1/2 occurrences match')


def test_single_occurrence_keeps_the_location_in_the_message(multi_ifd):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag='GPSLatitudeRef', expected_value='S')

    _assert(result, StatusEnum.FAILED)
    assert result.details[0].startswith('EXIF tag GPSLatitudeRef (GPS IFD tag 0x0001): ')


@pytest.mark.parametrize(
    ('expected', 'regex_match', 'status'),
    [
        ('.', True, StatusEnum.SUCCESS),
        ('^[A-Z]', True, StatusEnum.SUCCESS),
        ('ACME', False, StatusEnum.FAILED),
        ('^(ACME|Other)$', True, StatusEnum.FAILED),
    ],
)
def test_wildcard_mode_all_needs_every_ifd(multi_ifd, expected, regex_match, status):
    result = _run(
        image.exif_value_matches,
        dst=multi_ifd,
        tag='0x010f',
        expected_value=expected,
        regex_match=regex_match,
        wildcard_mode='all',
    )

    _assert(result, status)


def test_wildcard_mode_all_failure_lists_the_non_matching_ifds(multi_ifd):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag='0x010f', expected_value='ACME', wildcard_mode='all')

    _assert(result, StatusEnum.FAILED)
    assert result.details[0].startswith('EXIF tag 0x010f: 1/3 occurrences match')
    assert 'Exif IFD tag 0x010f: Other' in result.details[2]
    assert 'GPS IFD tag 0x010f: Gps' in result.details[2]


def test_invalid_wildcard_mode_is_an_error(multi_ifd):
    result = _run(image.exif_value_matches, dst=multi_ifd, tag='Make', expected_value='ACME', wildcard_mode='most')

    _assert(result, StatusEnum.ERROR)


# --- exif_value_count ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ('tag', 'count'),
    [('Make', 2), ('0x010f', 3), (271, 3), ('GPSLatitudeRef', 1), ('InteropIndex', 1), (1, 2)],
)
def test_each_ifd_counts_once(multi_ifd, tag, count):
    result = _run(image.exif_value_count, dst=multi_ifd, tag=tag, expected_count=count)

    _assert(result, StatusEnum.SUCCESS)
    assert result.details[0] == f'{count} occurrence(s) of EXIF tag {tag}'


def test_count_with_a_value_counts_matching_ifds(multi_ifd):
    result = _run(
        image.exif_value_count,
        dst=multi_ifd,
        tag='0x010f',
        expected_value='^(ACME|Gps)$',
        regex_match=True,
        expected_count=2,
    )

    _assert(result, StatusEnum.SUCCESS)
    assert result.details[0] == '2 occurrence(s) of EXIF tag 0x010f match "^(ACME|Gps)$"'


def test_count_mismatch_over_several_ifds_fails(multi_ifd):
    result = _run(image.exif_value_count, dst=multi_ifd, tag='Make', expected_count=3)

    _assert(result, StatusEnum.FAILED)
    assert result.details == ['2 occurrence(s) of EXIF tag Make', 'count 2 == 3 does not hold']


@pytest.mark.parametrize(
    ('comparison_type', 'expected_count'), [('greater', 2), ('less_equal', 3), ('greater_equal', 3)]
)
def test_count_comparisons_over_several_ifds(multi_ifd, comparison_type, expected_count):
    result = _run(
        image.exif_value_count,
        dst=multi_ifd,
        tag='0x010f',
        expected_count=expected_count,
        comparison_type=comparison_type,
    )

    _assert(result, StatusEnum.SUCCESS)


def test_count_zero_for_a_value_no_ifd_holds(multi_ifd):
    result = _run(image.exif_value_count, dst=multi_ifd, tag='0x010f', expected_value='Nikon', expected_count=0)

    _assert(result, StatusEnum.SUCCESS)
