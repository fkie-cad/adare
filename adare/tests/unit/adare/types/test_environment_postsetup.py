"""Post-setup steps in an environment file: new options, defaults, strict keys."""

import pytest
import yaml

from adare.exceptions import DataStructuringError
from adare.types.environment import (
    DEFAULT_POSTSETUP_TIMEOUT,
    PostsetupInstallations,
    parse_environment_file,
    structure_postsetup_steps,
)

pytestmark = pytest.mark.unit

_BASE = {'vm': 'disk.qcow2', 'os': {'os': 'Ubuntu', 'platform': 'linux', 'distribution': 'Jammy'}}


def _parse(tmp_path, steps):
    env_file = tmp_path / 'env.yml'
    env_file.write_text(yaml.safe_dump({**_BASE, 'postsetupinstallations': steps}))
    return parse_environment_file(env_file).postsetupinstallations


def test_new_options_default_to_off(tmp_path):
    (step,) = _parse(tmp_path, [{'name': 'a', 'command': 'x'}])

    assert (step.admin, step.allow_failure, step.timeout) == (False, False, None)
    assert DEFAULT_POSTSETUP_TIMEOUT == 600


def test_new_options_are_parsed(tmp_path):
    (step,) = _parse(tmp_path, [{'name': 'a', 'command': 'x', 'admin': True, 'allow_failure': True, 'timeout': 30}])

    assert (step.admin, step.allow_failure, step.timeout) == (True, True, 30.0)


def test_step_order_is_file_order(tmp_path):
    steps = _parse(tmp_path, [{'name': n, 'command': 'x'} for n in 'cab'])

    assert [step.name for step in steps] == ['c', 'a', 'b']


def test_an_environment_without_steps_parses(tmp_path):
    env_file = tmp_path / 'env.yml'
    env_file.write_text(yaml.safe_dump(_BASE))

    assert parse_environment_file(env_file).postsetupinstallations == []


def test_an_unknown_key_names_the_key_and_the_step(tmp_path):
    with pytest.raises(DataStructuringError) as error:
        _parse(
            tmp_path,
            [{'name': 'first', 'command': 'x'}, {'name': 'disable wizard', 'command': 'x', 'admn': True}],
        )

    message = str(error.value)
    assert "unknown key 'admn'" in message
    assert 'step 2 ("disable wizard")' in message


def test_several_unknown_keys_are_all_named():
    with pytest.raises(ValueError, match=r"unknown keys 'admn', 'timout'"):
        structure_postsetup_steps([{'name': 'a', 'command': 'x', 'admn': True, 'timout': 3}])


@pytest.mark.parametrize('timeout', [0, -5, -0.1])
def test_a_non_positive_timeout_is_rejected(tmp_path, timeout):
    with pytest.raises(DataStructuringError, match='timeout must be > 0'):
        _parse(tmp_path, [{'name': 'a', 'command': 'x', 'timeout': timeout}])


def test_a_non_positive_timeout_is_rejected_when_building_directly():
    with pytest.raises(ValueError, match='timeout must be > 0'):
        PostsetupInstallations(name='a', command='x', timeout=0)


def test_a_missing_command_names_the_step(tmp_path):
    with pytest.raises(DataStructuringError, match=r'step 1 \("a"\).*command'):
        _parse(tmp_path, [{'name': 'a'}])


def test_a_step_that_is_not_a_mapping_is_a_load_error(tmp_path):
    with pytest.raises(DataStructuringError, match='must be a mapping'):
        _parse(tmp_path, ['just a string'])
