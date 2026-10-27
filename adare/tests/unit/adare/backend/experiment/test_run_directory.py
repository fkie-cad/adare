"""Run directories of runs started in the same second must not collide."""

from types import SimpleNamespace

import pytest

from adare.backend.experiment.directory import DiffRunDirectory, ExperimentRunDirectory

pytestmark = pytest.mark.unit


def test_runs_started_in_the_same_second_get_their_own_directory(tmp_path):
    project = SimpleNamespace(run=tmp_path / 'run', path=tmp_path)
    first = ExperimentRunDirectory(project, 'exp')
    second = ExperimentRunDirectory(project, 'exp')
    second.path = first.path  # same second

    first.create()
    second.create()

    assert second.path == first.path.with_name(first.path.name + '_2')
    assert second.log_directory == second.path / 'logs' and second.log_directory.is_dir()
    assert second.adare_log_file.parent == second.log_directory


def test_diff_runs_started_in_the_same_second_get_their_own_directory(tmp_path):
    project = SimpleNamespace(path=tmp_path)
    first = DiffRunDirectory(project, 'exp')
    second = DiffRunDirectory(project, 'exp')
    second.path = first.path

    first.create()
    second.create()

    assert second.path.name == first.path.name + '_2'
    assert second.diff_directory == second.path / 'artifacts' / 'diff' and second.diff_directory.is_dir()
