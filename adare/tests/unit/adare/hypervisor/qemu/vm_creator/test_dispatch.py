"""Creator selection must be identical for `vm create` and for recipe builds.

`adare vm create` and `backend/vm/recipe.py::_build_disk` each used to carry their
own if/elif chain, and they drifted: the recipe copy dispatched on ``manual`` and
then fell through to *platform*, so a recipe over a ``gui-auto`` / ``gui-script`` /
``playbook`` profile silently built via the seed-file ``linux_creator`` — which
cannot install those guests at all. Both now call
:func:`vm_creator.dispatch.create_vm_disk`; these tests pin the rule it encodes.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from adare.hypervisor.qemu.vm_creator import dispatch
from adare.hypervisor.qemu.vm_creator.dispatch import (
    GUI_INSTALL_MODES,
    GuiBuildOptions,
    InstallerIsoRequired,
    UnsupportedInstallTarget,
    create_vm_disk,
)
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel

# creator module -> the attribute create_vm_disk imports from it
CREATORS = {
    'manual_creator': 'create_manual_vm',
    'gui_creator': 'create_gui_vm',
    'playbook_creator': 'create_playbook_vm',
    'qmp_script_creator': 'create_qmp_script_vm',
    'linux_creator': 'create_linux_vm',
    'windows_creator': 'create_windows_vm',
}

DISK = Path('/tmp/adare-test-disk.qcow2')


def _os_def(**overrides) -> OsDefinition:
    defaults = dict(
        name='kubuntu2404', display_name='Kubuntu 24.04', platform='linux',
        distribution='ubuntu', version='24.04', iso_url='', iso_sha256='',
        iso_filename='', default_disk_size='60G', default_ram_mb=8192,
        default_cpus=4, architecture='aarch64',
    )
    defaults.update(overrides)
    return OsDefinition(**defaults)


@pytest.fixture
def calls(monkeypatch):
    """Replace every creator with a recorder. Returns the recorded call list."""
    import importlib

    recorded: list[tuple[str, dict]] = []

    def _recorder(module_name):
        def _call(**kwargs):
            recorded.append((module_name, kwargs))
            return DISK
        return _call

    for module_name, function_name in CREATORS.items():
        module = importlib.import_module(
            f'adare.hypervisor.qemu.vm_creator.{module_name}'
        )
        monkeypatch.setattr(module, function_name, _recorder(module_name))
    return recorded


def _build(os_def, **overrides):
    kwargs = dict(
        os_def=os_def,
        iso_path=Path('/tmp/installer.iso'),
        vm_name='vm',
        disk_size='60G',
        ram_mb=4096,
        cpus=2,
        force=False,
        vm_dir=None,
        setup_level=SetupLevel.FULL,
    )
    kwargs.update(overrides)
    return create_vm_disk(**kwargs)


class TestInstallModeBeatsPlatform:
    """The regression: a Linux-platform profile with a GUI install_mode must NOT
    reach linux_creator."""

    @pytest.mark.parametrize('install_mode,expected', [
        ('gui-auto', 'gui_creator'),
        ('gui-script', 'qmp_script_creator'),
        ('playbook', 'playbook_creator'),
        ('manual', 'manual_creator'),
    ])
    def test_linux_platform_with_gui_mode_routes_to_gui_creator(self, calls, install_mode, expected):
        _build(_os_def(platform='linux', install_mode=install_mode))
        assert [module for module, _ in calls] == [expected]

    @pytest.mark.parametrize('install_mode,expected', [
        ('gui-auto', 'gui_creator'),
        ('gui-script', 'qmp_script_creator'),
        ('playbook', 'playbook_creator'),
        ('manual', 'manual_creator'),
    ])
    def test_windows_platform_with_gui_mode_routes_to_gui_creator(self, calls, install_mode, expected):
        _build(_os_def(platform='windows', install_mode=install_mode))
        assert [module for module, _ in calls] == [expected]


class TestPlatformFallback:
    """With the default seed-file mode, the platform decides."""

    def test_linux_auto_routes_to_linux_creator(self, calls):
        _build(_os_def(platform='linux', install_mode='auto'))
        assert [module for module, _ in calls] == ['linux_creator']

    def test_windows_auto_routes_to_windows_creator(self, calls):
        _build(_os_def(platform='windows', install_mode='auto'))
        assert [module for module, _ in calls] == ['windows_creator']

    def test_unknown_platform_raises(self, calls):
        with pytest.raises(UnsupportedInstallTarget, match='Unsupported platform'):
            _build(_os_def(platform='haiku', install_mode='auto'))
        assert calls == []


class TestIsoRequirement:

    @pytest.mark.parametrize('os_def_kwargs', [
        dict(platform='linux', install_mode='manual'),
        dict(platform='linux', install_mode='gui-auto'),
        dict(platform='windows', install_mode='auto'),
    ])
    def test_missing_iso_raises_before_any_creator_runs(self, calls, os_def_kwargs):
        with pytest.raises(InstallerIsoRequired):
            _build(_os_def(**os_def_kwargs), iso_path=None)
        assert calls == []

    @pytest.mark.parametrize('install_mode', ['playbook', 'gui-script'])
    def test_iso_optional_where_the_profile_can_supply_it(self, calls, install_mode):
        """playbook / gui-script may take the ISO from a baked iso_url."""
        _build(_os_def(install_mode=install_mode), iso_path=None)
        assert len(calls) == 1

    def test_linux_auto_tolerates_no_iso(self, calls):
        """linux_creator downloads the catalog ISO itself."""
        _build(_os_def(platform='linux', install_mode='auto'), iso_path=None)
        assert [module for module, _ in calls] == ['linux_creator']

    def test_error_carries_actionable_next_steps(self):
        with pytest.raises(InstallerIsoRequired) as excinfo:
            _build(_os_def(platform='windows', install_mode='auto'), iso_path=None)
        assert 'adare vm create windows11arm64 --iso' not in excinfo.value.next_steps[0]
        assert '--iso' in excinfo.value.next_steps[0]
        assert any('Microsoft' in step for step in excinfo.value.next_steps)


class TestArgumentForwarding:

    def test_gui_options_reach_the_gui_creator(self, calls):
        _build(
            _os_def(install_mode='gui-auto'),
            gui=GuiBuildOptions(record=True, relearn=True, display=True, template='t.yml'),
        )
        _, kwargs = calls[0]
        assert kwargs['record'] is True
        assert kwargs['relearn'] is True
        assert kwargs['display'] is True
        assert kwargs['template'] == 't.yml'

    def test_gui_script_maps_display_to_keep_running(self, calls):
        _build(
            _os_def(install_mode='gui-script'),
            gui=GuiBuildOptions(display=True, template='t.yml'),
        )
        _, kwargs = calls[0]
        assert kwargs['keep_running'] is True
        assert kwargs['template'] == 't.yml'

    def test_playbook_creator_gets_no_host_only_kwargs(self, calls):
        """create_playbook_vm accepts neither compress nor allow_emulation."""
        _build(_os_def(install_mode='playbook'))
        _, kwargs = calls[0]
        assert 'compress' not in kwargs
        assert 'allow_emulation' not in kwargs

    def test_other_creators_get_compress_and_allow_emulation(self, calls):
        _build(_os_def(platform='linux', install_mode='auto'),
               compress=False, allow_emulation=True)
        _, kwargs = calls[0]
        assert kwargs['compress'] is False
        assert kwargs['allow_emulation'] is True

    def test_sizing_and_identity_are_passed_through(self, calls):
        _build(_os_def(platform='linux', install_mode='auto'),
               vm_name='myvm', disk_size='120G', ram_mb=16384, cpus=8, force=True)
        _, kwargs = calls[0]
        assert kwargs['vm_name'] == 'myvm'
        assert kwargs['disk_size'] == '120G'
        assert kwargs['ram_mb'] == 16384
        assert kwargs['cpus'] == 8
        assert kwargs['force'] is True


class TestRecipeUsesTheSameDispatch:
    """The point of extracting it: a recipe over a gui-auto profile must not build
    via linux_creator."""

    def test_recipe_build_routes_gui_auto_to_gui_creator(self, calls, monkeypatch):
        from adare.backend.vm import recipe as recipe_module
        from adare.types.environment import Recipe, RecipeParams

        os_def = _os_def(install_mode='gui-auto', platform='linux')
        recipe = Recipe(
            profile='kubuntu2404',
            iso_sha256='a' * 64,
            params=RecipeParams(setup_level=2, disk_size='60G', ram_mb=4096, cpus=2),
        )
        built = recipe_module._build_disk(
            os_def, recipe, Path('/tmp/installer.iso'), 'vm', force=False,
        )
        assert built == DISK
        assert [module for module, _ in calls] == ['gui_creator']

    def test_recipe_build_translates_dispatch_errors(self, calls):
        from adare.backend.environment.exceptions import EnvironmentLoadFailed
        from adare.backend.vm import recipe as recipe_module
        from adare.types.environment import Recipe

        os_def = _os_def(platform='haiku', install_mode='auto')
        recipe = Recipe(profile='haiku', iso_sha256='a' * 64)
        with pytest.raises(EnvironmentLoadFailed, match='recipe build unsupported'):
            recipe_module._build_disk(
                os_def, recipe, Path('/tmp/installer.iso'), 'vm', force=False,
            )


def test_gui_install_modes_constant_matches_the_dispatch_branches():
    """`GUI_INSTALL_MODES` drives CLI behaviour (setup-level warning, skipping the
    post-install session); it must stay in step with the modes handled above."""
    assert GUI_INSTALL_MODES == frozenset({'manual', 'gui-auto', 'gui-script'})
    assert dispatch.GUI_INSTALL_MODES is GUI_INSTALL_MODES
