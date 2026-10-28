"""`adare runs prune` / `runs remove --keep-files` pass the right request and render the result."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from adare.core.dto.show import RunPruneEntry, RunPruneResult, RunRemoveResult
from adare.core.result import Result

pytestmark = pytest.mark.unit


def _invoke(*args):
    from adare.run import cli

    return CliRunner().invoke(cli, ['runs', *args])


def _api(prune_result=None, remove_result=None):
    api = MagicMock()
    api.show.prune_runs.return_value = Result.ok(prune_result)
    api.show.remove_run.return_value = Result.ok(remove_result)
    return api


def test_prune_defaults_to_a_dry_run_and_prints_json():
    data = RunPruneResult(
        project_path='/p',
        dry_run=True,
        entries=[
            RunPruneEntry(kind='orphan', experiment='exp', folder='/p/run/exp/2025-01-01_00-00-00', size_bytes=42)
        ],
    )
    api = _api(prune_result=data)
    with patch('adare.cli.show.AdareAPI', return_value=api):
        result = _invoke('prune', '--json')

    assert result.exit_code == 0, result.output
    request = api.show.prune_runs.call_args.args[0]
    assert (request.execute, request.fake, request.older_than_days) == (False, False, None)
    payload = json.loads(result.output)
    assert payload['dry_run'] is True
    assert payload['total_bytes'] == 42


def test_prune_flags_reach_the_request():
    api = _api(prune_result=RunPruneResult(project_path='/p', dry_run=False))
    with patch('adare.cli.show.AdareAPI', return_value=api):
        result = _invoke('prune', '--fake', '--older-than', '7', '--yes')

    assert result.exit_code == 0, result.output
    request = api.show.prune_runs.call_args.args[0]
    assert (request.execute, request.fake, request.older_than_days) == (True, True, 7.0)


def test_remove_keep_files_reaches_the_request():
    api = _api(remove_result=RunRemoveResult(removed=True, ulid='U', folder='/p/run/e/t', folder_note='kept'))
    with patch('adare.cli.show.AdareAPI', return_value=api):
        result = _invoke('remove', 'U', '--keep-files')

    assert result.exit_code == 0, result.output
    assert api.show.remove_run.call_args.args[0].keep_files is True


@pytest.mark.parametrize('dry_run', [True, False])
def test_prune_renders_a_table(dry_run):
    entries = [
        RunPruneEntry(
            kind='orphan',
            experiment='exp',
            folder='/p/run/exp/a',
            size_bytes=2048,
            removed=not dry_run,
            folder_removed=not dry_run,
        ),
        RunPruneEntry(kind='fake', experiment='exp', run_ulid='R', note='folder kept: changed less than 1 h ago'),
    ]
    api = _api(prune_result=RunPruneResult(project_path='/p', dry_run=dry_run, entries=entries, rows_deleted=1))
    with patch('adare.cli.show.AdareAPI', return_value=api):
        result = _invoke('prune', '--format', 'rich')

    assert result.exit_code == 0, result.output
    assert ('Nothing was deleted' in result.output) is dry_run
