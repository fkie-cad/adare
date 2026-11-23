"""`env extend` carries the post-setup step options (admin / allow_failure / timeout)."""

from pathlib import Path
from unittest.mock import patch

import attrs
import pytest
import yaml

from adare.backend.environment.extend import _installation_dict, _merged_installations
from adare.database.api.environment import EnvironmentDbApi
from adare.exceptions import DataStructuringError
from adare.types.environment import PostsetupInstallations, structure_postsetup_steps

pytestmark = pytest.mark.unit

_STEPS = [
    PostsetupInstallations(name='plain', command='a'),
    PostsetupInstallations(name='rooted', command='b', admin=True, allow_failure=True, timeout=12.5, cwd='/opt'),
]


@pytest.fixture
def global_db(tmp_path):
    with patch('adare.config.database.get_global_database_location', return_value=tmp_path / 'global.db'):
        yield


def test_a_database_row_round_trips_through_the_generated_yaml(global_db):
    with EnvironmentDbApi() as db:
        env = db.create_environment_version(
            name='src',
            description='',
            vm_id=None,
            vm_hash=None,
            tags=[],
            installations=[attrs.asdict(step) for step in _STEPS],
            environment_file=Path('/envs/src.yml'),
            sha256hash='1' * 64,
            hypervisor='qemu',
        )
        carried = [_installation_dict(row) for row in env.installations]

    reloaded = structure_postsetup_steps(yaml.safe_load(yaml.safe_dump(carried)))

    assert reloaded == _STEPS


def test_an_attrs_step_round_trips():
    carried = [_installation_dict(step) for step in _STEPS]

    assert structure_postsetup_steps(carried) == _STEPS


def test_install_flags_apply_to_every_install_entry():
    merged = _merged_installations(
        [], [('one', 'cmd-1'), ('two', 'cmd-2')], None, shell=True, cwd='/x', admin=True, allow_failure=True, timeout=9
    )

    assert structure_postsetup_steps(merged) == [
        PostsetupInstallations(
            name=name, command=f'cmd-{i}', cwd='/x', shell=True, admin=True, allow_failure=True, timeout=9.0
        )
        for i, name in enumerate(['one', 'two'], start=1)
    ]


def test_existing_steps_keep_their_options_when_extending():
    existing = [_installation_dict(step) for step in _STEPS]

    merged = _merged_installations(existing, [('new', 'c')], None, shell=False, cwd=None)

    assert structure_postsetup_steps(merged)[:2] == _STEPS
    assert [step['name'] for step in merged] == ['plain', 'rooted', 'new']


def test_from_file_steps_keep_their_options(tmp_path):
    from_file = tmp_path / 'steps.yml'
    from_file.write_text(yaml.safe_dump([attrs.asdict(step) for step in _STEPS]))

    merged = _merged_installations([], [], from_file, shell=False, cwd=None)

    assert structure_postsetup_steps(merged) == _STEPS


def test_a_from_file_with_an_unknown_key_is_a_clean_error(tmp_path):
    from_file = tmp_path / 'steps.yml'
    from_file.write_text(yaml.safe_dump([{'name': 'typo', 'command': 'x', 'allow_fail': True}]))

    with pytest.raises(DataStructuringError, match=r"unknown key 'allow_fail'"):
        _merged_installations([], [], from_file, shell=False, cwd=None)
