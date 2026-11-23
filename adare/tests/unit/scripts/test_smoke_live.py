"""scripts/smoke_live.py: run-summary verdicts and stale smoke-project cleanup (no VM)."""

import os
import time

import pytest

from .conftest import load_script

pytestmark = pytest.mark.unit

smoke = load_script('smoke_live')


def _result(*statuses: str) -> dict:
    return {
        'results': [
            {'experiment': 'test_loop_simple', 'environment': 'env', 'status': s, 'error_message': None}
            for s in statuses
        ]
    }


@pytest.mark.parametrize('statuses', [('SUCCESS',), ('SUCCESS', 'WARNING')])
def test_passing_runs(statuses):
    assert smoke.result_failures(_result(*statuses)) == []


@pytest.mark.parametrize('status', ['FAILED', 'ERROR', 'INCONCLUSIVE', 'INTERRUPTED'])
def test_any_other_status_fails(status):
    result = _result('SUCCESS', status)
    result['results'][1]['error_message'] = 'see the run log'
    assert smoke.result_failures(result) == [f'test_loop_simple on env: {status} (see the run log)']


def test_empty_summary_fails():
    assert smoke.result_failures({}) == ['the run summary has no results']
    assert smoke.result_failures({'results': []}) == ['the run summary has no results']


def test_clean_stale_removes_only_old_smoke_projects(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(smoke.subprocess, 'call', lambda cmd, **kw: calls.append(cmd) or 1)
    now = time.time()
    old = tmp_path / 'ci-smoke-1-1'
    fresh = tmp_path / 'ci-smoke-2-1'
    other = tmp_path / 'my-project'
    for path in (old, fresh, other):
        path.mkdir()
        os.utime(path, (now - 8 * 86400, now - 8 * 86400) if path != fresh else (now, now))

    assert smoke.clean_stale('adare', tmp_path, 7, now) == [old]
    assert not old.exists()
    assert fresh.exists()
    assert other.exists()
    assert calls == [['adare', 'project', 'remove', 'ci-smoke-1-1']]


def test_default_run_id_uses_the_github_run(monkeypatch):
    monkeypatch.setenv('GITHUB_RUN_ID', '123')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '2')
    assert smoke.default_run_id() == '123-2'
