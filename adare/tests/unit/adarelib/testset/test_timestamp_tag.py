"""!timestamp tag: tolerance forms and the direct ``YamlTimestamp.compare``."""

import pytest
import yaml

from adarelib.testset.yaml.customloader import get_custom_loader
from adarelib.testset.yaml.customtags import YamlTimestamp

pytestmark = pytest.mark.unit

UNIX_S = 1704164645  # 2024-01-02T03:04:05Z
FILETIME = (UNIX_S + 11644473600) * 10_000_000


def _load(text: str):
    return yaml.load(text, Loader=get_custom_loader())


class TestTolerance:
    @pytest.mark.parametrize(
        ('tolerance', 'bounds'),
        [('3', [-3, 3]), ('-3', [-3, 3]), ('1.5', [-1.5, 1.5]), ('[-5, 10]', [-5, 10]), ('[10, -5]', [-5, 10])],
    )
    def test_number_or_two_number_list(self, tolerance, bounds):
        tag = _load(f"!timestamp {{timestamp: '{{{{ t }}}}', tolerance: {tolerance}}}")
        assert tag.metadata['tolerance'] == bounds

    def test_list_reaches_the_tag_filled(self):
        """The mapping is built deep: a list value is complete when the tag is constructed."""
        tag = _load("!timestamp {timestamp: '{{ t }}', tolerance: [-5, 10]}")
        assert tag.tolerance == [-5, 10]

    @pytest.mark.parametrize('tolerance', ['[1]', '[1, 2, 3]', '[a, 1]', 'true', 'soon', '{a: 1}'])
    def test_other_values_are_load_errors(self, tolerance):
        with pytest.raises(ValueError, match='tolerance must be a number or a list of two numbers'):
            _load(f"!timestamp {{timestamp: '{{{{ t }}}}', tolerance: {tolerance}}}")


class TestDirectCompare:
    def test_string_within_default_second(self):
        tag = YamlTimestamp(timestamp='2024-01-02 03:04:05')
        assert tag.compare('2024-01-02 03:04:05.5').success
        assert not tag.compare('2024-01-02 03:04:07').success

    def test_list_tolerance_is_asymmetric(self):
        # bounds are for expected minus actual: [-5, 10] allows actual from 10 s before to 5 s after
        tag = YamlTimestamp(timestamp='2024-01-02 03:04:05', tolerance=[-5, 10])
        assert tag.compare('2024-01-02 03:03:56').success  # 9 s before
        assert tag.compare('2024-01-02 03:04:09').success  # 4 s after
        assert not tag.compare('2024-01-02 03:04:12').success  # 7 s after

    def test_numeric_entry_with_epoch_and_unit(self):
        tag = YamlTimestamp(timestamp='2024-01-02 03:04:05', tolerance=1, epoch=1601, unit='100ns')
        assert tag.compare(str(FILETIME)).success
        assert not tag.compare(str(FILETIME + 50_000_000)).success
        assert not tag.compare('not a number').success

    def test_format_for_the_expected_side_parses_the_expected_value(self):
        tag = YamlTimestamp(timestamp='02.01.2024 03:04:05', timestamp_format_comparison='%d.%m.%Y %H:%M:%S')
        assert tag.compare('2024-01-02T03:04:05').success

    def test_zone_mismatch_is_a_failed_comparison_not_a_crash(self):
        tag = YamlTimestamp(timestamp='2024-01-02T03:04:05+00:00')
        result = tag.compare('2024-01-02 03:04:05')
        assert not result.success
