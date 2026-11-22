"""Unknown keys in a ``tests:`` entry must be rejected, not silently dropped.

A typo such as ``paramter:`` under a test used to be accepted: the key vanished,
``parameter`` defaulted to ``{}``, and the run failed at the very last step with an
opaque ``NotAnAttrsClassError``. ``Test`` was not a strict class, and the strict
hooks of nested classes only fire when registered on the inner converter too.
"""

import pytest
import yaml

from adare.types.playbook import Playbook, parse_playbook

pytestmark = pytest.mark.unit


def _parse(tmp_path, **sections) -> Playbook:
    path = tmp_path / 'playbook.yml'
    path.write_text(yaml.safe_dump({'actions': [], **sections}))
    return parse_playbook(path)


class TestTestEntryStrictness:
    def test_typo_in_test_key_is_rejected_with_hint(self, tmp_path):
        entry = {'name': 'history', 'function': 'standard.file_exists', 'paramter': {'dst': '/tmp/x'}}
        with pytest.raises(ValueError) as exc:
            _parse(tmp_path, tests=[entry])
        message = str(exc.value)
        assert 'Unexpected field(s) in Test' in message
        assert 'paramter' in message
        assert 'did you mean: parameter' in message
        assert '$.tests[0]' in message

    def test_fully_specified_test_still_parses(self, tmp_path):
        entry = {
            'name': 'history',
            'function': 'standard.file_exists',
            'description': 'checks the file',
            'parameter': {'dst': '/tmp/x'},
            'variables': {'v': {'type': 'string', 'value': 'x'}},
            'expect_to_fail': True,
            'timeout': 30.0,
        }
        test = _parse(tmp_path, tests=[entry]).tests[0]
        assert test.parameter == {'dst': '/tmp/x'}
        assert test.expect_to_fail is True
        assert test.timeout == 30.0
        assert test.variables is not None

    def test_minimal_test_still_parses(self, tmp_path):
        test = _parse(tmp_path, tests=[{'name': 'history', 'function': 'standard.file_exists'}]).tests[0]
        assert test.parameter == {}


class TestArchiveDstMapping:
    """``dst: {archive, member}`` is checked at parse time (playbook validate and load)."""

    def test_valid_mapping_parses(self, tmp_path):
        dst = {'archive': '/home/u/backup.tar.gz', 'member': 'etc/app/config.json'}
        entry = {'name': 'cfg', 'function': 'json.value_matches', 'parameter': {'dst': dst}}
        assert _parse(tmp_path, tests=[entry]).tests[0].parameter['dst'] == dst

    @pytest.mark.parametrize(
        ('dst', 'hint'),
        [({'member': 'x'}, "needs 'archive'"), ({'archive': '/a.zip', 'format': 'zip'}, 'unknown key(s) format')],
    )
    def test_malformed_mapping_is_rejected(self, tmp_path, dst, hint):
        entry = {'name': 'cfg', 'function': 'json.value_matches', 'parameter': {'dst': dst}}
        with pytest.raises(ValueError, match='cfg') as exc:
            _parse(tmp_path, tests=[entry])
        assert hint in str(exc.value)
