"""A real temp-database ADARE workspace for webapi route tests.

Seeds two projects through the real database layer so a route test goes
route -> ``AdareAPI`` -> ``ShowService`` -> ``StructuredDataApi`` -> SQLite and asserts
the JSON the React frontend actually receives, not what a mocked service would return.

The two projects share the experiment short name ``exp`` (short names repeat across
projects, which is why the frontend scopes run lookups by project).

Not a test module (no ``test_`` prefix); import ``seeded_fixture`` into a test module to use it.
"""

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import ulid

from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.experiment import ExperimentApi
from adare.database.models.global_models import OsInfo, Project, Vm
from adare.database.models.project_models import (
    AbstractTest,
    Experiment,
    ExperimentRun,
    ExperimentRunFiles,
    Result,
    Status,
    Tag,
    TestEvent,
)
from adare.database.reference_manager import reference_manager
from adarelib.constants import StatusEnum

START = datetime(2026, 1, 2, 3, 4, 5)
END = datetime(2026, 1, 2, 3, 6, 5)


@dataclass
class Seeded:
    """Ids and paths of the seeded workspace."""

    alpha: Path
    beta: Path
    env_id: str
    exp_id: str
    run_id: str
    run_dir: Path
    beta_exp_id: str
    beta_run_id: str
    other_exp_id: str


def _new_id() -> str:
    return str(ulid.ULID())


def _add_environment(name: str) -> str:
    with EnvironmentDbApi() as db:
        osinfo = OsInfo(platform='linux', os='Ubuntu', distribution='Jammy', version='22.04')
        vm = Vm(name=f'{name}-disk', file=f'/disks/{name}.qcow2', hash='a' * 64, hypervisor='qemu', osinfo=osinfo)
        db._session.add(vm)
        db._session.flush()
        env = db.create_environment_version(
            name=name,
            description='',
            vm_id=vm.id,
            vm_hash=None,
            tags=[],
            installations=[],
            environment_file=Path(f'/envs/{name}.yml'),
            sha256hash='b' * 64,
            hypervisor='qemu',
        )
        return env.id


def _add_experiment(project: Path, name: str, env_id: str, tests: list[AbstractTest], tag: str | None = None) -> str:
    with ExperimentApi(project) as api:
        experiment = Experiment(
            name=name,
            description=f'{name} description',
            sha256='0' * 64,
            sha256_playbook='1' * 64,
            sha256_metadata='2' * 64,
            environment_ids=[env_id],
        )
        experiment.abstract_tests = tests
        if tag:
            experiment.tags = [Tag(name=tag)]
        api._session.add(experiment)
        api._session.flush()
        return experiment.id


def _add_run(
    project: Path,
    experiment_id: str,
    env_id: str,
    run_dir: Path,
    results: list[tuple[AbstractTest, StatusEnum]] | None = None,
) -> str:
    with ExperimentApi(project) as api:
        session = api._session
        for status in StatusEnum:
            if session.get(Status, status.value) is None:
                session.add(Status(id=status.value, name=status.name))
        session.flush()
        run = ExperimentRun(
            experiment_id=experiment_id,
            environment_id=env_id,
            path=str(run_dir),
            status=StatusEnum.FINISHED,
            start_time=START,
            end_time=END,
            published=True,
            files=ExperimentRunFiles(),
        )
        session.add(run)
        session.flush()
        for abstract_test, status in results or []:
            # Like a real run: a result-less `test_start` and a `test_complete` per test, one group.
            group = _new_id()
            session.add(
                TestEvent(
                    id=_new_id(),
                    experiment_run_id=run.id,
                    abstract_test_id=abstract_test.id,
                    event_type_specific='test_start',
                    event_group_id=group,
                    timestamp=START,
                )
            )
            session.add(
                TestEvent(
                    id=_new_id(),
                    experiment_run_id=run.id,
                    abstract_test_id=abstract_test.id,
                    success=status == StatusEnum.SUCCESS,
                    result=Result(status=str(int(status)), details=f'{abstract_test.name} details'),
                    event_type_specific='test_complete',
                    event_group_id=group,
                    timestamp=START,
                )
            )
        session.flush()
        return run.id


def _age(run_dir: Path) -> None:
    """Run-folder deletion only removes folders that look like run folders and are > 1 h old."""
    old = time.time() - 3 * 86400
    for path in (*run_dir.rglob('*'), run_dir):
        os.utime(path, (old, old))


def _make_project(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / 'experiments').mkdir(parents=True)
    (root / 'run').mkdir()
    return root


@pytest.fixture(name='seeded')
def seeded_fixture(tmp_path):
    """Projects ``Alpha`` (experiments ``exp``, ``other``) and ``Beta`` (experiment ``exp``)."""
    db_file = tmp_path / 'global.db'
    alpha, beta = _make_project(tmp_path, 'alpha'), _make_project(tmp_path, 'beta')
    with (
        patch('adare.config.database.get_global_database_location', return_value=db_file),
        patch('adare.config.database.get_database_location', return_value=db_file),
        patch.object(reference_manager, '_global_api', None),
        patch.object(reference_manager, '_cache', {}),
        patch.object(reference_manager, '_cache_timestamps', {}),
    ):
        with EnvironmentDbApi() as db:
            db._session.add(Project(name='Alpha', path=str(alpha)))
            db._session.add(Project(name='Beta', path=str(beta)))
        env_id = _add_environment('ubuntu-env')

        tests = [
            AbstractTest(id=_new_id(), name='file_exists', testfunction_id='standard.file_exists'),
            AbstractTest(id=_new_id(), name='file_hash', testfunction_id='standard.file_hash'),
        ]
        exp_id = _add_experiment(alpha, 'exp', env_id, tests, tag='forensics')
        other_exp_id = _add_experiment(alpha, 'other', env_id, [])
        run_dir = alpha / 'run' / 'exp' / '2026-01-02_03-04-05'
        (run_dir / 'steps').mkdir(parents=True)
        (run_dir / 'logs').mkdir()
        _age(run_dir)
        run_id = _add_run(
            alpha,
            exp_id,
            env_id,
            run_dir,
            results=[(tests[0], StatusEnum.SUCCESS), (tests[1], StatusEnum.FAILED)],
        )

        beta_exp_id = _add_experiment(beta, 'exp', env_id, [])
        beta_run_dir = beta / 'run' / 'exp' / '2026-01-03_00-00-00'
        beta_run_dir.mkdir(parents=True)
        beta_run_id = _add_run(beta, beta_exp_id, env_id, beta_run_dir)

        yield Seeded(
            alpha=alpha,
            beta=beta,
            env_id=env_id,
            exp_id=exp_id,
            run_id=run_id,
            run_dir=run_dir,
            beta_exp_id=beta_exp_id,
            beta_run_id=beta_run_id,
            other_exp_id=other_exp_id,
        )
