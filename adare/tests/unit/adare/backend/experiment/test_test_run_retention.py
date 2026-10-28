"""Automatic test-run retention: keep the ``ADARE_TEST_RUNS_KEEP`` newest test runs per experiment.

``retain_test_runs`` is exercised against a real (temporary) project and global
database; the run.py hook is pinned by reading the source, like
``test_run_signal_handling.py`` does, so it cannot drift from what runs.
"""

import ast
import inspect
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from adare.backend.experiment import run_prune
from adare.backend.experiment.run_folders import RunReferencesUnavailableError
from adare.backend.experiment.run_prune import (
    TEST_RUNS_KEEP_SETTING,
    RetentionResult,
    apply_test_run_retention,
    retain_test_runs,
)
from adare.config import settings
from adare.database.api.devmode import DevModeApi
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.experiment import ExperimentApi
from adare.database.models.devsession import DevSession
from adare.database.models.global_models import Project
from adare.database.models.project_models import Experiment, ExperimentRun
from adare.database.reference_manager import reference_manager
from adarelib.constants import StatusEnum

pytestmark = pytest.mark.unit

#: Naive UTC, like the database stores it.
BASE = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
OLD = time.time() - 3 * 86400


def make_run(project: Path, experiment: str, name: str, *, when: float = OLD) -> Path:
    """A run folder with logs/adare.log, last changed at ``when``."""
    folder = project / 'run' / experiment / name
    (folder / 'logs').mkdir(parents=True)
    (folder / 'logs' / 'adare.log').write_text('x' * 5000)
    for path in (folder / 'logs' / 'adare.log', folder / 'logs', folder):
        os.utime(path, (when, when))
    return folder


@pytest.fixture
def project(tmp_path):
    db_file = tmp_path / 'global.db'
    root = tmp_path / 'project'
    for name in ('exp', 'other'):
        (root / 'experiments' / name).mkdir(parents=True)
    (root / 'run').mkdir()
    with (
        patch('adare.config.database.get_global_database_location', return_value=db_file),
        patch('adare.config.database.get_database_location', return_value=db_file),
        patch.object(reference_manager, '_global_api', None),
        patch.object(reference_manager, '_cache', {}),
        patch.object(reference_manager, '_cache_timestamps', {}),
    ):
        with EnvironmentDbApi() as db:
            db._session.add(Project(name='project', path=str(root)))
        yield root


def _experiment(project: Path, name: str = 'exp') -> str:
    with ExperimentApi(project) as api:
        experiment = Experiment(
            name=name, sha256='0' * 64, sha256_playbook='1' * 64, sha256_metadata='2' * 64, environment_ids=[]
        )
        api._session.add(experiment)
        api._session.flush()
        return experiment.id


def _run(
    project: Path,
    experiment_id: str,
    path: Path | None,
    *,
    fake: bool = True,
    status: StatusEnum = StatusEnum.FINISHED,
    start: datetime | None = BASE,
) -> str:
    with ExperimentApi(project) as api:
        run = ExperimentRun(
            experiment_id=experiment_id, path=str(path) if path else None, fake=fake, status=status, start_time=start
        )
        api._session.add(run)
        api._session.flush()
        return run.id


def _test_run(project: Path, experiment_id: str, day: int, *, experiment: str = 'exp', **kwargs) -> tuple[str, Path]:
    """An old, finished fake run with a folder; a higher ``day`` started later."""
    folder = make_run(project, experiment, f'2025-01-{day:02d}_00-00-00')
    return _run(project, experiment_id, folder, start=BASE + timedelta(days=day), **kwargs), folder


def _current_run(project: Path, experiment_id: str) -> tuple[str, Path]:
    """The run that just finished: started minutes ago, folder written just now."""
    folder = make_run(project, 'exp', '2025-02-01_00-00-00', when=time.time())
    started = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    return _run(project, experiment_id, folder, start=started), folder


def _run_ids(project: Path) -> set[str]:
    with ExperimentApi(project) as api:
        return {run.id for run in api._session.query(ExperimentRun).all()}


def _dev_session(project: Path, run_dir: Path) -> None:
    with DevModeApi() as db:
        db._session.add(
            DevSession(
                project_path=str(project),
                experiment_name='exp',
                environment_name='env',
                vm_name='vm',
                run_directory_path=str(run_dir),
                status='stopped',
            )
        )


# ------------------------------------------------------------------ ranking


def test_keeps_the_newest_runs_counting_the_current_one(project):
    experiment_id = _experiment(project)
    older = [_test_run(project, experiment_id, day) for day in range(1, 6)]
    current_id, current_folder = _current_run(project, experiment_id)

    result = retain_test_runs(project, 'exp', 3, current_id)

    # keep=3: the current run plus the two newest older ones (days 5 and 4).
    kept = {current_id, older[4][0], older[3][0]}
    assert _run_ids(project) == kept
    assert result.removed == 3
    assert result.folders_removed == 3
    assert result.bytes_freed > 0
    for run_id, folder in older:
        assert folder.exists() == (run_id in kept)
    assert current_folder.exists()


def test_nothing_removed_within_the_limit(project):
    experiment_id = _experiment(project)
    older = [_test_run(project, experiment_id, day) for day in range(1, 4)]
    current_id, _ = _current_run(project, experiment_id)

    assert retain_test_runs(project, 'exp', 4, current_id) == RetentionResult()
    assert _run_ids(project) == {current_id, *(run_id for run_id, _ in older)}


def test_ranking_falls_back_to_created_at(project):
    experiment_id = _experiment(project)
    undated_id = _run(project, experiment_id, None, start=None)
    with ExperimentApi(project) as api:
        api._session.get(ExperimentRun, undated_id).created_at = BASE + timedelta(days=9)
    dated_id, _ = _test_run(project, experiment_id, 1)
    current_id, _ = _current_run(project, experiment_id)

    retain_test_runs(project, 'exp', 2, current_id)

    # created_at (day 9) makes the undated run newer than the one started on day 1.
    assert _run_ids(project) == {current_id, undated_id}
    assert dated_id not in _run_ids(project)


def test_keep_zero_removes_every_older_eligible_run_but_not_the_current_one(project):
    experiment_id = _experiment(project)
    older = [_test_run(project, experiment_id, day) for day in range(1, 4)]
    rowonly_id = _run(project, experiment_id, None, status=StatusEnum.INTERRUPTED)
    current_id, current_folder = _current_run(project, experiment_id)

    result = retain_test_runs(project, 'exp', 0, current_id)

    assert _run_ids(project) == {current_id}
    assert result.removed == 4  # three with a folder, one without
    assert result.folders_removed == 3
    assert current_folder.exists()
    assert not any(folder.exists() for _, folder in older)
    assert rowonly_id not in _run_ids(project)


def test_keep_one_equals_keep_zero_with_a_current_run(project):
    experiment_id = _experiment(project)
    _test_run(project, experiment_id, 1)
    current_id, _ = _current_run(project, experiment_id)

    assert retain_test_runs(project, 'exp', 1, current_id).removed == 1
    assert _run_ids(project) == {current_id}


def test_without_a_current_run_keep_zero_removes_all_candidates(project):
    experiment_id = _experiment(project)
    for day in range(1, 3):
        _test_run(project, experiment_id, day)

    assert retain_test_runs(project, 'exp', 0, None).removed == 2
    assert _run_ids(project) == set()


# ------------------------------------------------------------ never touched


def test_never_touches_protected_runs(project):
    experiment_id = _experiment(project)
    other_id = _experiment(project, 'other')
    # The current run is the OLDEST here: it is excluded by id, not by its rank.
    current_id = _run(project, experiment_id, None, start=BASE)
    fresh_folder = make_run(project, 'exp', '2025-01-10_00-00-00')
    fresh_id = _run(project, experiment_id, fresh_folder, start=datetime.now(UTC).replace(tzinfo=None))
    running_id, running_folder = _test_run(project, experiment_id, 2, status=StatusEnum.RUNNING)
    pending_id, _ = _test_run(project, experiment_id, 3, status=StatusEnum.PENDING)
    no_status_id = _run(project, experiment_id, None, status=None)
    dev_id, dev_folder = _test_run(project, experiment_id, 4)
    _dev_session(project, dev_folder)
    real_id, real_folder = _test_run(project, experiment_id, 5, fake=False)
    foreign_id, foreign_folder = _test_run(project, other_id, 6, experiment='other')
    # A run whose folder changed within the hour fails check_run_folder: row and folder stay.
    busy_folder = make_run(project, 'exp', '2025-01-07_00-00-00', when=time.time())
    busy_id = _run(project, experiment_id, busy_folder, start=BASE + timedelta(days=7))
    doomed_id, doomed_folder = _test_run(project, experiment_id, 8)

    result = retain_test_runs(project, 'exp', 0, current_id)

    assert result.removed == 1
    assert _run_ids(project) == {
        current_id,
        fresh_id,
        running_id,
        pending_id,
        no_status_id,
        dev_id,
        real_id,
        foreign_id,
        busy_id,
    }
    for folder in (fresh_folder, running_folder, dev_folder, real_folder, foreign_folder, busy_folder):
        assert folder.exists()
    assert not doomed_folder.exists()
    assert doomed_id not in _run_ids(project)


def test_protected_runs_take_no_place(project):
    """Unfinished and dev-session runs are kept anyway; they do not use up ``keep``."""
    experiment_id = _experiment(project)
    _test_run(project, experiment_id, 9, status=StatusEnum.RUNNING)
    dev_id, dev_folder = _test_run(project, experiment_id, 8)
    _dev_session(project, dev_folder)
    newest_id, _ = _test_run(project, experiment_id, 7)
    oldest_id, _ = _test_run(project, experiment_id, 1)
    current_id, _ = _current_run(project, experiment_id)

    retain_test_runs(project, 'exp', 2, current_id)

    remaining = _run_ids(project)
    assert newest_id in remaining and dev_id in remaining
    assert oldest_id not in remaining


# ---------------------------------------------------------------- the hook


def test_hook_uses_the_setting_and_returns_a_line(project, monkeypatch):
    experiment_id = _experiment(project)
    for day in range(1, 4):
        _test_run(project, experiment_id, day)
    current_id, _ = _current_run(project, experiment_id)
    monkeypatch.setenv(TEST_RUNS_KEEP_SETTING, '2')

    message = apply_test_run_retention(project, 'exp', current_id)

    assert message is not None
    assert message.startswith('removed 2 older test runs (')
    assert 'ADARE_TEST_RUNS_KEEP=2' in message
    assert len(_run_ids(project)) == 2


def test_hook_is_silent_when_nothing_was_removed(project):
    experiment_id = _experiment(project)
    _test_run(project, experiment_id, 1)
    current_id, _ = _current_run(project, experiment_id)

    # Default 10.
    assert apply_test_run_retention(project, 'exp', current_id) is None
    assert len(_run_ids(project)) == 2


@pytest.mark.parametrize(
    'error',
    [
        RunReferencesUnavailableError('the dev sessions could not be read'),
        OperationalError('DELETE FROM experiment_run', {}, Exception('database is locked')),
        PermissionError(13, 'Permission denied'),
    ],
    ids=['references', 'sqlalchemy', 'oserror'],
)
def test_hook_never_raises(tmp_path, caplog, error):
    with patch.object(run_prune, 'retain_test_runs', side_effect=error), caplog.at_level(logging.WARNING):
        assert apply_test_run_retention(tmp_path, 'exp', 'run-id') is None
    assert 'older test runs of exp kept' in caplog.text


def test_hook_passes_the_configured_keep(tmp_path, monkeypatch):
    monkeypatch.setenv(TEST_RUNS_KEEP_SETTING, '0')
    with patch.object(run_prune, 'retain_test_runs', return_value=RetentionResult()) as retain:
        apply_test_run_retention(tmp_path, 'exp', 'run-id')
    retain.assert_called_once_with(tmp_path, 'exp', 0, 'run-id')


# ------------------------------------------------------------------ setting


def test_setting_defaults_to_ten_and_accepts_zero():
    assert settings.SETTINGS[TEST_RUNS_KEEP_SETTING].default == 10
    assert settings.parse(TEST_RUNS_KEEP_SETTING, '0') == 0
    with pytest.raises(ValueError):
        settings.parse(TEST_RUNS_KEEP_SETTING, '-1')
    with pytest.raises(ValueError):
        settings.parse(TEST_RUNS_KEEP_SETTING, '2.5')


# ------------------------------------------------------------ run.py wiring


class TestRunWiring:
    """Reads run.py itself: retention runs after test-mode runs only, never in dev mode."""

    GUARD = ast.dump(ast.parse('test and not experiment_run_context.config.dev_mode', mode='eval').body)

    @classmethod
    def _is_guard(cls, node: ast.If) -> bool:
        return ast.dump(node.test) == cls.GUARD

    @staticmethod
    def _retention_ifs() -> list[ast.If]:
        from adare.backend.experiment import run as run_module

        tree = ast.parse(inspect.getsource(run_module.experiment_run))
        return [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If) and 'apply_test_run_retention' in ast.unparse(node)
        ]

    def test_called_exactly_once_under_the_test_and_not_dev_mode_guard(self):
        from adare.backend.experiment import run as run_module

        source = inspect.getsource(run_module.experiment_run)
        assert source.count('apply_test_run_retention,') == 1
        assert any(self._is_guard(node) for node in self._retention_ifs())

    def test_runs_off_the_event_loop_with_the_current_run(self):
        guard = next(node for node in self._retention_ifs() if self._is_guard(node))
        body = ast.unparse(guard)
        assert 'await asyncio.to_thread(' in body
        assert 'experiment_run_context.experiment_run_ulid' in body
        assert 'not disable_printing' in body

    def test_runs_after_the_forensic_report(self):
        from adare.backend.experiment import run as run_module

        source = inspect.getsource(run_module.experiment_run)
        assert source.index('generate_forensic_report_for_run') < source.index('apply_test_run_retention')
