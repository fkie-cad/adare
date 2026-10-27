"""Batched run verdicts agree with ExperimentRun.result_status on every branch."""

import pytest
import sqlalchemy
import ulid
from sqlalchemy.orm import joinedload, sessionmaker

from adare.database.api.run_results import load_result_statuses
from adare.database.models.project_models import (
    AbstractTest,
    Experiment,
    ExperimentRun,
    ProjectBase,
    Result,
    TestEvent,
)
from adarelib.constants import StatusEnum

pytestmark = pytest.mark.unit


def _id() -> str:
    return str(ulid.ULID())


@pytest.fixture
def session(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "runs.db"}')
    ProjectBase.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def _test_event(run, abstract_test, *, success=True, status=StatusEnum.SUCCESS):
    result = Result(status=str(int(status))) if status is not None else None
    return TestEvent(id=_id(), experiment_run_id=run.id, abstract_test=abstract_test, success=success, result=result)


def _runs_by_verdict(session) -> dict[StatusEnum, ExperimentRun]:
    first = AbstractTest(id=_id(), name='first', testfunction_id='standard.file_exists')
    second = AbstractTest(id=_id(), name='second', testfunction_id='standard.file_exists')
    experiment = Experiment(id=_id(), name='exp', sha256='x')
    experiment.abstract_tests = [first, second]
    untested = Experiment(id=_id(), name='untested', sha256='y')

    def run(exp):
        return ExperimentRun(id=_id(), experiment_id=exp.id if exp else None)

    runs = {
        StatusEnum.SUCCESS: run(experiment),
        StatusEnum.WARNING: run(experiment),
        StatusEnum.FAILED: run(experiment),
        StatusEnum.TEST_FAILED: run(experiment),  # a test result that is not SUCCESS/WARNING
        StatusEnum.TEST_MISSING: run(experiment),
        StatusEnum.NONE: run(untested),  # experiment without tests and a run without events
        StatusEnum.ERROR: run(None),
    }
    session.add_all([experiment, untested, *runs.values()])
    session.add_all(
        [
            _test_event(runs[StatusEnum.SUCCESS], first),
            _test_event(runs[StatusEnum.SUCCESS], second, status=None),
            _test_event(runs[StatusEnum.WARNING], first, status=StatusEnum.WARNING),
            _test_event(runs[StatusEnum.WARNING], second),
            _test_event(runs[StatusEnum.FAILED], first, success=False),
            _test_event(runs[StatusEnum.TEST_FAILED], first, status=StatusEnum.FAILED),
            _test_event(runs[StatusEnum.TEST_MISSING], first),
        ]
    )
    session.commit()
    return runs


def test_batched_verdicts_match_the_per_run_property(session):
    runs = _runs_by_verdict(session)
    loaded = session.query(ExperimentRun).options(joinedload(ExperimentRun.experiment)).all()

    batched = load_result_statuses(session, loaded)

    assert batched == {run.id: run.result_status for run in loaded}
    assert {key: batched[run.id] for key, run in runs.items()} == {
        StatusEnum.SUCCESS: StatusEnum.SUCCESS,
        StatusEnum.WARNING: StatusEnum.WARNING,
        StatusEnum.FAILED: StatusEnum.FAILED,
        StatusEnum.TEST_FAILED: StatusEnum.FAILED,
        StatusEnum.TEST_MISSING: StatusEnum.TEST_MISSING,
        StatusEnum.NONE: StatusEnum.SUCCESS,
        StatusEnum.ERROR: StatusEnum.ERROR,
    }


def test_listing_many_runs_takes_a_fixed_number_of_queries(session):
    _runs_by_verdict(session)
    loaded = session.query(ExperimentRun).options(joinedload(ExperimentRun.experiment)).all()
    statements = []
    sqlalchemy.event.listen(session.bind, 'before_cursor_execute', lambda *args: statements.append(args[2]))

    load_result_statuses(session, loaded)

    assert len(statements) == 2  # test events + expected tests, independent of the run count
