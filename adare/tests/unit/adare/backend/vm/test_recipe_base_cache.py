"""Tests for the Stage 1 base-disk cache and the reprovision/force flags (T9).

The cache is what makes provisioning affordable: without it a failed MSI on step
40 of 49 costs another two-hour Windows install, and the solr4 / solr8 pair costs
two installs instead of one. These tests assert the OS installer is *not* invoked
when it must not be — by patching it to raise.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

pytestmark = pytest.mark.unit

from adare.backend.environment.exceptions import EnvironmentLoadFailed
from adare.backend.vm import recipe as recipe_module
from adare.types.environment import parse_environment_file

_RECIPE_MODULE = 'adare.backend.vm.recipe'

_ENV = {
    'vm_type': 'recipe',
    'hypervisor': 'qemu',
    'recipe': {
        'profile': 'windows11arm64',
        'iso_sha256': None,  # filled in per test from the fake ISO's real digest
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
    """A parsed provision-bearing recipe env with isolated dirs and a real ISO digest."""
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
    logs = tmp_path / 'build-logs'

    monkeypatch.setattr(recipe_module, 'RECIPE_BASE_CACHE_DIR', base_cache)
    monkeypatch.setattr(recipe_module, 'VMS_DIR', vms)
    monkeypatch.setattr(recipe_module, 'RECIPE_BUILD_LOG_DIR', logs)
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


def _base_path(recipe_env) -> Path:
    from adare.backend.vm.recipe import compute_base_hash
    base_hash = compute_base_hash(recipe_env['metadata'])
    return recipe_env['base_cache'] / f'windows11arm64-recipebase-{base_hash[:12]}.qcow2'


def _write_cached_base(recipe_env, marker: bytes = b'cached') -> Path:
    """Write a plausibly-sized cached base disk.

    Must exceed the 1 MB floor `_build_base_disk` uses to reject the OS-less
    `qemu-img create` shell an interrupted Stage 1 leaves behind.
    """
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


# --- T9: the base cache ---

def test_a_present_base_disk_is_reused_without_invoking_the_installer(recipe_env):
    """Patch the creators to raise: a cache hit must never reach them."""
    _write_cached_base(recipe_env)

    def _must_not_run(**kwargs):  # pragma: no cover - the assertion
        raise AssertionError('the OS installer was invoked despite a base cache hit')

    with (
        patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
              side_effect=_must_not_run),
        patch('adare.hypervisor.qemu.vm_creator.linux_creator.create_linux_vm',
              side_effect=_must_not_run),
        patch(f'{_RECIPE_MODULE}._provision_disk',
              return_value=recipe_env['vms'] / 'out.qcow2') as provision,
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'VM1', 'was_existing': False}),
    ):
        result = _run(recipe_env)

    assert result['vm_id'] == 'VM1'
    provision.assert_called_once()
    # Stage 2 was handed the cached base, not a freshly built disk.
    assert provision.call_args.args[0] == _base_path(recipe_env)


def test_an_interrupted_build_does_not_poison_the_cache(recipe_env):
    """A killed Stage 1 must leave NO cache entry, only a `.partial`.

    Regression test for an observed defect: the creator's first act is
    `qemu-img create`, so a build killed any time afterwards used to leave an
    OS-less qcow2 at exactly the path later builds treat as a hit. They then
    skipped the install and failed 15 minutes later with a misleading "the guest
    agent did not respond".
    """
    base = _base_path(recipe_env)
    partial = base.with_name(base.name.replace('.qcow2', '.partial.qcow2'))

    def _killed_mid_install(**kwargs):
        # What the creator has done by the time it is interrupted.
        Path(kwargs['vm_dir'] / f"{kwargs['vm_name']}.qcow2").write_bytes(b'x' * 196_928)
        raise KeyboardInterrupt('simulated SIGINT during the OS install')

    with patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
               side_effect=_killed_mid_install):
        with pytest.raises(KeyboardInterrupt):
            _run(recipe_env)

    assert not base.exists(), 'an interrupted build published a cache entry'
    assert partial.exists(), 'the partial build should remain for inspection'


def test_the_installer_writes_to_a_partial_path_not_the_cache_name(recipe_env):
    """The cache name is only ever produced by the rename."""
    seen = {}

    def _record(**kwargs):
        seen['vm_name'] = kwargs['vm_name']
        built = kwargs['vm_dir'] / f"{kwargs['vm_name']}.qcow2"
        built.write_bytes(b'y' * 2_000_000)
        return built

    with (
        patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
              side_effect=_record),
        patch(f'{_RECIPE_MODULE}._provision_disk',
              return_value=recipe_env['vms'] / 'out.qcow2'),
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'VM1', 'was_existing': False}),
    ):
        _run(recipe_env)

    assert seen['vm_name'].endswith('.partial')
    # ... and after a successful build the cache entry exists under the real name.
    assert _base_path(recipe_env).is_file()
    assert not _base_path(recipe_env).with_name(
        _base_path(recipe_env).name.replace('.qcow2', '.partial.qcow2')).exists()


def test_a_truncated_cached_base_is_discarded_and_rebuilt(recipe_env):
    """Defence in depth for caches poisoned before the rename existed."""
    _base_path(recipe_env).write_bytes(b'z' * 196_928)  # the real observed size

    def _rebuild(**kwargs):
        built = kwargs['vm_dir'] / f"{kwargs['vm_name']}.qcow2"
        built.write_bytes(b'w' * 2_000_000)
        return built

    with (
        patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
              side_effect=_rebuild) as creator,
        patch(f'{_RECIPE_MODULE}._provision_disk',
              return_value=recipe_env['vms'] / 'out.qcow2'),
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'VM1', 'was_existing': False}),
    ):
        _run(recipe_env)

    creator.assert_called_once()
    assert _base_path(recipe_env).stat().st_size == 2_000_000


def test_a_plausibly_sized_cached_base_is_still_reused(recipe_env):
    """The size floor must not reject a legitimately small-but-real base."""
    _base_path(recipe_env).write_bytes(b'q' * 1_000_001)

    def _must_not_run(**kwargs):  # pragma: no cover
        raise AssertionError('a valid cached base was discarded')

    with (
        patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
              side_effect=_must_not_run),
        patch(f'{_RECIPE_MODULE}._provision_disk',
              return_value=recipe_env['vms'] / 'out.qcow2'),
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'VM1', 'was_existing': False}),
    ):
        _run(recipe_env)


def test_an_absent_base_disk_triggers_the_installer(recipe_env):
    built = _base_path(recipe_env)

    def _fake_build(**kwargs):
        built.write_bytes(b'freshly installed')
        return built

    with (
        patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
              side_effect=_fake_build) as creator,
        patch(f'{_RECIPE_MODULE}._provision_disk',
              return_value=recipe_env['vms'] / 'out.qcow2'),
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'VM1', 'was_existing': False}),
    ):
        _run(recipe_env)

    creator.assert_called_once()
    assert creator.call_args.kwargs['vm_dir'] == recipe_env['base_cache']
    assert creator.call_args.kwargs['vm_name'].startswith('windows11arm64-recipebase-')


def test_reprovision_keeps_the_cached_base(recipe_env):
    """The retry path: redo Stage 2 only. An OS reinstall here defeats the point."""
    _write_cached_base(recipe_env)

    def _must_not_run(**kwargs):  # pragma: no cover
        raise AssertionError('--reprovision rebuilt the base disk')

    with (
        patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
              side_effect=_must_not_run),
        patch(f'{_RECIPE_MODULE}._provision_disk',
              return_value=recipe_env['vms'] / 'out.qcow2') as provision,
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'VM2', 'was_existing': False}),
    ):
        _run(recipe_env, reprovision=True)

    provision.assert_called_once()


def test_force_rebuilds_the_base_too(recipe_env):
    _write_cached_base(recipe_env, b'stale')
    built = _base_path(recipe_env)

    with (
        patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
              return_value=built) as creator,
        patch(f'{_RECIPE_MODULE}._provision_disk',
              return_value=recipe_env['vms'] / 'out.qcow2'),
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'VM3', 'was_existing': False}),
    ):
        _run(recipe_env, force=True)

    creator.assert_called_once()
    assert creator.call_args.kwargs['force'] is True


def test_reprovision_bypasses_the_registered_vm_cache(recipe_env):
    """A recipe-hash cache hit would otherwise short-circuit the whole build."""
    _write_cached_base(recipe_env)
    existing = type('Vm', (), {
        'id': 'OLD', 'name': 'old-vm', 'file': str(recipe_env['vms'] / 'old.qcow2'),
    })()
    (recipe_env['vms'] / 'old.qcow2').write_bytes(b'previously built')

    with (
        patch(f'{_RECIPE_MODULE}.vm_database.get_vm_by_recipe_hash', return_value=existing),
        patch(f'{_RECIPE_MODULE}._provision_disk',
              return_value=recipe_env['vms'] / 'out.qcow2') as provision,
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'NEW', 'was_existing': False}),
    ):
        result = _run(recipe_env, reprovision=True)

    provision.assert_called_once()
    assert result['vm_id'] == 'NEW'


def test_a_registered_vm_with_a_present_disk_short_circuits_everything(recipe_env):
    existing = type('Vm', (), {
        'id': 'OLD', 'name': 'old-vm', 'file': str(recipe_env['vms'] / 'old.qcow2'),
    })()
    (recipe_env['vms'] / 'old.qcow2').write_bytes(b'previously built')

    def _must_not_run(*args, **kwargs):  # pragma: no cover
        raise AssertionError('a recipe cache hit still tried to build')

    with (
        patch(f'{_RECIPE_MODULE}.vm_database.get_vm_by_recipe_hash', return_value=existing),
        patch(f'{_RECIPE_MODULE}._provision_disk', side_effect=_must_not_run),
        patch(f'{_RECIPE_MODULE}._build_base_disk', side_effect=_must_not_run),
    ):
        result = _run(recipe_env)

    assert result == {'vm_id': 'OLD', 'was_existing': True}


# --- preflight: fail before any build starts ---

def test_setup_level_bare_with_provision_is_rejected_before_building(recipe_env, tmp_path):
    """The guest agent ships from setup_level 1; level 0 has nothing to talk to."""
    import hashlib

    env = yaml.safe_load(recipe_env['env_file'].read_text())
    env['recipe']['params']['setup_level'] = 0
    env_file = tmp_path / 'bare.yml'
    env_file.write_text(yaml.dump(env))

    def _must_not_run(**kwargs):  # pragma: no cover
        raise AssertionError('a build started despite an impossible setup level')

    from adare.backend.vm.recipe import build_or_reuse_recipe_vm
    with patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
               side_effect=_must_not_run):
        with pytest.raises(EnvironmentLoadFailed, match='setup_level'):
            build_or_reuse_recipe_vm(
                parse_environment_file(env_file), base_dir=env_file.parent,
                iso_override=recipe_env['iso_dir'],
            )
    assert hashlib  # keep the import meaningful for readers


def test_insufficient_free_disk_is_rejected_before_building(recipe_env, monkeypatch):
    monkeypatch.setattr(recipe_module.shutil, 'disk_usage',
                        lambda p: type('U', (), {'free': 5 * 1024 ** 3})())

    def _must_not_run(**kwargs):  # pragma: no cover
        raise AssertionError('a build started without enough free disk')

    with patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
               side_effect=_must_not_run):
        with pytest.raises(EnvironmentLoadFailed, match='free disk space'):
            _run(recipe_env)


def test_free_disk_requirement_is_lower_when_the_base_is_already_cached(recipe_env, monkeypatch):
    """No OS reinstall means no second full-size write."""
    _write_cached_base(recipe_env)
    # 200 GB: enough for base+overlay+output (1.0x of 160G) but not for a fresh
    # build's 1.5x headroom.
    monkeypatch.setattr(recipe_module.shutil, 'disk_usage',
                        lambda p: type('U', (), {'free': 200 * 1024 ** 3})())
    with (
        patch(f'{_RECIPE_MODULE}._provision_disk',
              return_value=recipe_env['vms'] / 'out.qcow2'),
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'VM1', 'was_existing': False}),
    ):
        _run(recipe_env)


def test_a_bad_provision_block_is_rejected_before_the_iso_is_even_hashed(tmp_path, monkeypatch):
    """A `{{ version }}` typo must cost seconds, not a multi-hour install."""
    env = yaml.safe_load(yaml.dump(_ENV))
    env['recipe']['iso_sha256'] = 'f' * 64
    env['recipe']['provision'] = [{
        'name': 'g', 'for_each': ['1.0'],
        'steps': [{'name': 's-{{ item }}', 'command': 'get {{ version }}'}],
    }]
    env_file = tmp_path / 'bad.yml'
    env_file.write_text(yaml.dump(env))

    from adare.backend.vm.recipe import build_or_reuse_recipe_vm
    with pytest.raises(EnvironmentLoadFailed, match="'version' is undefined"):
        build_or_reuse_recipe_vm(parse_environment_file(env_file), base_dir=tmp_path)


# --- no-provision path stays byte-identical to the old behaviour ---

def test_a_provisionless_recipe_never_enters_stage_two(tmp_path, monkeypatch):
    import hashlib

    iso_dir = tmp_path / 'isos'
    iso_dir.mkdir()
    iso = iso_dir / _ENV['recipe']['iso_name']
    iso.write_bytes(b'iso')

    env = yaml.safe_load(yaml.dump(_ENV))
    env['recipe'].pop('provision')
    env['recipe']['iso_sha256'] = hashlib.sha256(b'iso').hexdigest()
    env_file = tmp_path / 'plain.yml'
    env_file.write_text(yaml.dump(env))

    vms = tmp_path / 'vms'
    vms.mkdir()
    monkeypatch.setattr(recipe_module, 'VMS_DIR', vms)

    def _must_not_run(*args, **kwargs):  # pragma: no cover
        raise AssertionError('Stage 2 ran for a recipe with no provision steps')

    from adare.backend.vm.recipe import build_or_reuse_recipe_vm
    with (
        patch('adare.hypervisor.qemu.vm_creator.windows_creator.create_windows_vm',
              return_value=vms / 'built.qcow2') as creator,
        patch(f'{_RECIPE_MODULE}._provision_disk', side_effect=_must_not_run),
        patch(f'{_RECIPE_MODULE}._build_base_disk', side_effect=_must_not_run),
        patch('adare.backend.vm.commands.load_vm_file_for_environment',
              return_value={'vm_id': 'VM1', 'was_existing': False}),
    ):
        build_or_reuse_recipe_vm(parse_environment_file(env_file), base_dir=tmp_path,
                                 iso_override=iso_dir)

    # Built straight into managed VM storage under the old naming, not the cache.
    assert creator.call_args.kwargs['vm_dir'] is None
    assert 'recipebase' not in creator.call_args.kwargs['vm_name']
