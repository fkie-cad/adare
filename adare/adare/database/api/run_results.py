"""Verdicts of many experiment runs from a few batched queries.

``ExperimentRun.result_status`` lazy-loads every event of its run, then each test's
result and the experiment's tests: one run costs several queries, so a listing of
4.5k runs issued ~10k of them. :func:`load_result_statuses` reads the same rows for
all runs at once and computes the identical verdict (``compute_result_status``).
"""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy.orm import Session

from adare.database.models.project_models import (
    AbstractTest,
    ExperimentRun,
    Result,
    TestEvent,
    mapping_experiment_abstracttest,
)
from adare.database.models.run_verdict import compute_result_status
from adarelib.constants import StatusEnum

# Ids per IN (...) clause, well below SQLite's bound-parameter limit.
_CHUNK = 500


def _chunks(ids: list[str]) -> Iterable[list[str]]:
    for start in range(0, len(ids), _CHUNK):
        yield ids[start : start + _CHUNK]


def load_result_statuses(session: Session, runs: Iterable[ExperimentRun]) -> dict[str, StatusEnum]:
    """``result_status`` of each run, keyed by run id.

    ``run.experiment`` is read for every run, so eager-load it in the query that
    produced ``runs``.
    """
    runs = list(runs)
    linked = [run for run in runs if run.experiment is not None]

    tests_by_run: dict[str, list[tuple[bool | None, str | None, str | None]]] = defaultdict(list)
    for chunk in _chunks([str(run.id) for run in linked]):
        rows = (
            session.query(TestEvent.experiment_run_id, TestEvent.success, TestEvent.abstract_test_id, Result.status_id)
            .select_from(TestEvent)
            .outerjoin(Result, Result.id == TestEvent.result_id)
            .filter(TestEvent.experiment_run_id.in_(chunk))
        )
        for run_id, success, abstract_test_id, status_id in rows:
            tests_by_run[run_id].append((success, abstract_test_id, status_id))

    expected_by_experiment: dict[str, list[str]] = defaultdict(list)
    mapping = mapping_experiment_abstracttest.c
    for chunk in _chunks(list({str(run.experiment.id) for run in linked})):
        rows = (
            session.query(mapping.experiment_id, AbstractTest.id)
            .join(AbstractTest, AbstractTest.id == mapping.abstracttest_id)
            .filter(mapping.experiment_id.in_(chunk))
        )
        for experiment_id, test_id in rows:
            expected_by_experiment[experiment_id].append(test_id)

    statuses = {str(run.id): StatusEnum.ERROR for run in runs}
    for run in linked:
        run_id, experiment_id = str(run.id), str(run.experiment.id)
        statuses[run_id] = compute_result_status(tests_by_run[run_id], expected_by_experiment[experiment_id])
    return statuses
