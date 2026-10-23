"""Without -e, a run resolves its environment by the name stored for the experiment."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from adare.backend.experiment import database as experiment_database
from adare.backend.experiment.exceptions import NoEnvironmentError

pytestmark = pytest.mark.unit


def _experiment(*environments):
    return SimpleNamespace(environments=list(environments))


def _call(experiment):
    with patch.object(experiment_database, 'ExperimentApi') as api:
        api.return_value.__enter__.return_value.get_experiment_by_project_and_name.return_value = experiment
        return experiment_database.get_experiment_environment_name(Path('/project'), 'exp')


def test_returns_the_environment_name_not_the_managed_file_stem():
    env = SimpleNamespace(name='ubuntu2204', file='/home/u/.adare/state/environments/ubuntu2204_1a2b3c4d.yml')

    assert _call(_experiment(env)) == 'ubuntu2204'


def test_deleted_environment_is_reported_not_crashed_on():
    with pytest.raises(NoEnvironmentError, match='no longer exists'):
        _call(_experiment(None))
