"""Every run-delete path removes the rows a run owns, not only what the ORM cascades.

Foreign keys are off in SQLite: a run's ``action_execution`` rows (linked by
``experiment_run_id`` only), its ``experiment_run_files`` row and that row's
``log_file`` rows used to stay behind after ``session.delete(run)``.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from adare.backend.environment import database as env_database
from adare.backend.testfunction import database as testfunction_database
from adare.database.api.base import ProjectDatabaseApi
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.experiment import ExperimentApi
from adare.database.api.run_cleanup import delete_runs
from adare.database.models.global_models import Project, TestFunction, TestFunctionFile
from adare.database.models.project_models import (
    AbstractTest,
    ActionExecution,
    Event,
    Experiment,
    ExperimentRun,
    ExperimentRunFiles,
    LogFile,
    Playbook,
    PlaybookItem,
    RunArtifact,
    Stage,
    StageInRun,
    Status,
)
from adare.database.reference_manager import reference_manager

pytestmark = pytest.mark.unit

RUN_TABLES = ('experiment_run', 'action_execution', 'experiment_run_files', 'log_file', 'event', 'stage_in_run')


@pytest.fixture
def global_db(tmp_path):
    db_file = tmp_path / 'global.db'
    with (
        patch('adare.config.database.get_global_database_location', return_value=db_file),
        patch.object(reference_manager, '_global_api', None),
        patch.object(reference_manager, '_cache', {}),
        patch.object(reference_manager, '_cache_timestamps', {}),
    ):
        yield db_file


@pytest.fixture
def project(tmp_path):
    project_path = tmp_path / 'project'
    project_path.mkdir()
    return project_path


@pytest.fixture
def registered_project(project, global_db):
    with EnvironmentDbApi() as db:
        db._session.add(Project(name='project', path=str(project)))
        db._session.commit()
    return project


def _add_experiment(project_path: Path, name: str = 'exp', abstract_tests=()) -> tuple[str, str]:
    """An experiment with a one-action playbook; returns (experiment id, playbook item id)."""
    with ExperimentApi(project_path) as api:
        experiment = Experiment(
            name=name, sha256='0' * 64, sha256_playbook='1' * 64, sha256_metadata='2' * 64, environment_ids=[]
        )
        experiment.abstract_tests.extend(abstract_tests)
        playbook = Playbook(name='pb', experiment=experiment)
        item = PlaybookItem(item_type='action', sequence_order=0, parameters={}, playbook=playbook)
        api._session.add_all([experiment, playbook, item])
        api._session.flush()
        return experiment.id, item.id


def _add_run(
    project_path: Path,
    experiment_id: str,
    item_id: str,
    *,
    fake: bool = False,
    environment_id: str | None = None,
    executions: int = 2,
) -> str:
    """A run owning every kind of row: files + logs, executions, events, stages, artifacts."""
    with ExperimentApi(project_path) as api:
        session = api._session
        run = ExperimentRun(experiment_id=experiment_id, fake=fake, environment_id=environment_id)
        session.add(run)
        session.flush()
        run.path = f'/runs/{run.id}'
        run.files = ExperimentRunFiles(
            log_adare=LogFile(name='adare.log', path=f'/runs/{run.id}/adare.log'),
            log_adarevm=LogFile(name='adarevm.log', path=f'/runs/{run.id}/adarevm.log'),
        )
        for attempt in range(executions):
            session.add(
                ActionExecution(
                    playbook_item_id=item_id,
                    experiment_run_id=run.id,
                    status='success',
                    attempt_number=attempt + 1,
                    result_data={'blob': 'x' * 1000},
                )
            )
        session.add(Event(experiment_run=run, category='action'))
        session.add(RunArtifact(experiment_run=run, kind='disk_image', path=f'/runs/{run.id}/disk.raw'))
        run.stages_in_run.append(StageInRun(stage=session.query(Stage).first(), status=session.query(Status).first()))
        return run.id


def _add_dev_session_execution(project_path: Path, item_id: str) -> None:
    with ProjectDatabaseApi(project_path) as api:
        api._session.add(ActionExecution(playbook_item_id=item_id, experiment_run_id=None, status='success'))


def _counts(project_path: Path) -> dict[str, int]:
    with ProjectDatabaseApi(project_path) as api:
        return {t: api._session.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar_one() for t in RUN_TABLES} | {
            'run_artifact': api._session.execute(text('SELECT COUNT(*) FROM run_artifact')).scalar_one(),
            'dev_executions': api._session.execute(
                text('SELECT COUNT(*) FROM action_execution WHERE experiment_run_id IS NULL')
            ).scalar_one(),
        }


def _assert_no_orphans(project_path: Path) -> None:
    with ProjectDatabaseApi(project_path) as api:
        conn = api._session
        orphan_queries = {
            'action_execution': 'SELECT COUNT(*) FROM action_execution WHERE experiment_run_id IS NOT NULL '
            'AND experiment_run_id NOT IN (SELECT id FROM experiment_run)',
            'experiment_run_files': 'SELECT COUNT(*) FROM experiment_run_files WHERE id NOT IN '
            '(SELECT files_id FROM experiment_run WHERE files_id IS NOT NULL)',
            'log_file': 'SELECT COUNT(*) FROM log_file WHERE id NOT IN (SELECT log_adare_id FROM experiment_run_files '
            'WHERE log_adare_id IS NOT NULL UNION SELECT log_adarevm_id FROM experiment_run_files '
            'WHERE log_adarevm_id IS NOT NULL)',
            'event': 'SELECT COUNT(*) FROM event WHERE experiment_run_id NOT IN (SELECT id FROM experiment_run)',
            'stage_in_run': 'SELECT COUNT(*) FROM stage_in_run WHERE run_id NOT IN (SELECT id FROM experiment_run)',
            'run_artifact': 'SELECT COUNT(*) FROM run_artifact '
            'WHERE experiment_run_id NOT IN (SELECT id FROM experiment_run)',
        }
        leftovers = {table: conn.execute(text(sql)).scalar_one() for table, sql in orphan_queries.items()}
    assert leftovers == dict.fromkeys(orphan_queries, 0)


@pytest.fixture
def two_runs(project):
    """(experiment id, doomed run id, kept run id) plus one dev-session execution."""
    experiment_id, item_id = _add_experiment(project)
    doomed = _add_run(project, experiment_id, item_id, fake=True)
    kept = _add_run(project, experiment_id, item_id)
    _add_dev_session_execution(project, item_id)
    return experiment_id, doomed, kept


def _assert_only_kept_run_left(project: Path, kept: str) -> None:
    _assert_no_orphans(project)
    counts = _counts(project)
    assert counts == {
        'experiment_run': 1,
        'action_execution': 3,  # the kept run's 2 + the dev-session one
        'experiment_run_files': 1,
        'log_file': 2,
        'event': 1,
        'stage_in_run': 1,
        'run_artifact': 1,
        'dev_executions': 1,
    }
    with ProjectDatabaseApi(project) as api:
        assert [run.id for run in api._session.query(ExperimentRun)] == [kept]


class TestDeleteRuns:
    def test_deletes_everything_a_run_owns_and_returns_its_path(self, project, two_runs):
        _, doomed, kept = two_runs

        with ProjectDatabaseApi(project) as api:
            run = api._session.get(ExperimentRun, doomed)
            assert delete_runs(api._session, [run]) == [f'/runs/{doomed}']

        _assert_only_kept_run_left(project, kept)

    def test_nothing_to_delete(self, project):
        with ProjectDatabaseApi(project) as api:
            assert delete_runs(api._session, []) == []

    def test_does_not_commit(self, project, two_runs):
        _, doomed, _ = two_runs

        with ProjectDatabaseApi(project) as api:
            delete_runs(api._session, [api._session.get(ExperimentRun, doomed)])
            api._session.rollback()

        assert _counts(project)['experiment_run'] == 2

    def test_run_without_files_or_path(self, project):
        experiment_id, item_id = _add_experiment(project)
        with ProjectDatabaseApi(project) as api:
            run = ExperimentRun(experiment_id=experiment_id)
            api._session.add(run)
            api._session.flush()
            api._session.add(ActionExecution(playbook_item_id=item_id, experiment_run_id=run.id, status='failed'))
            api._session.flush()
            assert delete_runs(api._session, [run]) == []

        assert _counts(project)['experiment_run'] == 0
        assert _counts(project)['action_execution'] == 0

    def test_keeps_files_and_log_rows_another_run_still_uses(self, project, two_runs):
        _, doomed, kept = two_runs
        with ProjectDatabaseApi(project) as api:
            kept_run = api._session.get(ExperimentRun, kept)
            doomed_run = api._session.get(ExperimentRun, doomed)
            # A second files row sharing the kept run's adare log, and the doomed run sharing the kept files row.
            api._session.add(ExperimentRunFiles(log_adare_id=kept_run.files.log_adare_id))
            doomed_run.files_id = kept_run.files_id

        with ProjectDatabaseApi(project) as api:
            delete_runs(api._session, [api._session.get(ExperimentRun, doomed)])

        with ProjectDatabaseApi(project) as api:
            kept_run = api._session.get(ExperimentRun, kept)
            assert kept_run.files is not None
            assert kept_run.files.log_adare is not None
            assert kept_run.files.log_adarevm is not None


class TestExperimentApiDeletePaths:
    def test_delete_experiment_run(self, project, two_runs):
        _, doomed, kept = two_runs

        with ExperimentApi(project) as api:
            paths = api.delete_experiment_run(api._session.get(ExperimentRun, doomed))

        assert paths == [f'/runs/{doomed}']
        _assert_only_kept_run_left(project, kept)

    def test_remove_fake_experiment_run(self, project, two_runs):
        _, doomed, kept = two_runs

        with ExperimentApi(project) as api:
            assert api.remove_fake_experiment_run(doomed) == [f'/runs/{doomed}']
            assert api.remove_fake_experiment_run(kept) == []  # not fake: left alone

        _assert_only_kept_run_left(project, kept)

    def test_remove_fake_runs_by_experiment_name(self, project, two_runs):
        _, doomed, kept = two_runs

        with ExperimentApi(project) as api:
            assert api.remove_fake_experiment_runs_by_experiment_name(project, 'exp') == 1

        _assert_only_kept_run_left(project, kept)

    def test_remove_fake_runs_of_experiment_returns_paths(self, project, two_runs):
        _, doomed, kept = two_runs

        with ExperimentApi(project) as api:
            assert api.remove_fake_runs_of_experiment(project, 'exp') == (1, [f'/runs/{doomed}'])

        _assert_only_kept_run_left(project, kept)

    def test_remove_experiment_deletes_all_its_runs(self, project, two_runs):
        experiment_id, doomed, kept = two_runs
        other_id, other_item = _add_experiment(project, name='other')
        other_run = _add_run(project, other_id, other_item)

        with ExperimentApi(project) as api:
            paths = api.remove_experiment_by_ulid(experiment_id)

        assert sorted(paths) == sorted([f'/runs/{doomed}', f'/runs/{kept}'])
        _assert_no_orphans(project)
        counts = _counts(project)
        assert counts['experiment_run'] == 1
        assert counts['action_execution'] == 2  # the other experiment's run
        assert counts['experiment_run_files'] == 1
        assert counts['log_file'] == 2
        with ProjectDatabaseApi(project) as api:
            assert [e.name for e in api._session.query(Experiment)] == ['other']
            assert [r.id for r in api._session.query(ExperimentRun)] == [other_run]

    def test_remove_experiment_with_runs_already_loaded(self, project, two_runs):
        experiment_id, _, _ = two_runs

        with ExperimentApi(project) as api:
            experiment = api.get_experiment_by_ulid(experiment_id)
            assert len(experiment.runs) == 2  # collection loaded before the delete
            assert len(api.remove_experiment(experiment)) == 2

        _assert_no_orphans(project)
        assert _counts(project)['experiment_run'] == 0


def _new_environment_version(name: str, sha: str) -> str:
    with EnvironmentDbApi() as db:
        return db.create_environment_version(
            name=name,
            description='',
            vm_id=None,
            vm_hash=None,
            tags=[],
            installations=[],
            environment_file=Path(f'/envs/{name}_{sha[:8]}.yml'),
            sha256hash=sha,
            hypervisor='qemu',
        ).id


class TestEnvironmentForceDelete:
    def test_force_deletes_runs_completely_and_returns_their_paths(self, registered_project):
        environment_id = _new_environment_version('ubuntu', '1' * 64)
        experiment_id, item_id = _add_experiment(registered_project)
        doomed = _add_run(registered_project, experiment_id, item_id, environment_id=environment_id)
        kept = _add_run(registered_project, experiment_id, item_id, environment_id='other-env')
        _add_dev_session_execution(registered_project, item_id)

        paths = env_database.delete_environment(environment_id, force=True, cleanup_vm=False)

        assert paths == [f'/runs/{doomed}']
        _assert_only_kept_run_left(registered_project, kept)


class TestTestfunctionRunDelete:
    @staticmethod
    def _add_testfunction() -> str:
        with EnvironmentDbApi() as db:
            tf_file = TestFunctionFile(name='xml', path='/tf/xml.py', sha256hash='f' * 64)
            tf = TestFunction(type='check', name='node_exists', sha256hash='e' * 64, file=tf_file)
            db._session.add_all([tf_file, tf])
            db._session.flush()
            return tf.id

    def test_deletes_runs_in_the_project_database(self, registered_project):
        testfunction_id = self._add_testfunction()
        experiment_id, item_id = _add_experiment(
            registered_project, abstract_tests=[AbstractTest(name='t', testfunction_id=testfunction_id)]
        )
        doomed = _add_run(registered_project, experiment_id, item_id)
        other_id, other_item = _add_experiment(registered_project, name='other')
        kept = _add_run(registered_project, other_id, other_item)
        _add_dev_session_execution(registered_project, item_id)

        assert testfunction_database.delete_runs_for_testfunction('xml') == (1, [f'/runs/{doomed}'])

        _assert_only_kept_run_left(registered_project, kept)

    def test_count_wrapper(self, registered_project):
        testfunction_id = self._add_testfunction()
        experiment_id, item_id = _add_experiment(
            registered_project, abstract_tests=[AbstractTest(name='t', testfunction_id=testfunction_id)]
        )
        _add_run(registered_project, experiment_id, item_id)
        _add_run(registered_project, experiment_id, item_id)

        assert testfunction_database.delete_experiment_runs_for_testfunction('xml') == 2
        assert testfunction_database.delete_experiment_runs_for_testfunction('xml') == 0
        _assert_no_orphans(registered_project)

    def test_unknown_testfunction_deletes_nothing(self, registered_project):
        assert testfunction_database.delete_runs_for_testfunction('nope') == (0, [])
