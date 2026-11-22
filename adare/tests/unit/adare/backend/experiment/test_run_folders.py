"""Only clear ADARE run folders are ever selected or deleted (run/ also holds users' own files)."""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from adare.backend.experiment.run_folders import (
    DEV_SESSION_FOLDER,
    DevSessionRefs,
    RunReferencesUnavailableError,
    check_run_folder,
    folder_size,
    is_run_folder,
    map_db_run_path,
    remove_db_run_folders,
    remove_run_folder,
    scan_run_folders,
)

pytestmark = pytest.mark.unit

OLD = time.time() - 3 * 86400


def _age(path: Path, when: float = OLD) -> None:
    """Backdate ``path`` and everything under it."""
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files + dirs:
            os.utime(Path(root) / name, (when, when), follow_symlinks=False)
    os.utime(path, (when, when))


def make_run(project: Path, experiment: str, name: str, *, marker: str = 'logs', when: float = OLD) -> Path:
    folder = project / 'run' / experiment / name
    (folder / marker).mkdir(parents=True)
    (folder / marker / 'adare.log').write_text('x' * 5000)
    _age(folder, when)
    return folder


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    (root / 'experiments' / 'exp').mkdir(parents=True)
    (root / 'run').mkdir()
    return root


def test_a_real_run_folder_passes(project):
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    check = check_run_folder(project, folder)
    assert check.ok, check.reason
    assert check.resolved == folder.resolve()
    assert is_run_folder(project, folder)
    # reporting/ alone is enough; same-second suffix is part of the format
    assert is_run_folder(project, make_run(project, 'exp', '2025-01-01_00-00-00_2', marker='reporting'))


@pytest.mark.parametrize(
    ('relative', 'reason'),
    [
        # user script output: not a known experiment
        ('_p4_sample/2025-01-01_00-00-00', 'not a known experiment'),
        # wrong name
        ('exp/_c2_driver', 'not a run timestamp'),
        ('exp/2025-01-01', 'not a run timestamp'),
        ('exp/2025-01-01_00-00-00_x', 'not a run timestamp'),
    ],
)
def test_user_folders_are_refused(project, relative, reason):
    folder = project / 'run' / relative
    (folder / 'logs').mkdir(parents=True)
    _age(folder)
    check = check_run_folder(project, folder)
    assert not check.ok
    assert reason in check.reason


def test_wrong_depth_is_refused(project):
    deep = make_run(project, 'exp', '_c2_driver/2025-01-01_00-00-00')
    assert 'run/<experiment>/<timestamp>' in check_run_folder(project, deep).reason
    shallow = project / 'run' / 'exp'
    assert 'run/<experiment>/<timestamp>' in check_run_folder(project, shallow).reason


def test_missing_markers_and_fresh_folders_are_refused(project):
    bare = project / 'run' / 'exp' / '2025-01-01_00-00-00'
    (bare / 'screenshots').mkdir(parents=True)
    _age(bare)
    assert 'no logs/ or reporting/' in check_run_folder(project, bare).reason

    fresh = make_run(project, 'exp', '2025-01-02_00-00-00', when=time.time() - 60)
    assert 'less than 1 h' in check_run_folder(project, fresh).reason


def test_an_appended_log_makes_a_folder_fresh(project):
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    now = time.time()
    os.utime(folder / 'logs' / 'adare.log', (now, now))
    assert 'less than 1 h' in check_run_folder(project, folder).reason


def test_paths_outside_the_project_are_refused(project, tmp_path):
    outside = make_run(tmp_path / 'other', 'exp', '2025-01-01_00-00-00')
    assert "outside the project's run/" in check_run_folder(project, outside).reason
    traversal = project / 'run' / 'exp' / '..' / '..' / '..' / 'other' / 'run' / 'exp' / '2025-01-01_00-00-00'
    assert '..' in check_run_folder(project, traversal).reason
    assert not remove_run_folder(project, traversal).removed
    assert outside.exists()


def test_symlinks_out_of_run_are_refused(project, tmp_path):
    victim = make_run(tmp_path / 'victim', 'exp', '2025-01-01_00-00-00')
    # run/exp/<ts> -> outside
    (project / 'run' / 'exp').mkdir()
    link = project / 'run' / 'exp' / '2025-02-02_00-00-00'
    link.symlink_to(victim, target_is_directory=True)
    # run/exp2 -> outside experiment directory
    (project / 'experiments' / 'exp2').mkdir()
    (project / 'run' / 'exp2').symlink_to(victim.parent, target_is_directory=True)
    via_parent = project / 'run' / 'exp2' / '2025-01-01_00-00-00'

    for path in (link, via_parent):
        check = check_run_folder(project, path, experiments={'exp', 'exp2'})
        assert not check.ok
        assert 'symlink' in check.reason
        assert not remove_run_folder(project, path, experiments={'exp', 'exp2'}).removed
    assert victim.exists()
    assert not scan_run_folders(project, {'exp', 'exp2'})


def test_moved_project_db_paths_map_by_their_run_tail(project):
    folder = make_run(project, 'exp', '2025-01-01_00-00-00_3')
    old = '/home/someone/old-place/project/run/exp/2025-01-01_00-00-00_3'
    assert map_db_run_path(project, old) == folder
    assert map_db_run_path(project, '/home/x/project/logs/exp/ts') is None
    assert map_db_run_path(project, '/home/x/run/exp/..') is None

    (removal,) = remove_db_run_folders(project, [old])
    assert removal.removed
    assert not folder.exists()


def test_remove_db_run_folders_refuses_unmappable_paths_and_reports_missing(project):
    unmappable, missing = remove_db_run_folders(
        project, ['/etc/passwd', str(project / 'run' / 'exp' / '2025-01-01_00-00-00')]
    )
    assert not unmappable.removed
    assert 'not a run/<experiment>/<timestamp>' in unmappable.reason
    assert missing.missing
    assert not missing.removed


def test_remove_run_folder_deletes_only_valid_folders(project):
    good = make_run(project, 'exp', '2025-01-01_00-00-00')
    user = project / 'run' / '_p4_sample' / '2025-01-01_00-00-00'
    (user / 'logs').mkdir(parents=True)
    _age(user)

    assert remove_run_folder(project, good).removed
    assert not good.exists()
    refused = remove_run_folder(project, user)
    assert not refused.removed
    assert user.exists()


def test_rmtree_does_not_follow_symlinks_inside_a_run_folder(project, tmp_path):
    keep = tmp_path / 'keep'
    keep.mkdir()
    (keep / 'precious').write_text('data')
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    (folder / 'logs' / 'link').symlink_to(keep, target_is_directory=True)
    _age(folder)

    assert remove_run_folder(project, folder).removed
    assert (keep / 'precious').read_text() == 'data'


def test_remove_run_folder_keeps_a_dev_session_folder(project):
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    # A dev session of the project when it lived elsewhere: matched by its run/ tail.
    refs = DevSessionRefs(ids=frozenset({'S'}), tails=frozenset({('exp', folder.name)}))

    removal = remove_run_folder(project, folder, dev_sessions=refs)
    assert not removal.removed
    assert removal.reason == DEV_SESSION_FOLDER
    (removal,) = remove_db_run_folders(project, ['/old/project/run/exp/2025-01-01_00-00-00'], dev_sessions=refs)
    assert not removal.removed
    assert folder.exists()

    assert refs.refers_to(run_id='S')
    assert refs.refers_to(path='/x/run/exp/2025-01-01_00-00-00')
    assert not refs.refers_to(run_id='T', path=None)
    assert DevSessionRefs().with_run_paths(['/x/run/exp/a', None]).tails == {('exp', 'a')}


def test_remove_run_folder_keeps_the_folder_when_dev_sessions_cannot_be_read(project):
    folder = make_run(project, 'exp', '2025-01-01_00-00-00')
    with patch(
        'adare.backend.experiment.run_folders.load_dev_session_refs',
        side_effect=RunReferencesUnavailableError('database is locked'),
    ):
        removal = remove_run_folder(project, folder)
        (db_removal,) = remove_db_run_folders(project, [str(folder)])

    assert not removal.removed
    assert 'database is locked' in removal.reason
    assert not db_removal.removed
    assert folder.exists()


def test_scan_selects_only_run_folders_and_folder_size_counts_files(project):
    good = make_run(project, 'exp', '2025-01-01_00-00-00')
    make_run(project, 'exp', '2025-01-02_00-00-00', when=time.time())  # fresh
    make_run(project, '_p4_sample', '2025-01-01_00-00-00')  # unknown experiment
    make_run(project, 'exp', '_c2_driver')  # name mismatch
    (project / 'run' / 'exp' / 'notes.txt').write_text('mine')

    found = scan_run_folders(project, {'exp'})
    assert [check.path for check in found] == [good]
    assert folder_size(good) >= 5000
