"""The metadata.yml skeleton of `adare experiment create` loads, and takes `add-env`.

The skeleton once wrote ``environments:`` followed only by comments, which YAML reads as
``null``; the strict loader then rejected it, so a fresh experiment could neither run with
``-e`` nor take ``add-env``. Now the skeleton writes a real empty list, and the loader
treats a present-but-empty key as absent, so experiments created with the old skeleton
keep working without editing.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from adare.backend.experiment import database as experiment_database
from adare.backend.experiment.commands import modify
from adare.backend.experiment.commands.create import experiment_create
from adare.backend.experiment.directory import ExperimentDirectory
from adare.backend.experiment.exceptions import NoEnvironmentError
from adare.cli.experiment import unlisted_environment_message
from adare.exceptions import DataStructuringError
from adare.parsers import parse_metadata_file

pytestmark = pytest.mark.unit

OLD_SKELETON = (
    '# Experiment metadata\n'
    'name: "exp"\n'
    'description: "Brief description"\n'
    '\n'
    'environments:\n'
    '  # Add environment names here, e.g.:\n'
    '  # - win11\n'
    '  # - ubuntu22\n'
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path / 'project'


def _metadata_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / 'metadata.yml'
    path.write_text(text, encoding='utf-8')
    return path


def test_fresh_skeleton_is_a_valid_empty_list(project):
    experiment_create(project, 'exp')
    raw = yaml.safe_load((project / 'experiments' / 'exp' / 'metadata.yml').read_text(encoding='utf-8'))

    assert raw['environments'] == []

    metadata = ExperimentDirectory(project, 'exp').load_metadata()
    assert metadata.environments == []
    assert metadata.tags == []
    assert metadata.usb == []
    assert metadata.disk == []
    assert metadata.smb is None


def test_loader_treats_null_environments_as_empty(tmp_path):
    metadata = parse_metadata_file(_metadata_file(tmp_path, OLD_SKELETON))

    assert metadata.environments == []


@pytest.mark.parametrize('key', ['environments', 'tags', 'usb', 'disk'])
def test_loader_treats_every_null_list_as_empty(tmp_path, key):
    metadata = parse_metadata_file(_metadata_file(tmp_path, f'description: d\n{key}:\n'))

    assert getattr(metadata, key) == []


def test_loader_keeps_optional_sections_unset_when_null(tmp_path):
    metadata = parse_metadata_file(_metadata_file(tmp_path, 'smb:\nnfs:\nocr:\n'))

    assert metadata.smb is None
    assert metadata.nfs is None
    assert metadata.ocr is None


def test_loader_still_rejects_a_wrong_type(tmp_path):
    with pytest.raises(DataStructuringError, match='environments'):
        parse_metadata_file(_metadata_file(tmp_path, 'environments: 7\n'))


def _add_env(project: Path, *names: str) -> None:
    """``adare experiment add-env exp <names>`` against a project that knows these environments."""
    environments = [SimpleNamespace(name=name) for name in names]
    with (
        patch('adare.database.api.environment.EnvironmentDbApi') as env_api,
        patch.object(modify, '_reload', return_value=True) as reload,
    ):
        env_api.return_value.__enter__.return_value.get_environments.return_value = environments
        modify.experiment_add_environments(project, 'exp', list(names))
    reload.assert_called_once_with(project, 'exp')


@pytest.mark.parametrize('skeleton', ['fresh', 'old'])
def test_skeleton_load_add_env_load_round_trip(project, skeleton):
    experiment_create(project, 'exp')
    directory = ExperimentDirectory(project, 'exp')
    if skeleton == 'old':
        directory.metadatafile.write_text(OLD_SKELETON, encoding='utf-8')
    assert directory.load_metadata().environments == []

    _add_env(project, 'win11')

    raw = yaml.safe_load(directory.metadatafile.read_text(encoding='utf-8'))
    assert raw['environments'] == ['win11']
    assert directory.load_metadata().environments == ['win11']

    _add_env(project, 'ubuntu22')

    assert directory.load_metadata().environments == ['ubuntu22', 'win11']


def test_run_without_environment_hints_at_add_env():
    experiment = SimpleNamespace(environments=[])
    with patch.object(experiment_database, 'ExperimentApi') as api:
        api.return_value.__enter__.return_value.get_experiment_by_project_and_name.return_value = experiment
        with pytest.raises(NoEnvironmentError, match='no environment') as excinfo:
            experiment_database.get_experiment_environment_name(Path('/project'), 'exp')

    assert any('adare experiment add-env exp' in hint for hint in excinfo.value.possible_solutions)


def test_run_with_explicit_environment_on_empty_list_names_add_env():
    message = unlisted_environment_message('exp', 'win11', SimpleNamespace(environments=[]))

    assert 'lists no environments' in message
    assert 'adare experiment add-env exp win11' in message


def test_run_with_explicit_unlisted_environment_keeps_the_plain_warning():
    message = unlisted_environment_message('exp', 'win11', SimpleNamespace(environments=[SimpleNamespace(name='x')]))

    assert message == 'WARNING: environment "win11" is not listed in exp/metadata.yml'
