"""Load-time check of literal zones in `timezone(...)` filters."""

import textwrap

import pytest

from adare.types.playbook import parse_playbook
from adare.types.playbook_templates import check_timestamp_filters
from adarelib.common.variables import ValidationError
from adarelib.testset.yaml.customtags import YamlTimestamp

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "template",
    [
        "{{ t | timezone('Europe/Berlin') }}",
        "{{ t | timezone('+02:00') | format('%Y') }}",
        "{{ t | timezone(zone_var) }}",  # not a literal: checked when the filter runs
        "{{ t | timezone(tz_name='UTC') }}",
        "no template",
        "{{ broken",  # syntax errors are reported where the template renders
    ],
)
def test_accepted(template):
    check_timestamp_filters({"actions": [{"command": {"command": template}}]})


@pytest.mark.parametrize(
    "template",
    ["{{ t | timezone('Europe/Berln') }}", "{{ t | timezone('+25:00') }}", "{{ t | timezone(tz_name='Nope/X') }}"],
)
def test_bad_literal_zone_raises_naming_the_template(template):
    with pytest.raises(ValidationError, match="Template"):
        check_timestamp_filters({"tests": [{"parameter": {"v": template}}]})


def test_custom_tag_fields_are_checked():
    tag = YamlTimestamp(timestamp="{{ t | timezone('Mars/Olympus') }}")
    with pytest.raises(ValidationError, match="Mars/Olympus"):
        check_timestamp_filters({"tests": [{"parameter": {"v": tag}}]})


def test_parse_playbook_rejects_a_bad_zone(tmp_path):
    path = tmp_path / "playbook.yml"
    path.write_text(
        textwrap.dedent(
            """\
            actions:
              - command:
                  command: "echo {{ t | timezone('Europe/Berln') }}"
            """
        )
    )
    with pytest.raises(ValueError, match="Europe/Berln"):
        parse_playbook(path)
