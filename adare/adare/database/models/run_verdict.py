"""The overall verdict of an experiment run, from its test events and its experiment's tests.

One function serves both ``ExperimentRun.result_status`` (one run, through its loaded
relationships) and :func:`adare.database.api.run_results.load_result_statuses` (many
runs from a few batched queries), so the two can never disagree.
"""

from collections.abc import Iterable

from adarelib.constants import StatusEnum


def compute_result_status(
    tests: Iterable[tuple[bool | None, str | None, str | None]], expected_test_ids: Iterable[str]
) -> StatusEnum:
    """Verdict of a run whose experiment exists.

    Args:
        tests: One ``(success, abstract_test_id, result_status_id)`` per test event of the run;
            ``result_status_id`` is None for a test without a stored result.
        expected_test_ids: Ids of the abstract tests the experiment declares.
    """
    tests = list(tests)
    # Failures take priority over missing tests: a failed test stops execution early,
    # so the tests after it are expected to be missing.
    saw_warning = False
    for success, _abstract_test_id, status_id in tests:
        if success is False:
            return StatusEnum.FAILED
        if status_id is not None:
            status = int(status_id)
            # WARNING is pass-with-warning: it must not be treated as a failure (see TestResult.warning).
            if status == StatusEnum.WARNING:
                saw_warning = True
            elif status != StatusEnum.SUCCESS:
                return StatusEnum.FAILED

    ran = {abstract_test_id for _success, abstract_test_id, _status_id in tests}
    if any(test_id not in ran for test_id in expected_test_ids):
        return StatusEnum.TEST_MISSING

    # All tests passed; surface WARNING distinctly (still a passing verdict).
    return StatusEnum.WARNING if saw_warning else StatusEnum.SUCCESS
