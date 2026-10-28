"""runs remove / DELETE /api/runs / runs prune / experiment clean+remove delete run folders safely."""

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.backend.experiment.commands.manage import experiment_clean, experiment_remove
from adare.core.dto.show import RunPruneRequest, RunRemoveRequest
from adare.database.api.devmode import DevModeApi
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.experiment import ExperimentApi
from adare.database.models.devsession import DevSession
from adare.database.models.global_models import Project
from adare.database.models.project_models import Experiment, ExperimentRun
from adare.database.reference_manager import reference_manager
from adare.services.show_service import ShowService
from adarelib.constants import StatusEnum

pytestmark = pytest.mark.unit

LONG_AGO = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
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
    (root / 'experiments' / 'exp').mkdir(parents=True)
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
    path: str | None,
    *,
    fake: bool = False,
    status: StatusEnum = StatusEnum.FINISHED,
    start: datetime | None = LONG_AGO,
) -> str:
    with ExperimentApi(project) as api:
        run = ExperimentRun(experiment_id=experiment_id, path=path, fake=fake, status=status, start_time=start)
        api._session.add(run)
        api._session.flush()
        return run.id


def _run_ids(project: Path) -> set[str]:
    with ExperimentApi(project) as api:
        return {run.id for run in api._session.query(ExperimentRun).all()}


# ---------------------------------------------------------------- runs remove


def test_runs_remove_deletes_row_and_folder(project):
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    run_id = _run(project, _experiment(project), str(folder))

    result = ShowService().remove_run(RunRemoveRequest(ulid=run_id, project_path=project))

    assert result.success
    assert result.data.folder_removed
    assert not folder.exists()
    assert run_id not in _run_ids(project)


def test_runs_remove_keep_files_keeps_the_folder(project):
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    run_id = _run(project, _experiment(project), str(folder))

    result = ShowService().remove_run(RunRemoveRequest(ulid=run_id, project_path=project, keep_files=True))

    assert result.success
    assert not result.data.folder_removed
    assert folder.exists()
    assert run_id not in _run_ids(project)


def test_runs_remove_moved_project_maps_old_path(project):
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    run_id = _run(project, _experiment(project), '/old/location/project/run/exp/2025-01-01_00-00-00')

    result = ShowService().remove_run(RunRemoveRequest(ulid=run_id, project_path=project))

    assert result.data.folder_removed
    assert not folder.exists()


def test_runs_remove_refused_folder_does_not_fail_the_row_delete(project, tmp_path):
    outside = make_run(tmp_path / 'elsewhere', 'exp', '2025-01-01_00-00-00')
    (project / 'run' / 'exp').mkdir()
    (project / 'run' / 'exp' / '2025-01-01_00-00-00').symlink_to(outside, target_is_directory=True)
    run_id = _run(project, _experiment(project), str(outside))

    result = ShowService().remove_run(RunRemoveRequest(ulid=run_id, project_path=project))

    assert result.success
    assert not result.data.folder_removed
    assert result.data.folder_note.startswith('folder kept: ')
    assert outside.exists()
    assert run_id not in _run_ids(project)


def test_web_delete_removes_row_and_folder(project):
    from adare.webapi.routes.runs import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    experiment_id = _experiment(project)
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    kept = make_run(project, 'exp', '2025-01-02_00-00-00')
    run_id = _run(project, experiment_id, str(folder))
    kept_id = _run(project, experiment_id, str(kept))

    response = client.delete(f'/api/runs/{run_id}', params={'project_path': str(project)})
    assert response.status_code == 200
    assert response.json()['success']
    assert not folder.exists()

    response = client.delete(f'/api/runs/{kept_id}', params={'project_path': str(project), 'keep_files': 'true'})
    assert response.json()['success']
    assert kept.exists()
    assert _run_ids(project) == set()


# ---------------------------------------------------------------- runs prune


def _prune_fixture(project: Path) -> dict[str, Path | str]:
    experiment_id = _experiment(project)
    orphan = make_run(project, 'exp', '2025-01-01_00-00-00')
    real = make_run(project, 'exp', '2025-01-02_00-00-00')
    fake_done = make_run(project, 'exp', '2025-01-03_00-00-00')
    fake_running = make_run(project, 'exp', '2025-01-04_00-00-00')
    user = make_run(project, '_p4_sample', '2025-01-05_00-00-00')
    fresh_orphan = make_run(project, 'exp', '2025-01-06_00-00-00', when=time.time())
    dev = make_run(project, 'exp', '2025-01-07_00-00-00')
    with DevModeApi() as db:
        db._session.add(
            DevSession(
                project_path=str(project),
                experiment_name='exp',
                environment_name='env',
                vm_name='vm',
                run_directory_path=str(dev),
                status='stopped',
            )
        )
    return {
        'orphan': orphan,
        'real': real,
        'fake_done': fake_done,
        'fake_running': fake_running,
        'user': user,
        'fresh_orphan': fresh_orphan,
        'dev': dev,
        'real_id': _run(project, experiment_id, str(real)),
        'fake_done_id': _run(project, experiment_id, str(fake_done), fake=True, status=StatusEnum.FAILED),
        'fake_running_id': _run(project, experiment_id, str(fake_running), fake=True, status=StatusEnum.RUNNING),
        'fake_rowonly_id': _run(project, experiment_id, None, fake=True, status=StatusEnum.INTERRUPTED),
        'fake_fresh_id': _run(project, experiment_id, None, fake=True, start=datetime.now(UTC).replace(tzinfo=None)),
    }


def test_prune_dry_run_lists_orphans_and_deletes_nothing(project):
    f = _prune_fixture(project)
    before = _run_ids(project)

    result = ShowService().prune_runs(RunPruneRequest(project_path=project))

    assert result.success
    data = result.data
    assert data.dry_run
    assert [(e.kind, e.folder) for e in data.entries] == [('orphan', str(f['orphan']))]
    assert data.total_bytes == data.entries[0].size_bytes > 0
    assert all(Path(p).exists() for k, p in f.items() if not k.endswith('_id'))
    assert _run_ids(project) == before


def test_prune_yes_deletes_exactly_the_listed_set(project):
    f = _prune_fixture(project)
    listed = ShowService().prune_runs(RunPruneRequest(project_path=project)).data.entries

    result = ShowService().prune_runs(RunPruneRequest(project_path=project, execute=True))

    assert [e.folder for e in result.data.entries] == [e.folder for e in listed]
    assert all(e.removed and e.folder_removed for e in result.data.entries)
    assert not f['orphan'].exists()
    for kept in ('real', 'fake_done', 'fake_running', 'user', 'fresh_orphan', 'dev'):
        assert f[kept].exists(), kept
    assert result.data.rows_deleted == 0
    assert len(_run_ids(project)) == 5


def test_prune_fake_includes_non_running_fake_runs(project):
    f = _prune_fixture(project)

    dry = ShowService().prune_runs(RunPruneRequest(project_path=project, fake=True)).data
    fake_ids = {e.run_ulid for e in dry.entries if e.kind == 'fake'}
    assert fake_ids == {f['fake_done_id'], f['fake_rowonly_id']}

    result = ShowService().prune_runs(RunPruneRequest(project_path=project, fake=True, execute=True)).data

    assert result.rows_deleted == 2
    assert not f['orphan'].exists()
    assert not f['fake_done'].exists()
    assert f['fake_running'].exists()
    assert f['real'].exists()
    assert f['user'].exists()
    assert _run_ids(project) == {f['real_id'], f['fake_running_id'], f['fake_fresh_id']}


def test_prune_older_than_filters_by_age(project):
    _experiment(project)
    make_run(project, 'exp', '2025-01-01_00-00-00', when=time.time() - 2 * 86400)
    week_old = make_run(project, 'exp', '2025-01-02_00-00-00', when=time.time() - 8 * 86400)

    data = ShowService().prune_runs(RunPruneRequest(project_path=project, older_than_days=7)).data

    assert [e.folder for e in data.entries] == [str(week_old)]


# ------------------------------------------------------- experiment clean/remove


def test_experiment_clean_deletes_fake_run_folders(project):
    experiment_id = _experiment(project)
    fake = make_run(project, 'exp', '2025-01-01_00-00-00')
    real = make_run(project, 'exp', '2025-01-02_00-00-00')
    _run(project, experiment_id, str(fake), fake=True)
    real_id = _run(project, experiment_id, str(real))

    assert experiment_clean(project, 'exp') == 1

    assert not fake.exists()
    assert real.exists()
    assert _run_ids(project) == {real_id}


def test_experiment_remove_deletes_run_folders(project):
    experiment_id = _experiment(project)
    folders = [make_run(project, 'exp', f'2025-01-0{i}_00-00-00') for i in (1, 2)]
    for folder in folders:
        _run(project, experiment_id, str(folder))
    user = project / 'run' / 'exp' / 'my_notes'
    user.mkdir()

    experiment_remove(project, 'exp', force=True)

    assert not any(folder.exists() for folder in folders)
    assert user.exists()
    assert not (project / 'experiments' / 'exp').exists()
    assert _run_ids(project) == set()


def test_experiment_remove_keep_files_keeps_run_folders(project):
    experiment_id = _experiment(project)
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    _run(project, experiment_id, str(folder))

    experiment_remove(project, 'exp', force=True, keep_files=True)

    assert folder.exists()
    assert _run_ids(project) == set()


# ------------------------------------------------- runs that never got a path


def _orphans(project: Path) -> list[str]:
    result = ShowService().prune_runs(RunPruneRequest(project_path=project))
    assert result.success, result.error
    return [e.folder for e in result.data.entries if e.kind == 'orphan']


@pytest.mark.parametrize(
    'start',
    [
        datetime(2025, 1, 1, 0, 0, 40),  # folder created right after the run started (both UTC)
        datetime(2025, 1, 1, 1, 30),  # VM preparation took long
        datetime(2024, 12, 31, 14, 0),  # local-time start of an old run, 10 h off UTC
    ],
)
def test_prune_keeps_the_folder_of_a_run_that_failed_before_it_got_a_path(project, start):
    experiment_id = _experiment(project)
    kept = make_run(project, 'exp', '2025-01-01_00-00-00')
    orphan = make_run(project, 'exp', '2025-01-05_00-00-00')
    _run(project, experiment_id, None, status=StatusEnum.FAILED, start=start)

    assert _orphans(project) == [str(orphan)]
    ShowService().prune_runs(RunPruneRequest(project_path=project, execute=True))
    assert kept.exists()
    assert not orphan.exists()


def test_prune_pathless_run_falls_back_to_created_at_and_ignores_other_experiments(project):
    experiment_id = _experiment(project)
    _experiment(project, 'other')
    near = make_run(project, 'exp', '2025-01-01_00-00-00')
    other = make_run(project, 'other', '2025-01-01_00-00-00')
    with ExperimentApi(project) as api:
        api._session.add(
            ExperimentRun(
                experiment_id=experiment_id,
                status=StatusEnum.INTERRUPTED,
                start_time=None,
                created_at=datetime(2025, 1, 1, 0, 0, 5),
            )
        )

    assert _orphans(project) == [str(other)]
    assert near.exists()


def test_prune_pathless_run_without_experiment_keeps_nearby_folders_of_every_experiment(project):
    _experiment(project)
    _experiment(project, 'other')
    make_run(project, 'exp', '2025-01-01_00-00-00')
    make_run(project, 'other', '2025-01-01_00-30-00')
    far = make_run(project, 'exp', '2025-03-01_00-00-00')
    _run(project, None, None, status=StatusEnum.FAILED, start=datetime(2025, 1, 1, 0, 1))

    assert _orphans(project) == [str(far)]


# ------------------------------------------------ run/ shared between projects


def _register(root: Path, name: str) -> None:
    with EnvironmentDbApi() as db:
        db._session.add(Project(name=name, path=str(root)))


def _sharing_project(project: Path, tmp_path: Path, name: str = 'second') -> Path:
    """A second registered project whose run/ is a symlink to ``project``'s run/."""
    root = tmp_path / name
    (root / 'experiments' / 'exp').mkdir(parents=True)
    (root / 'run').symlink_to(project / 'run', target_is_directory=True)
    _register(root, name)
    return root


def test_prune_counts_the_runs_of_every_project_sharing_the_run_directory(project, tmp_path):
    _experiment(project)
    second = _sharing_project(project, tmp_path)
    mine = make_run(project, 'exp', '2025-01-01_00-00-00')
    theirs = make_run(project, 'exp', '2025-01-02_00-00-00')
    orphan = make_run(project, 'exp', '2025-01-03_00-00-00')
    _run(project, _experiment(project, 'unused'), str(mine))
    _run(second, _experiment(second), str(second / 'run' / 'exp' / theirs.name))

    assert _orphans(project) == [str(orphan)]
    # And the other way round, through the symlinked run/.
    assert _orphans(second) == [str(second / 'run' / 'exp' / orphan.name)]

    ShowService().prune_runs(RunPruneRequest(project_path=project, execute=True))
    assert mine.exists()
    assert theirs.exists()
    assert not orphan.exists()


def test_prune_refuses_when_a_project_sharing_run_cannot_be_read(project, tmp_path):
    _experiment(project)
    _sharing_project(project, tmp_path, 'nodb')  # registered, shares run/, has no project database
    orphan = make_run(project, 'exp', '2025-01-03_00-00-00')

    for execute in (False, True):
        result = ShowService().prune_runs(RunPruneRequest(project_path=project, execute=execute))
        assert not result.success
        assert result.error.code == 'RunPruneRefused'
        assert 'nodb' in result.error.message
    assert orphan.exists()
    assert not (tmp_path / 'nodb' / '.adare').exists()  # nothing created in the other project


def test_prune_ignores_registered_projects_with_their_own_run_directory(project, tmp_path):
    _experiment(project)
    separate = tmp_path / 'separate'
    (separate / 'run').mkdir(parents=True)
    _register(separate, 'separate')
    _register(tmp_path / 'gone', 'gone')
    orphan = make_run(project, 'exp', '2025-01-03_00-00-00')

    assert _orphans(project) == [str(orphan)]
    assert not (separate / '.adare').exists()


# ------------------------------------------------------------- dev sessions


def _dev_session(project: Path, run_dir: Path | None, *, session_id: str | None = None, status='running') -> None:
    with DevModeApi() as db:
        session = DevSession(
            project_path=str(project),
            experiment_name='exp',
            environment_name='env',
            vm_name='vm',
            run_directory_path=str(run_dir) if run_dir else None,
            status=status,
        )
        if session_id:
            session.session_id = session_id
        db._session.add(session)


def test_runs_remove_keeps_a_dev_session_folder(project):
    experiment_id = _experiment(project)
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    run_id = _run(project, experiment_id, str(folder), fake=True)
    _dev_session(project, folder, status='stopped')

    result = ShowService().remove_run(RunRemoveRequest(ulid=run_id, project_path=project))

    assert result.success
    assert not result.data.folder_removed
    assert result.data.folder_note == 'folder kept: belongs to a dev session'
    assert folder.exists()
    assert run_id not in _run_ids(project)


def test_runs_remove_keeps_the_folder_of_a_dev_session_run_by_id(project):
    experiment_id = _experiment(project)
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    run_id = _run(project, experiment_id, str(folder), fake=True)
    _dev_session(project, None, session_id=run_id)  # the session never recorded its folder

    result = ShowService().remove_run(RunRemoveRequest(ulid=run_id, project_path=project))

    assert result.success
    assert not result.data.folder_removed
    assert folder.exists()


def test_experiment_clean_keeps_active_and_dev_session_fake_runs(project):
    experiment_id = _experiment(project)
    folders = {name: make_run(project, 'exp', f'2025-01-0{i}_00-00-00') for i, name in enumerate('abcde', 1)}
    done = _run(project, experiment_id, str(folders['a']), fake=True, status=StatusEnum.FAILED)
    running = _run(project, experiment_id, str(folders['b']), fake=True, status=StatusEnum.RUNNING)
    pending = _run(project, experiment_id, str(folders['c']), fake=True, status=StatusEnum.PENDING)
    by_path = _run(project, experiment_id, str(folders['d']), fake=True, status=StatusEnum.FINISHED)
    by_id = _run(project, experiment_id, str(folders['e']), fake=True, status=StatusEnum.INTERRUPTED)
    _dev_session(project, folders['d'], status='crashed')
    _dev_session(project, None, session_id=by_id)

    assert experiment_clean(project, 'exp') == 1

    assert not folders['a'].exists()
    assert all(folders[name].exists() for name in 'bcde')
    assert done not in _run_ids(project)
    assert _run_ids(project) == {running, pending, by_path, by_id}


def test_experiment_remove_keeps_dev_session_folders(project):
    experiment_id = _experiment(project)
    plain = make_run(project, 'exp', '2025-01-01_00-00-00')
    dev_by_path = make_run(project, 'exp', '2025-01-02_00-00-00')
    dev_by_id = make_run(project, 'exp', '2025-01-03_00-00-00')
    _run(project, experiment_id, str(plain))
    _run(project, experiment_id, str(dev_by_path), fake=True)
    _dev_session(project, dev_by_path)
    _dev_session(project, None, session_id=_run(project, experiment_id, str(dev_by_id), fake=True))

    experiment_remove(project, 'exp', force=True)

    assert not plain.exists()
    assert dev_by_path.exists()
    assert dev_by_id.exists()
    assert _run_ids(project) == set()


def test_prune_fake_skips_non_terminal_and_dev_session_runs(project):
    experiment_id = _experiment(project)
    done = _run(project, experiment_id, None, fake=True, status=StatusEnum.FAILED)
    for status in (StatusEnum.PENDING, StatusEnum.RUNNING, StatusEnum.PAUSE, StatusEnum.NONE):
        _run(project, experiment_id, None, fake=True, status=status)
    dev_id = _run(project, experiment_id, None, fake=True, status=StatusEnum.FINISHED)
    _dev_session(project, None, session_id=dev_id, status='stopped')
    dev_folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    _run(project, experiment_id, str(dev_folder), fake=True, status=StatusEnum.FINISHED)
    _dev_session(project, dev_folder)

    dry = ShowService().prune_runs(RunPruneRequest(project_path=project, fake=True)).data
    assert [(e.kind, e.run_ulid) for e in dry.entries] == [('fake', done)]

    result = ShowService().prune_runs(RunPruneRequest(project_path=project, fake=True, execute=True)).data
    assert result.rows_deleted == 1
    assert done not in _run_ids(project)
    assert len(_run_ids(project)) == 6
    assert dev_folder.exists()
