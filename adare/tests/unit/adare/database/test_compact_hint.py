"""The `adare db compact` hint: when it fires (adare.database.compact_hint) and how the CLI prints it."""

import io
import json
import sqlite3
import uuid
from contextlib import closing

import pytest
from click.testing import CliRunner

from adare.database import compact_hint, maintenance
from adare.database.api.base import ProjectDatabaseApi, dispose_engines

pytestmark = pytest.mark.unit

# Stands in for the 512 MiB threshold: the empty schema is ~200 KiB, one bulky row 300 KiB.
MIN_BYTES = 400 * 1024
BULKY = json.dumps({'image': {'data': 'A' * 300_000, 'format': 'png'}})


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Small threshold, no queued hints before or after, no dev sessions for compact."""
    monkeypatch.setattr(compact_hint, 'HINT_MIN_BYTES', MIN_BYTES)
    monkeypatch.setattr(maintenance, '_default_global_db_path', lambda: tmp_path / 'no-global.db')
    compact_hint.clear_hints()
    yield
    compact_hint.clear_hints()


def _insert(db_path, *results: str) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.executemany(
            "INSERT INTO action_execution (id, playbook_item_id, status, result_data) VALUES (?, 'item', 'success', ?)",
            [(uuid.uuid4().hex, result) for result in results],
        )


def _project(tmp_path, *results: str):
    """A project database holding ``results`` as ``action_execution.result_data``; no hint queued yet."""
    project = tmp_path / 'proj'
    db_path = ProjectDatabaseApi(project).db_path
    dispose_engines()
    compact_hint.clear_hints()
    _insert(db_path, *results)
    return project, db_path


def _open(project) -> list[compact_hint.CompactHint]:
    """Open the project's database as a fresh process would; the hints queued by now."""
    dispose_engines()
    ProjectDatabaseApi(project)
    return compact_hint.pending_hints()


def _marker(db_path):
    return json.loads(compact_hint.marker_path(db_path).read_text())['size']


@pytest.mark.skipif(sqlite3.sqlite_version_info < (3, 43), reason='octet_length needs SQLite >= 3.43')
def test_octet_length_is_available_in_the_bundled_sqlite():
    with closing(sqlite3.connect(':memory:')) as conn:
        assert conn.execute("SELECT octet_length('abc')").fetchone()[0] == 3


def test_a_bulky_database_above_the_size_threshold_gets_a_hint(tmp_path):
    project, db_path = _project(tmp_path, BULKY, BULKY)

    hints = _open(project)

    assert [(h.project_path, h.db_path) for h in hints] == [(project, db_path)]
    assert 'adare db compact -p' in hints[0].message() and str(project) in hints[0].message()
    assert not compact_hint.marker_path(db_path).exists()  # written once the hint is shown


def test_a_small_database_gets_no_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(compact_hint, 'HINT_MIN_BYTES', 10 * MIN_BYTES)
    project, db_path = _project(tmp_path, BULKY, BULKY)

    assert _open(project) == []
    assert not compact_hint.marker_path(db_path).exists()  # below the size threshold: nothing read


def test_a_large_database_without_bulky_results_gets_no_hint(tmp_path):
    project, db_path = _project(tmp_path, *[json.dumps({'out': 'x' * 200_000})] * 3)

    assert _open(project) == []
    # Settled at this size: the row query does not run again until the file grows by half.
    assert _marker(db_path) == db_path.stat().st_size


def test_the_probe_falls_back_to_the_blob_length_without_octet_length(tmp_path, monkeypatch):
    _root, db_path = _project(tmp_path, BULKY)
    # SQLite < 3.43 answers "no such function: octet_length".
    monkeypatch.setattr(compact_hint, '_PROBE_OCTET_LENGTH', 'SELECT octet_length_unavailable(?)')

    assert compact_hint._has_large_result(db_path) is True


def test_the_blob_length_fallback_ignores_small_results(tmp_path, monkeypatch):
    _root, db_path = _project(tmp_path, '{"x": 1}')
    monkeypatch.setattr(compact_hint, '_PROBE_OCTET_LENGTH', 'SELECT octet_length_unavailable(?)')

    assert compact_hint._has_large_result(db_path) is False


def test_any_other_probe_error_means_no_hint(tmp_path, monkeypatch):
    _root, db_path = _project(tmp_path, BULKY)
    monkeypatch.setattr(compact_hint, '_PROBE_OCTET_LENGTH', 'SELECT no_such_function(?)')

    with pytest.raises(sqlite3.OperationalError):
        compact_hint._has_large_result(db_path)
    assert compact_hint.needs_compact(db_path) is False


def test_the_hint_fires_once_then_again_after_the_database_grew_by_half(tmp_path):
    project, db_path = _project(tmp_path, BULKY, BULKY)
    assert len(_open(project)) == 1

    compact_hint.emit_hints(io.StringIO())

    assert compact_hint.pending_hints() == []
    shown_at = _marker(db_path)
    assert shown_at == db_path.stat().st_size
    assert _open(project) == []  # same size: the marker holds it back

    while db_path.stat().st_size < shown_at * compact_hint.HINT_GROWTH_FACTOR:
        _insert(db_path, BULKY)
    assert len(_open(project)) == 1


def test_no_hint_after_compact_wrote_the_marker(tmp_path):
    project, db_path = _project(tmp_path, BULKY, BULKY)
    assert len(_open(project)) == 1  # queued in this process ...

    entry = maintenance.compact_database(maintenance.project_target(project))

    assert entry.status == 'compacted'
    assert compact_hint.pending_hints() == []  # ... and dropped by the compact
    assert _marker(db_path) == db_path.stat().st_size
    assert _open(project) == []


def test_a_dry_run_compact_writes_no_marker(tmp_path):
    project, db_path = _project(tmp_path, BULKY, BULKY)

    maintenance.compact_database(maintenance.project_target(project), dry_run=True)

    assert not compact_hint.marker_path(db_path).exists()


def test_an_unreadable_database_gets_no_hint(tmp_path):
    db_path = tmp_path / 'project.db.sqlite3'
    db_path.write_bytes(b'not a database' * 50_000)

    assert compact_hint.needs_compact(db_path) is False


def test_maintenance_re_exports_needs_compact():
    assert maintenance.needs_compact is compact_hint.needs_compact


# --- printed by the CLI -------------------------------------------------------


def _run_cli(*args):
    from adare.run import cli

    return CliRunner().invoke(cli, list(args))


def test_the_cli_prints_a_queued_hint_once_on_stderr(tmp_path):
    project, db_path = _project(tmp_path, BULKY, BULKY)
    [hint] = _open(project)

    first = _run_cli('--format', 'plain', 'icons', 'list')
    second = _run_cli('--format', 'plain', 'icons', 'list')

    assert first.exit_code == 0, first.output
    assert 'adare db compact' in first.stderr and 'adare db compact' not in first.stdout
    assert 'adare db compact' not in second.stderr
    assert _marker(db_path) == hint.size  # the size the hint was given at (optimize may add stat pages)


def test_the_cli_holds_the_hint_back_for_json_output(tmp_path):
    project, db_path = _project(tmp_path, BULKY, BULKY)
    _open(project)

    result = _run_cli('icons', 'list', '--json')

    assert result.exit_code == 0, result.output
    assert 'adare db compact' not in result.stderr
    json.loads(result.stdout)
    assert len(compact_hint.pending_hints()) == 1  # kept for the next interactive command
    assert not compact_hint.marker_path(db_path).exists()
