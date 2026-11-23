"""`adare experiment run` exit codes: 0 all passed, 1 any run did not pass, 130 interrupted."""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adare.backend.experiment.batch_runner import BatchRunSummary, ExperimentResult
from adare.cli import experiment as cli_experiment
from adarelib.constants import StatusEnum

OK, FAIL, ERR, INC, INT = (
    StatusEnum.SUCCESS,
    StatusEnum.FAILED,
    StatusEnum.ERROR,
    StatusEnum.INCONCLUSIVE,
    StatusEnum.INTERRUPTED,
)
PROJECT = Path('/nonexistent/project')


def _summary(*statuses):
    results = [
        ExperimentResult(environment=f'env{i}', experiment='exp', status=s, duration=timedelta(seconds=1))
        for i, s in enumerate(statuses)
    ]
    return BatchRunSummary(results=results, total_combinations=len(results), total_duration=timedelta(seconds=1))


@pytest.mark.parametrize(
    ('statuses', 'code'),
    [
        ((OK, OK), 0),
        ((OK, FAIL), 1),
        ((ERR,), 1),
        ((INC,), 1),
        ((OK, INT), 130),
        ((FAIL, INT), 1),
        ((), 1),
    ],
)
def test_summary_exit_code(statuses, code):
    assert _summary(*statuses).exit_code == code


def _arguments(environment):
    return SimpleNamespace(
        experiment='exp',
        environment=environment,
        project=None,
        test=False,
        verbose=True,
        very_verbose=False,
        debug_screenshots=False,
        preserve_snapshot=False,
        runlog=False,
        vm_memory=None,
        vm_cpus=None,
        gui_mode=None,
    )


def _formatter(fmt):
    """A formatter mock: ``rich`` (summary not printed by the CLI) or ``json`` to an output file."""
    formatter = MagicMock()
    formatter.format_type.value = fmt
    output_file = None if fmt == 'rich' else Path('/nonexistent/summary.json')
    return formatter, output_file, False


def _common_patches(environment, formatter):
    return (
        patch.object(cli_experiment, 'determine_projectdirectory', return_value=PROJECT),
        patch.object(cli_experiment, 'resolve_experiment_path', return_value='exp'),
        patch.object(cli_experiment, 'resolve_environment_path', return_value=environment),
        patch('adare.backend.experiment.commands.experiment_load'),
        patch('adare.run.get_formatter_from_context', return_value=formatter),
    )


def _run_single(outcome, fmt):
    """Run the single-environment path with ``experiment_run`` returning ``outcome``.

    ``outcome``: ``(was_interrupted, was_successful, verdict)`` or an exception to raise.
    """

    async def fake_run(*args, verdict_out, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        was_interrupted, was_successful, verdict = outcome
        verdict_out.update(verdict)
        return was_interrupted, was_successful

    api = MagicMock()
    api.__enter__.return_value = api
    api.get_environment.return_value = SimpleNamespace(id=1)
    api.get_experiment.return_value = SimpleNamespace(id=2)
    formatter = _formatter(fmt)
    p1, p2, p3, p4, p5 = _common_patches('env', formatter)
    with (
        p1,
        p2,
        p3,
        p4,
        p5,
        patch('adare.database.api.experiment.ExperimentApi', return_value=api),
        patch('adare.backend.experiment.run.experiment_run', side_effect=fake_run),
        pytest.raises(SystemExit) as exit_info,
    ):
        cli_experiment.exec_experiment_run(_arguments('env'))
    return exit_info.value.code, formatter[0]


@pytest.mark.parametrize('fmt', ['rich', 'json'])
@pytest.mark.parametrize(
    ('outcome', 'code', 'status'),
    [
        ((False, True, {'verdict': 'SUCCESS'}), 0, 'SUCCESS'),
        ((False, False, {'verdict': 'FAILED'}), 1, 'FAILED'),
        ((False, False, {'verdict': 'INCONCLUSIVE'}), 1, 'INCONCLUSIVE'),
        ((True, False, {}), 130, 'INTERRUPTED'),
    ],
)
def test_single_environment_exit_code(outcome, code, status, fmt):
    exit_code, formatter = _run_single(outcome, fmt)

    assert exit_code == code
    if fmt == 'rich':
        formatter.print_or_save.assert_not_called()
    else:
        summary = formatter.print_or_save.call_args.args[0]
        assert [r['status'] for r in summary['results']] == [status]


def test_single_environment_ctrl_c_exits_130():
    exit_code, _ = _run_single(KeyboardInterrupt(), 'rich')

    assert exit_code == 130


def _run_batch(**batch_patch):
    p1, p2, p3, p4, p5 = _common_patches(None, _formatter('json'))
    with (
        p1,
        p2,
        p3,
        p4,
        p5,
        patch('adare.backend.experiment.batch_runner.run_batch_experiments', new=AsyncMock(**batch_patch)),
        pytest.raises(SystemExit) as exit_info,
    ):
        cli_experiment.exec_experiment_run(_arguments(None))
    return exit_info.value.code


@pytest.mark.parametrize(('statuses', 'code'), [((OK, ERR), 1), ((OK, OK), 0), ((OK, INT), 130)])
def test_batch_exit_code(statuses, code):
    assert _run_batch(return_value=_summary(*statuses)) == code


def test_batch_ctrl_c_exits_130():
    assert _run_batch(side_effect=KeyboardInterrupt) == 130
