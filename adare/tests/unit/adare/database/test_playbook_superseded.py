"""Re-ingesting a playbook keeps the items earlier runs executed (marked superseded).

Re-ingest used to bulk-delete every item of the playbook, so the ``action_execution``
rows of existing runs pointed at deleted items (foreign keys are off in SQLite).
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy
from sqlalchemy import text

from adare.core.dto.playbook import PlaybookWriteRequest
from adare.database import maintenance
from adare.database.api.base import ProjectDatabaseApi
from adare.database.api.experiment import ExperimentApi
from adare.database.api.playbook import PlaybookApi
from adare.database.migrations import add_superseded_to_playbook_item
from adare.database.migrations.runner import MIGRATIONS
from adare.database.models.project_models import ActionExecution, Experiment, ExperimentRun, ProjectBase
from adare.database.reference_manager import reference_manager
from adare.services.experiment_service import ExperimentService

pytestmark = pytest.mark.unit

EXPERIMENT = 'exp'


def _playbook_yaml(*commands: str) -> str:
    actions = ''.join(f'  - command:\n      command: "{command}"\n      shell: true\n' for command in commands)
    return f'actions:\n{actions}'


@pytest.fixture
def project(tmp_path):
    """A project with one loaded experiment whose playbook has the actions a, b, c."""
    with (
        patch('adare.config.database.get_global_database_location', return_value=tmp_path / 'global.db'),
        patch.object(reference_manager, '_global_api', None),
        patch.object(reference_manager, '_cache', {}),
        patch.object(reference_manager, '_cache_timestamps', {}),
    ):
        project_path = tmp_path / 'project'
        experiment_dir = project_path / 'experiments' / EXPERIMENT
        experiment_dir.mkdir(parents=True)
        playbook_file = experiment_dir / 'playbook.yml'
        playbook_file.write_text(_playbook_yaml('echo a', 'echo b', 'echo c'), encoding='utf-8')
        with ExperimentApi(project_path) as api:
            experiment = Experiment(name=EXPERIMENT, sha256='0' * 64, environment_ids=[])
            api._session.add(experiment)
            api._session.flush()
            playbook_api = PlaybookApi(project_path)
            playbook_api._session = api._session
            playbook_api.populate_playbook_from_file(experiment, playbook_file)
        yield project_path


def _write_playbook(project_path: Path, *commands: str) -> None:
    result = ExperimentService().write_playbook(
        PlaybookWriteRequest(project_path=project_path, experiment=EXPERIMENT, yaml=_playbook_yaml(*commands))
    )
    assert result.success, result.error
    assert result.data.db_ingested


def _current_commands(project_path: Path) -> list[str]:
    with PlaybookApi(project_path) as api:
        experiment = api._session.query(Experiment).filter_by(name=EXPERIMENT).one()
        playbook = api.load_playbook_from_database(experiment.id)
        return [action.command for action in playbook.actions]


def _current_item_ids(project_path: Path) -> list[str]:
    with PlaybookApi(project_path) as api:
        experiment = api._session.query(Experiment).filter_by(name=EXPERIMENT).one()
        playbook = api.get_playbook_by_experiment_id(experiment.id)
        return [item.id for item in api.get_playbook_items(playbook.id)]


def _items(project_path: Path) -> dict[str, bool]:
    """Every playbook_item row: id -> superseded."""
    with ProjectDatabaseApi(project_path) as api:
        rows = api._session.execute(text('SELECT id, superseded FROM playbook_item')).all()
        return {row[0]: bool(row[1]) for row in rows}


def _run_executing(project_path: Path, item_ids: list[str]) -> str:
    """A run with one execution per given item; returns the run id."""
    with ExperimentApi(project_path) as api:
        experiment = api._session.query(Experiment).filter_by(name=EXPERIMENT).one()
        run = ExperimentRun(experiment_id=experiment.id)
        api._session.add(run)
        api._session.flush()
        for item_id in item_ids:
            api._session.add(ActionExecution(playbook_item_id=item_id, experiment_run_id=run.id, status='success'))
        return run.id


def _check(project_path: Path):
    target = maintenance.DatabaseTarget('proj', project_path / '.adare' / 'project.db.sqlite3', project_path)
    return maintenance.check_database(target)


def test_reingest_keeps_executed_items_superseded_and_deletes_the_rest(project):
    first, second, third = _current_item_ids(project)
    _run_executing(project, [first, second])

    _write_playbook(project, 'echo x', 'echo y')

    items = _items(project)
    assert items[first] is True
    assert items[second] is True
    assert third not in items
    new_ids = _current_item_ids(project)
    assert len(new_ids) == 2
    assert not set(new_ids) & {first, second}
    assert all(items[item_id] is False for item_id in new_ids)
    assert _current_commands(project) == ['echo x', 'echo y']
    assert _check(project).orphans['action_execution_dangling_playbook_item'] == 0


def test_reingest_without_runs_replaces_every_item(project):
    old_ids = set(_current_item_ids(project))

    _write_playbook(project, 'echo x')

    assert not old_ids & set(_items(project))
    assert _current_commands(project) == ['echo x']


def test_reingest_twice(project):
    v1 = _current_item_ids(project)
    _run_executing(project, v1[:1])
    _write_playbook(project, 'echo x', 'echo y')
    v2 = _current_item_ids(project)
    _run_executing(project, v2)

    _write_playbook(project, 'echo p', 'echo q', 'echo r')

    items = _items(project)
    assert {item_id for item_id, superseded in items.items() if superseded} == {v1[0], *v2}
    assert _current_commands(project) == ['echo p', 'echo q', 'echo r']
    assert len(items) == 1 + 2 + 3
    assert _check(project).orphans['action_execution_dangling_playbook_item'] == 0


def test_superseded_item_whose_runs_are_gone_is_deleted_on_the_next_reingest(project):
    first = _current_item_ids(project)[0]
    run_id = _run_executing(project, [first])
    _write_playbook(project, 'echo x')
    with ExperimentApi(project) as api:
        api.delete_experiment_run(api._session.get(ExperimentRun, run_id))

    _write_playbook(project, 'echo y')

    assert first not in _items(project)
    assert _current_commands(project) == ['echo y']


def test_executions_map_to_current_items_by_sequence(project):
    """The run controller maps action index -> item via get_playbook_items: only current items."""
    _run_executing(project, _current_item_ids(project))
    _write_playbook(project, 'echo x', 'echo y')

    with PlaybookApi(project) as api:
        experiment = api._session.query(Experiment).filter_by(name=EXPERIMENT).one()
        playbook = api.get_playbook_by_experiment_id(experiment.id)
        orders = [item.sequence_order for item in api.get_playbook_items(playbook.id)]

    assert orders == [0, 1]


def test_experiment_removal_deletes_superseded_items(project):
    _run_executing(project, _current_item_ids(project))
    _write_playbook(project, 'echo x')
    assert any(_items(project).values())

    with ExperimentApi(project) as api:
        api.remove_experiment(api._session.query(Experiment).filter_by(name=EXPERIMENT).one())

    with ProjectDatabaseApi(project) as api:
        for table in ('playbook_item', 'playbook', 'action_execution', 'experiment_run'):
            assert api._session.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar_one() == 0, table


def _columns(conn) -> dict[str, tuple]:
    return {row[1]: row for row in conn.execute(text('PRAGMA table_info(playbook_item)'))}


def test_new_database_has_the_column_from_the_model(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "new.db"}')
    ProjectBase.metadata.create_all(engine)

    with engine.connect() as conn:
        column = _columns(conn)['superseded']

    assert column[3] == 1  # NOT NULL
    assert column[4] == "'0'"


def test_upgrade_adds_the_column_to_an_existing_database(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "old.db"}')
    ProjectBase.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE playbook_item DROP COLUMN superseded'))
        conn.execute(text("INSERT INTO playbook (id, experiment_id, name) VALUES ('pb', 'exp', 'pb')"))
        conn.execute(
            text(
                'INSERT INTO playbook_item (id, playbook_id, item_type, sequence_order, parameters) '
                "VALUES ('item', 'pb', 'action', 0, '{}')"
            )
        )

    with engine.begin() as conn:
        add_superseded_to_playbook_item.upgrade(conn)
        add_superseded_to_playbook_item.upgrade(conn)  # idempotent

    with engine.connect() as conn:
        assert 'superseded' in _columns(conn)
        assert conn.execute(text('SELECT superseded FROM playbook_item')).scalar_one() == 0


def test_upgrade_skips_a_database_without_the_table(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    with engine.begin() as conn:
        add_superseded_to_playbook_item.upgrade(conn)


def test_migration_is_registered_for_project_databases():
    entry = next(m for m in MIGRATIONS if m.name == 'add_superseded_to_playbook_item')

    assert entry.scope == 'project'
    assert entry.module == 'adare.database.migrations.add_superseded_to_playbook_item'
