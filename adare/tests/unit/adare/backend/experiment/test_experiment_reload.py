"""Reloading a changed experiment never deletes production runs.

`adare experiment run` / `replicate` load the experiment before every run. In test
mode (the default) that load used ``force=True``, and a changed playbook then went
through ``remove_experiment``: the experiment and *every* run of it -- production
runs included -- were deleted and the experiment recreated under a new id. Now a
changed experiment without production runs is refreshed in place (only its finished
fake runs go), and one with production runs is refused; only the explicit
``adare experiment load --force`` still replaces it.

Exercised against a real (temporary) project and global database.
"""

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text

from adare.backend.experiment.commands.load import ExperimentHasProductionRunsError, experiment_load
from adare.backend.experiment.directory import ExperimentDirectory
from adare.core.dto.playbook import PlaybookWriteRequest
from adare.database import maintenance
from adare.database.api.base import ProjectDatabaseApi
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.experiment import ExperimentApi
from adare.database.api.playbook import PlaybookApi
from adare.database.models.global_models import Project, TestFunction, TestFunctionFile, TestParameter
from adare.database.models.project_models import (
    ActionExecution,
    Experiment,
    ExperimentRun,
    PlaybookItem,
    SyncMetadata,
)
from adare.database.models.sync_identity import apply_remote_identity
from adare.database.reference_manager import reference_manager
from adare.services.experiment_service import ExperimentService
from adarelib.constants import StatusEnum

pytestmark = pytest.mark.unit

EXPERIMENT = 'exp'
#: Run folders this old pass the run-folder safety test (it refuses folders changed < 1 h ago).
OLD = time.time() - 3 * 86400
#: Naive UTC, like the database stores it.
NOW = datetime.now(UTC).replace(tzinfo=None)


def _playbook_yaml(*commands: str, tests: bool = False) -> str:
    actions = ''.join(f'  - command:\n      command: "{command}"\n      shell: true\n' for command in commands)
    text_ = f'actions:\n{actions}'
    if tests:
        text_ += 'tests:\n  - name: marker_exists\n    function: file_exists\n    parameter:\n      dst: /tmp/marker\n'
    return text_


@pytest.fixture
def project(tmp_path):
    """A project with the experiment ``exp`` (actions a, b, c) loaded through ``experiment_load``."""
    db_file = tmp_path / 'global.db'
    root = tmp_path / 'project'
    experiment_dir = root / 'experiments' / EXPERIMENT
    experiment_dir.mkdir(parents=True)
    (root / 'run').mkdir()
    (experiment_dir / 'metadata.yml').write_text('description: first\ntags: [alpha]\n', encoding='utf-8')
    (experiment_dir / 'playbook.yml').write_text(_playbook_yaml('echo a', 'echo b', 'echo c'), encoding='utf-8')
    with (
        patch('adare.config.database.get_global_database_location', return_value=db_file),
        patch('adare.config.database.get_database_location', return_value=db_file),
        patch.object(reference_manager, '_global_api', None),
        patch.object(reference_manager, '_cache', {}),
        patch.object(reference_manager, '_cache_timestamps', {}),
        patch('adare.backend.experiment.commands.load.is_logged_in', return_value=False),
    ):
        with EnvironmentDbApi() as db:
            db._session.add(Project(name='project', path=str(root)))
            tf_file = TestFunctionFile(name='standard', path='/tf/standard.py', sha256hash='f' * 64)
            db._session.add_all(
                [
                    tf_file,
                    TestFunction(type='check', name='file_exists', sha256hash='e' * 64, file=tf_file),
                    TestParameter(name='dst', dtype='str'),
                ]
            )
        _load(root)
        yield root


def _load(project: Path, force: bool = False) -> None:
    """What `adare experiment run` / `replicate` do before a run (test and production mode alike)."""
    experiment_load(project, EXPERIMENT, force=force, silent=True)


def _edit_playbook(project: Path, *commands: str, tests: bool = False) -> None:
    (project / 'experiments' / EXPERIMENT / 'playbook.yml').write_text(
        _playbook_yaml(*commands, tests=tests), encoding='utf-8'
    )


def _experiment(project: Path) -> dict:
    with ExperimentApi(project) as api:
        experiment = api._session.query(Experiment).filter_by(name=EXPERIMENT).one()
        return {
            'id': experiment.id,
            'sha256': experiment.sha256,
            'description': experiment.description,
            'tags': sorted(tag.name for tag in experiment.tags),
            'tests': sorted(test.name for test in experiment.abstract_tests),
            'sync_metadata_id': experiment.sync_metadata_id,
        }


def _current_items(project: Path) -> list[str]:
    with PlaybookApi(project) as api:
        playbook = api.get_playbook_by_experiment_id(_experiment(project)['id'])
        return [item.id for item in api.get_playbook_items(playbook.id)]


def _current_commands(project: Path) -> list[str]:
    with PlaybookApi(project) as api:
        return [action.command for action in api.load_playbook_from_database(_experiment(project)['id']).actions]


def _items(project: Path) -> dict[str, bool]:
    """Every playbook_item row: id -> superseded."""
    with ProjectDatabaseApi(project) as api:
        return {row[0]: bool(row[1]) for row in api._session.execute(text('SELECT id, superseded FROM playbook_item'))}


def _run_ids(project: Path) -> set[str]:
    with ProjectDatabaseApi(project) as api:
        return set(api._session.execute(text('SELECT id FROM experiment_run')).scalars())


def _execution_count(project: Path, run_id: str) -> int:
    with ProjectDatabaseApi(project) as api:
        return api._session.query(ActionExecution).filter_by(experiment_run_id=run_id).count()


def _add_run(
    project: Path,
    item_ids: list[str],
    *,
    fake: bool,
    status: StatusEnum = StatusEnum.SUCCESS,
    started: datetime | None = None,
    folder: str | None = None,
    folder_time: float = OLD,
) -> str:
    """A run of ``exp`` executing ``item_ids``; with ``folder`` also its run folder (last changed ``folder_time``)."""
    started = started or NOW - timedelta(days=3)
    path = None
    if folder is not None:
        run_dir = project / 'run' / EXPERIMENT / folder
        (run_dir / 'logs').mkdir(parents=True)
        (run_dir / 'logs' / 'adare.log').write_text('log', encoding='utf-8')
        for entry in (run_dir / 'logs' / 'adare.log', run_dir / 'logs', run_dir):
            os.utime(entry, (folder_time, folder_time))
        path = run_dir.as_posix()
    with ExperimentApi(project) as api:
        experiment = api._session.query(Experiment).filter_by(name=EXPERIMENT).one()
        run = ExperimentRun(
            experiment_id=experiment.id,
            fake=fake,
            status=status,
            path=path,
            start_time=started,
            created_at=started,
        )
        api._session.add(run)
        api._session.flush()
        for item_id in item_ids:
            api._session.add(ActionExecution(playbook_item_id=item_id, experiment_run_id=run.id, status='success'))
        return run.id


def _dangling(project: Path) -> int:
    target = maintenance.DatabaseTarget('proj', project / '.adare' / 'project.db.sqlite3', project)
    return maintenance.check_database(target).orphans['action_execution_dangling_playbook_item']


def _write_playbook(project: Path, *commands: str):
    return ExperimentService().write_playbook(
        PlaybookWriteRequest(project_path=project, experiment=EXPERIMENT, yaml=_playbook_yaml(*commands))
    )


# --- test-mode run path (load without force) ---------------------------------------------


def test_changed_experiment_without_production_runs_is_reloaded_in_place(project):
    before = _experiment(project)
    old_items = _current_items(project)
    fake = _add_run(project, old_items, fake=True, folder='2026-01-01_00-00-00')
    (project / 'experiments' / EXPERIMENT / 'metadata.yml').write_text(
        'description: second\ntags: [beta]\n', encoding='utf-8'
    )
    _edit_playbook(project, 'echo x', 'echo y', tests=True)

    _load(project)

    after = _experiment(project)
    assert after['id'] == before['id']
    assert after['sha256'] == ExperimentDirectory(project, EXPERIMENT).sha256
    assert (after['description'], after['tags'], after['tests']) == ('second', ['beta'], ['marker_exists'])
    assert fake not in _run_ids(project)
    assert _execution_count(project, fake) == 0
    assert not (project / 'run' / EXPERIMENT / '2026-01-01_00-00-00').exists()
    # Only the deleted fake run executed the old items, so they are gone, not superseded.
    assert not set(old_items) & set(_items(project))
    assert _current_commands(project) == ['echo x', 'echo y']
    assert _dangling(project) == 0


def test_reload_keeps_unfinished_fake_runs_and_the_items_they_may_still_execute(project):
    first, second, third = _current_items(project)
    running = _add_run(project, [first], fake=True, status=StatusEnum.RUNNING, started=NOW)
    _edit_playbook(project, 'echo x')

    _load(project)

    assert running in _run_ids(project)
    items = _items(project)
    # The run mapped all three items at its start: none may go, executed or not.
    assert {first: True, second: True, third: True}.items() <= items.items()
    assert _current_commands(project) == ['echo x']
    # The run goes on to execute an item it had not reached yet: still no dangling row.
    with ExperimentApi(project) as api:
        api._session.add(ActionExecution(playbook_item_id=third, experiment_run_id=running, status='success'))
    assert _dangling(project) == 0


def test_reload_drops_the_remote_identity_of_the_old_content(project):
    with ExperimentApi(project) as api:
        experiment = api._session.query(Experiment).filter_by(name=EXPERIMENT).one()
        apply_remote_identity(
            api._session, experiment, SyncMetadata, remote_ulid='R' * 26, remote_url='u', is_published=True
        )
    assert _experiment(project)['sync_metadata_id'] is not None
    _edit_playbook(project, 'echo x')

    _load(project)

    assert _experiment(project)['sync_metadata_id'] is None


def test_unchanged_experiment_reload_is_a_noop(project):
    before = _experiment(project)
    items = _current_items(project)
    production = _add_run(project, items, fake=False)
    fake = _add_run(project, items, fake=True, folder='2026-01-01_00-00-00')

    _load(project)
    _load(project, force=True)

    assert _experiment(project) == before
    assert {production, fake} <= _run_ids(project)
    assert _current_items(project) == items
    assert (project / 'run' / EXPERIMENT / '2026-01-01_00-00-00').is_dir()


# --- production runs: refuse, never delete --------------------------------------------------


def test_changed_experiment_with_production_runs_is_refused_and_nothing_changes(project):
    before = _experiment(project)
    items = _current_items(project)
    production = _add_run(project, items, fake=False)
    fake = _add_run(project, items, fake=True, folder='2026-01-01_00-00-00')
    _edit_playbook(project, 'echo x')

    with pytest.raises(ExperimentHasProductionRunsError) as raised:
        _load(project)

    assert '1 production run(s)' in raised.value.message
    solutions = ' '.join(raised.value.possible_solutions)
    assert f'adare experiment clone {EXPERIMENT}' in solutions
    assert f'adare experiment load {EXPERIMENT} --force' in solutions
    assert _experiment(project) == before
    assert {production, fake} <= _run_ids(project)
    assert _execution_count(project, production) == 3
    assert _current_items(project) == items
    assert not any(_items(project).values())


def test_an_unfinished_production_run_counts_too(project):
    _add_run(project, [], fake=False, status=StatusEnum.RUNNING, started=NOW)
    _edit_playbook(project, 'echo x')

    with pytest.raises(ExperimentHasProductionRunsError):
        _load(project)


def test_explicit_load_force_still_replaces_the_experiment_and_its_runs(project):
    before = _experiment(project)
    production = _add_run(project, _current_items(project), fake=False)
    _edit_playbook(project, 'echo x')

    _load(project, force=True)

    assert _experiment(project)['id'] != before['id']
    assert production not in _run_ids(project)
    assert _current_commands(project) == ['echo x']


@pytest.mark.parametrize('test_mode', [True, False])
def test_experiment_run_never_loads_with_force(project, test_mode):
    """The single-environment `experiment run` (and `replicate`) path loads with force=False."""
    from adare.cli import experiment as cli_experiment

    class Stop(Exception):
        pass

    arguments = SimpleNamespace(
        experiment=EXPERIMENT, environment='env', project=None, test=test_mode, verbose=True, very_verbose=False
    )
    with (
        patch.object(cli_experiment, 'determine_projectdirectory', return_value=project),
        patch.object(cli_experiment, 'resolve_experiment_path', return_value=EXPERIMENT),
        patch.object(cli_experiment, 'resolve_environment_path', return_value='env'),
        patch('adare.backend.experiment.commands.experiment_load', side_effect=Stop) as load,
        pytest.raises(Stop),
    ):
        cli_experiment.exec_experiment_run(arguments)

    load.assert_called_once_with(project, EXPERIMENT, force=False, silent=True)


# --- playbook set ------------------------------------------------------------------------------


def test_playbook_set_leaves_no_change_for_the_next_run(project):
    before = _experiment(project)
    fake = _add_run(project, _current_items(project), fake=True, folder='2026-01-01_00-00-00')

    result = _write_playbook(project, 'echo x', 'echo y')

    assert result.success, result.error
    assert result.data.db_ingested
    assert _experiment(project)['sha256'] == ExperimentDirectory(project, EXPERIMENT).sha256
    _load(project)  # the next run's load: no change, so nothing is deleted
    assert _experiment(project)['id'] == before['id']
    assert fake in _run_ids(project)
    assert (project / 'run' / EXPERIMENT / '2026-01-01_00-00-00').is_dir()
    assert _current_commands(project) == ['echo x', 'echo y']
    assert _dangling(project) == 0


def test_playbook_set_refuses_a_changed_playbook_when_production_runs_exist(project):
    playbook_file = project / 'experiments' / EXPERIMENT / 'playbook.yml'
    original = playbook_file.read_text(encoding='utf-8')
    before = _experiment(project)
    items = _current_items(project)
    production = _add_run(project, items, fake=False)

    result = _write_playbook(project, 'echo x')

    assert not result.success
    assert result.error.code == 'ExperimentHasProductionRunsError'
    assert playbook_file.read_text(encoding='utf-8') == original
    assert not playbook_file.with_suffix('.yml.bak').exists()
    assert _experiment(project) == before
    assert _current_items(project) == items
    assert production in _run_ids(project)


def test_playbook_set_may_write_back_the_loaded_version_despite_production_runs(project):
    _add_run(project, _current_items(project), fake=False)
    _edit_playbook(project, 'echo edited')  # edited on disk, not loaded

    result = _write_playbook(project, 'echo a', 'echo b', 'echo c')

    assert result.success, result.error
    _load(project)  # back in line with the database: a no-op


# --- re-ingest while a run is in progress ------------------------------------------------------


def test_reingest_with_an_active_run_supersedes_every_item(project):
    old = _current_items(project)
    _add_run(project, old[:1], fake=True, status=StatusEnum.RUNNING, started=NOW)

    assert _write_playbook(project, 'echo x').success

    items = _items(project)
    assert all(items[item_id] for item_id in old)
    assert _current_commands(project) == ['echo x']


def test_an_unfinished_run_whose_folder_changed_recently_is_active(project):
    old = _current_items(project)
    _add_run(
        project,
        [],
        fake=True,
        status=StatusEnum.PAUSE,
        started=NOW - timedelta(days=3),
        folder='2026-01-01_00-00-00',
        folder_time=time.time(),
    )

    assert _write_playbook(project, 'echo x').success

    assert all(_items(project)[item_id] for item_id in old)


def test_reingest_with_a_stale_unfinished_run_deletes_unreferenced_items(project):
    first, second, third = _current_items(project)
    _add_run(project, [first], fake=True, status=StatusEnum.RUNNING, started=NOW - timedelta(hours=2))

    assert _write_playbook(project, 'echo x').success

    items = _items(project)
    assert items[first] is True
    assert second not in items
    assert third not in items


def test_superseded_items_left_by_an_active_run_go_once_it_is_over(project):
    first, second, third = _current_items(project)
    running = _add_run(project, [first], fake=True, status=StatusEnum.RUNNING, started=NOW)
    assert _write_playbook(project, 'echo x').success
    with ExperimentApi(project) as api:
        api._session.get(ExperimentRun, running).status = StatusEnum.SUCCESS

    assert _write_playbook(project, 'echo y').success

    with ProjectDatabaseApi(project) as api:
        remaining = set(api._session.execute(text('SELECT id FROM playbook_item')).scalars())
        current = api._session.query(PlaybookItem).filter_by(superseded=False).count()
    assert first in remaining
    assert not {second, third} & remaining
    assert current == 1


def test_add_and_remove_env_never_force_reload():
    """`experiment add-env` / `remove-env` must not replace an experiment (and delete its production runs)."""
    import ast
    import inspect

    from adare.backend.experiment.commands import modify

    tree = ast.parse(inspect.getsource(modify))
    loads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'experiment_load'
    ]
    assert loads
    for call in loads:
        force = {kw.arg: kw.value for kw in call.keywords}['force']
        assert isinstance(force, ast.Constant) and force.value is False
    handlers = [
        node.type.id
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Name)
    ]
    assert 'ExperimentHasProductionRunsError' in handlers
