"""Tests for the Stage 1 cache-key lock: one builder per recipe base disk.

The base cache is keyed on a hash of the build inputs, so two concurrent
``environment load`` calls over the same base do not merely race — they aim at the
same derived filename on purpose. Unlocked, that was observed as five QEMU
processes installing into one disk inode and one serial log, each one's ``--force``
unlinking the file the others were still writing to, and every survivor's
"did the install finish?" check reading the same interleaved soup.

These tests never boot a VM: the creator is patched, and the *host-side*
bookkeeping is what is under test — who waits, who reinstalls, what gets unlinked
and what does not. They exercise real ``fcntl.flock`` calls, which exclude per open
file description, so two threads in one interpreter behave like two processes.
"""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

pytestmark = pytest.mark.unit

from adare.backend.vm import recipe as recipe_module
from adare.helperfunctions.file.lock import exclusive_lock, try_exclusive_lock
from adare.hypervisor.qemu.vm_creator.base_creator import VMCreationError
from adare.types.environment import parse_environment_file

_RECIPE_MODULE = 'adare.backend.vm.recipe'
_WINDOWS_CREATOR = 'adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm'

# Anything a thread waits on: long enough never to fire on a loaded CI box, short
# enough that a genuine deadlock fails the suite instead of hanging it.
_WAIT = 30.0

_ENV = {
    'vm_type': 'recipe',
    'hypervisor': 'qemu',
    'recipe': {
        'profile': 'windows11arm64',
        'iso_sha256': None,  # filled in from the fake ISO's real digest
        'iso_name': 'Win11_25H2_English_Arm64_v2.iso',
        'template': 'autounattend_win11_arm64.xml',
        'params': {'setup_level': 2, 'disk_size': '160G'},
        'provision': [{'name': 'hardening', 'shell': 'cmd', 'command': 'bcdedit /x'}],
    },
    'os': {
        'os': 'Windows 11 (ARM64)', 'platform': 'windows', 'distribution': 'Home',
        'version': '11', 'language': 'English', 'architecture': 'aarch64',
    },
}


@pytest.fixture
def recipe_env(tmp_path, monkeypatch):
    """A parsed recipe env with every cache directory redirected into tmp_path."""
    import hashlib

    iso_dir = tmp_path / 'isos'
    iso_dir.mkdir()
    iso = iso_dir / _ENV['recipe']['iso_name']
    iso.write_bytes(b'not really a windows iso')

    env = yaml.safe_load(yaml.dump(_ENV))
    env['recipe']['iso_sha256'] = hashlib.sha256(iso.read_bytes()).hexdigest()
    env_file = tmp_path / 'win-autopsy.yml'
    env_file.write_text(yaml.dump(env))

    base_cache = tmp_path / 'recipe-bases'
    base_cache.mkdir()
    vms = tmp_path / 'vms'
    vms.mkdir()

    monkeypatch.setattr(recipe_module, 'RECIPE_BASE_CACHE_DIR', base_cache)
    monkeypatch.setattr(recipe_module, 'VMS_DIR', vms)
    monkeypatch.setattr(recipe_module, 'RECIPE_BUILD_LOG_DIR', tmp_path / 'build-logs')
    # Free-space preflight must not depend on the developer's actual disk.
    monkeypatch.setattr(recipe_module.shutil, 'disk_usage',
                        lambda p: type('U', (), {'free': 500 * 1024 ** 3})())

    return {
        'metadata': parse_environment_file(env_file),
        'env_file': env_file,
        'iso_dir': iso_dir,
        'base_cache': base_cache,
        'vms': vms,
    }


def _base_name(recipe_env) -> str:
    from adare.backend.vm.recipe import compute_base_hash
    return f'windows11arm64-recipebase-{compute_base_hash(recipe_env["metadata"])[:12]}'


def _base_path(recipe_env) -> Path:
    return recipe_env['base_cache'] / f'{_base_name(recipe_env)}.qcow2'


def _lock_path(recipe_env) -> Path:
    return recipe_env['base_cache'] / f'{_base_name(recipe_env)}.lock'


def _write_cached_base(recipe_env, marker: bytes = b'cached') -> Path:
    """Write a plausibly-sized cache entry (above the 1 MB "no OS fits" floor)."""
    base = _base_path(recipe_env)
    base.write_bytes(marker * 400_000)
    return base


def _run(recipe_env, **kwargs):
    from adare.backend.vm.recipe import build_or_reuse_recipe_vm
    return build_or_reuse_recipe_vm(
        recipe_env['metadata'],
        base_dir=recipe_env['env_file'].parent,
        iso_override=recipe_env['iso_dir'],
        **kwargs,
    )


def _stage_two_patches(vm_id: str = 'VM1'):
    """Patch out Stage 2 and registration, and the recipe-hash lookup's real DB.

    The lookup is patched because these tests run two builds concurrently, and a
    read against the developer's actual VM database from two threads is neither
    isolated nor deterministic.
    """
    return (
        patch(f'{_RECIPE_MODULE}.vm_database.get_vm_by_recipe_hash', return_value=None),
        patch(f'{_RECIPE_MODULE}._provision_disk', return_value=Path('/dev/null')),
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': vm_id, 'was_existing': False}),
    )


# --- the lock itself ---

def test_flock_excludes_a_second_holder_within_one_process(tmp_path):
    """The assumption the rest of this file rests on.

    ``flock`` locks the open file *description*, not the process, so a second
    ``os.open`` of the same path is excluded — which is what makes a two-thread test
    a faithful stand-in for two ``adare`` processes.
    """
    lock_path = tmp_path / 'x.lock'
    with exclusive_lock(lock_path), try_exclusive_lock(lock_path) as acquired:
        assert acquired is False
    with try_exclusive_lock(lock_path) as acquired:
        assert acquired is True, 'the lock was not released when the block exited'


def test_the_contention_callback_runs_once_before_blocking(tmp_path):
    """A silent multi-minute wait is indistinguishable from a hang."""
    lock_path = tmp_path / 'x.lock'
    calls = []
    holder_has_it = threading.Event()
    release = threading.Event()

    def _hold():
        with exclusive_lock(lock_path):
            holder_has_it.set()
            release.wait(_WAIT)

    holder = threading.Thread(target=_hold, daemon=True)
    holder.start()
    assert holder_has_it.wait(_WAIT)

    threading.Timer(0.2, release.set).start()
    with exclusive_lock(lock_path, on_contention=lambda: calls.append(1)):
        pass
    holder.join(_WAIT)

    assert calls == [1], 'the waiter did not announce exactly one wait'


def test_an_uncontended_lock_does_not_announce_a_wait(tmp_path):
    calls = []
    with exclusive_lock(tmp_path / 'x.lock', on_contention=lambda: calls.append(1)):
        pass
    assert calls == []


# --- Stage 1 under concurrency ---

def test_a_second_builder_waits_instead_of_clobbering_the_first(recipe_env, capsys):
    """The original defect, end to end.

    Two builds of the same base start; the second must block on the lock, leave the
    first one's in-progress disk alone, and never start an install of its own.
    """
    install_started = threading.Event()
    may_finish = threading.Event()
    creator_calls: list[dict] = []
    partial_disk: list[Path] = []

    def _creator(**kwargs):
        creator_calls.append(kwargs)
        if len(creator_calls) > 1:  # pragma: no cover - the assertion
            raise AssertionError('a second OS install started for the same base')
        disk = kwargs['vm_dir'] / f"{kwargs['vm_name']}.qcow2"
        disk.write_bytes(b'q')  # what `qemu-img create` leaves behind, seconds in
        partial_disk.append(disk)
        install_started.set()
        assert may_finish.wait(_WAIT), 'the test never released the first builder'
        disk.write_bytes(b'i' * 2_000_000)
        return disk

    results: dict[str, object] = {}

    def _build(tag: str) -> None:
        try:
            results[tag] = _run(recipe_env)
        except (AssertionError, VMCreationError, OSError) as e:
            results[tag] = e

    lookup, provision, register = _stage_two_patches()
    with patch(_WINDOWS_CREATOR, side_effect=_creator), lookup, provision, register:
        first = threading.Thread(target=_build, args=('first',), daemon=True)
        first.start()
        assert install_started.wait(_WAIT), 'the first build never reached the creator'

        with try_exclusive_lock(_lock_path(recipe_env)) as acquired:
            assert acquired is False, 'the running build does not hold its cache lock'

        second = threading.Thread(target=_build, args=('second',), daemon=True)
        second.start()
        second.join(timeout=1.0)
        assert second.is_alive(), 'the second builder did not wait for the lock'
        assert partial_disk[0].exists(), "the second builder unlinked the first's disk"
        assert len(creator_calls) == 1

        may_finish.set()
        first.join(_WAIT)
        second.join(_WAIT)

    assert not first.is_alive() and not second.is_alive(), 'a build never finished'
    assert results['first'] == {'vm_id': 'VM1', 'was_existing': False}
    assert results['second'] == {'vm_id': 'VM1', 'was_existing': False}
    # One install, one publish — the point of locking rather than using unique paths.
    assert len(creator_calls) == 1
    assert _base_path(recipe_env).is_file()
    assert 'Another ADARE process' in capsys.readouterr().out


def test_the_waiter_reuses_the_base_the_first_builder_published(recipe_env):
    """Re-checking the cache after acquiring is what collapses the pile-up.

    Without it, every process queued behind a build inherits its turn and installs
    an OS that is by then sitting in the cache.
    """
    holder_has_it = threading.Event()
    release = threading.Event()

    def _hold_like_a_running_build():
        with exclusive_lock(_lock_path(recipe_env)):
            holder_has_it.set()
            release.wait(_WAIT)

    holder = threading.Thread(target=_hold_like_a_running_build, daemon=True)
    holder.start()
    assert holder_has_it.wait(_WAIT)

    # Published while the waiter is queued behind the lock, exactly as a finishing
    # build would publish it.
    _write_cached_base(recipe_env)

    def _must_not_run(**kwargs):  # pragma: no cover - the assertion
        raise AssertionError('the waiter reinstalled a base that was already cached')

    threading.Timer(0.2, release.set).start()
    lookup, provision, register = _stage_two_patches(vm_id='VM2')
    with patch(_WINDOWS_CREATOR, side_effect=_must_not_run), lookup, provision, register:
        result = _run(recipe_env)
    holder.join(_WAIT)

    assert result == {'vm_id': 'VM2', 'was_existing': False}


def test_force_does_not_accept_a_base_published_while_it_waited(recipe_env):
    """``--force`` means "this base is not to be trusted", including a brand-new one.

    The re-check after acquiring must therefore be skipped under ``force``, or the
    flag silently becomes a no-op whenever another build has just finished.
    """
    holder_has_it = threading.Event()
    release = threading.Event()

    def _hold_like_a_running_build():
        with exclusive_lock(_lock_path(recipe_env)):
            holder_has_it.set()
            release.wait(_WAIT)

    holder = threading.Thread(target=_hold_like_a_running_build, daemon=True)
    holder.start()
    assert holder_has_it.wait(_WAIT)
    _write_cached_base(recipe_env)

    def _rebuild(**kwargs):
        disk = kwargs['vm_dir'] / f"{kwargs['vm_name']}.qcow2"
        disk.write_bytes(b'r' * 2_000_000)
        return disk

    threading.Timer(0.2, release.set).start()
    lookup, provision, register = _stage_two_patches(vm_id='VM3')
    with patch(_WINDOWS_CREATOR, side_effect=_rebuild) as creator, lookup, provision, register:
        _run(recipe_env, force=True)
    holder.join(_WAIT)

    creator.assert_called_once()
    assert _base_path(recipe_env).read_bytes()[:1] == b'r', 'the forced rebuild was skipped'


# --- per-attempt artifacts and the lock file's lifetime ---

def test_each_attempt_gets_its_own_install_log(recipe_env):
    """The serial log is derived from the disk name, so the name must be per-attempt.

    QEMU opens ``-serial file:…`` with O_TRUNC and holds an independent offset, so a
    shared name gave N writers one interleaved log — and ``_assert_install_succeeded``
    greps that log to decide whether the install finished. A per-attempt log is also
    what leaves the failed attempt's evidence readable after a retry.
    """
    names: list[str] = []

    def _attempt(**kwargs):
        names.append(kwargs['vm_name'])
        disk = kwargs['vm_dir'] / f"{kwargs['vm_name']}.qcow2"
        disk.write_bytes(b'x' * 2_000_000)
        # Stand in for `-serial file:{stem}_install.log`, as linux_creator names it.
        (kwargs['vm_dir'] / f"{kwargs['vm_name']}_install.log").write_text(
            f'attempt {len(names)}\n'
        )
        if len(names) == 1:
            raise VMCreationError('simulated installer failure')
        return disk

    lookup, provision, register = _stage_two_patches()
    with patch(_WINDOWS_CREATOR, side_effect=_attempt), lookup, provision, register:
        with pytest.raises(VMCreationError):
            _run(recipe_env)
        _run(recipe_env)

    assert names[0] != names[1], 'two attempts shared one install log'
    assert all('.partial-' in name for name in names)

    base_name = _base_name(recipe_env)
    logs = {p.name for p in recipe_env['base_cache'].glob('*_install.log')}
    # The successful attempt's log is published under the cache name (unchanged
    # behaviour); the failed attempt's is kept for post-mortem.
    assert f'{base_name}_install.log' in logs
    assert f'{names[0]}_install.log' in logs
    assert (recipe_env['base_cache'] / f'{base_name}_install.log').read_text() == 'attempt 2\n'
    # ... while its multi-GB partial disk is reclaimed, under the lock, by the retry.
    assert not list(recipe_env['base_cache'].glob('*.partial-*.qcow2'))


def test_a_normal_build_no_longer_forces_the_creator(recipe_env):
    """``force=True`` used to be hardcoded here, which is what armed the unlink.

    ``BaseVMCreator._create_disk`` refuses to overwrite an existing disk unless
    forced. That refusal is an accidental second line of defence against exactly
    this bug, so a plain build must pass the caller's ``force`` through.
    """
    def _creator(**kwargs):
        disk = kwargs['vm_dir'] / f"{kwargs['vm_name']}.qcow2"
        disk.write_bytes(b'n' * 2_000_000)
        return disk

    lookup, provision, register = _stage_two_patches()
    with patch(_WINDOWS_CREATOR, side_effect=_creator) as creator, lookup, provision, register:
        _run(recipe_env)

    assert creator.call_args.kwargs['force'] is False


def test_the_lock_file_survives_the_build(recipe_env):
    """Unlinking a locked file silently ends the exclusion — so it is never removed.

    The next process would ``open`` a different inode, its ``flock`` would succeed
    at once, and two builders would proceed with everything looking correct.
    """
    def _creator(**kwargs):
        disk = kwargs['vm_dir'] / f"{kwargs['vm_name']}.qcow2"
        disk.write_bytes(b'l' * 2_000_000)
        return disk

    lookup, provision, register = _stage_two_patches()
    with patch(_WINDOWS_CREATOR, side_effect=_creator), lookup, provision, register:
        _run(recipe_env)

    assert _lock_path(recipe_env).is_file(), 'the lock file was removed after the build'


def test_a_cache_hit_takes_no_lock_at_all(recipe_env):
    """The fast path is read-only, so it must not queue behind anything."""
    _write_cached_base(recipe_env)

    def _must_not_run(**kwargs):  # pragma: no cover - the assertion
        raise AssertionError('a cache hit reached the installer')

    lookup, provision, register = _stage_two_patches()
    with patch(_WINDOWS_CREATOR, side_effect=_must_not_run), lookup, provision, register:
        _run(recipe_env)

    assert not _lock_path(recipe_env).exists()


# --- `vm prune` must not reclaim a running install's disk ---

def test_prune_leaves_an_in_progress_partial_build_alone(tmp_path, monkeypatch, capsys):
    """`prune --force` used to unlink the disk of every running Stage 1.

    Its glob matches the partial disk too, and the "hash" parsed out of that name
    can never match a live environment — so a running install was always classified
    stale. Unlinking it drops the live QEMU onto an unlinked inode: the install runs
    to completion and then the disk is simply gone, with no error anywhere.
    """
    from adare.cli import vm as vm_cli
    from adare.config import configdirectory

    cache = tmp_path / 'recipe-bases'
    cache.mkdir()
    disks = tmp_path / 'vms'
    disks.mkdir()
    in_progress = cache / 'windows11arm64-recipebase-abcdef123456.partial-4242-9f.qcow2'
    in_progress.write_bytes(b'p' * 2048)
    truly_stale = cache / 'windows11arm64-recipebase-0badc0ffee00.qcow2'
    truly_stale.write_bytes(b's' * 2048)

    monkeypatch.setattr(configdirectory, 'RECIPE_BASE_CACHE_DIR', cache)
    monkeypatch.setattr(vm_cli, '_live_recipe_base_hashes', lambda: set())
    monkeypatch.setattr(
        'adare.hypervisor.qemu.mixins.configuration.get_qemu_disk_dir', lambda: disks)

    class _FakeVmApi:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_all_vms(self):
            return []

        def get_all_vm_instances(self):
            return []

    monkeypatch.setattr('adare.database.api.vm.VmApi', _FakeVmApi)

    arguments = type('Args', (), {'dry_run': False, 'sockets': False})()
    vm_cli.exec_vm_prune(arguments)

    assert in_progress.exists(), 'prune unlinked an in-progress base build'
    assert not truly_stale.exists(), 'prune stopped reclaiming genuinely stale bases'
    assert in_progress.name not in capsys.readouterr().out
