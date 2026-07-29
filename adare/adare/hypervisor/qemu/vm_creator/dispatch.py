"""Single place that decides *which creator* builds a disk for an OS profile.

Two callers need this decision: `adare vm create` (:mod:`adare.cli.vm_create`)
and recipe builds (:mod:`adare.backend.vm.recipe`). They used to each carry their
own if/elif chain, and they drifted: the recipe copy dispatched on ``manual`` and
then fell through to *platform*, so a recipe over a ``gui-auto`` /
``playbook`` profile silently built via the seed-file
``linux_creator`` — which cannot install those guests at all.

The rule the chain encodes, in order:

1. ``install_mode`` first. It names a *mechanism* (drive the installer's GUI,
   replay a playbook, wait for a human), and that always wins over the platform.
2. ``platform`` second, for the seed-file modes where the mechanism is implied
   (Linux autoinstall/kickstart, Windows unattend.xml).

Presentation stays with the callers: this module raises
:class:`InstallerIsoRequired` / :class:`UnsupportedInstallTarget` and each caller
renders them its own way (console message vs ``EnvironmentLoadFailed``).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition

log = logging.getLogger(__name__)

# Install modes that drive the OS installer's own GUI (or a human) instead of
# handing it a seed file. They bake no Python environment, and they need no
# post-install interactive session because the install already ran in a driven
# window.
GUI_INSTALL_MODES = frozenset({'manual', 'gui-auto'})


class DispatchError(Exception):
    """Base for 'no creator could be run' — carries ready-made display text."""

    def __init__(self, title: str, next_steps: list[str]):
        super().__init__(title)
        self.title = title
        self.next_steps = next_steps


class InstallerIsoRequired(DispatchError):
    """The creator selected for this profile cannot build without an ISO."""


class UnsupportedInstallTarget(DispatchError):
    """No creator exists for this profile's install_mode/platform combination."""


@dataclass(frozen=True)
class GuiBuildOptions:
    """Options only the GUI-driven creators (`gui-auto`) accept."""

    record: bool = False
    relearn: bool = False
    display: bool = False
    template: str | None = None


def create_vm_disk(
    *,
    os_def: OsDefinition,
    iso_path: Path | None,
    vm_name: str | None,
    disk_size: str | None,
    ram_mb: int | None,
    cpus: int | None,
    force: bool,
    vm_dir: Path | None,
    setup_level,
    compress: bool = True,
    allow_emulation: bool = False,
    gui: GuiBuildOptions | None = None,
) -> Path:
    """Build a disk for *os_def* with the creator its profile calls for.

    Raises :class:`InstallerIsoRequired` when the chosen creator needs an ISO and
    ``iso_path`` is ``None``, and :class:`UnsupportedInstallTarget` when nothing
    can build the profile at all. Creator-internal failures propagate unchanged.
    """
    gui = gui or GuiBuildOptions()
    common = {
        'os_def': os_def,
        'vm_name': vm_name,
        'disk_size': disk_size,
        'ram_mb': ram_mb,
        'cpus': cpus,
        'force': force,
        'vm_dir': vm_dir,
        'setup_level': setup_level,
    }
    # playbook_creator takes neither compress nor allow_emulation; every other
    # creator takes both.
    hostable = {**common, 'compress': compress, 'allow_emulation': allow_emulation}

    # 1. install_mode wins over platform.
    if os_def.install_mode == 'manual':
        _require_iso(
            iso_path, os_def,
            title=f'ISO required for manual install of {os_def.display_name}',
        )
        from adare.hypervisor.qemu.vm_creator.manual_creator import create_manual_vm

        return create_manual_vm(iso_path=iso_path, **hostable)

    if os_def.install_mode == 'gui-auto':
        _require_iso(
            iso_path, os_def,
            title=f'ISO required for GUI-automated install of {os_def.display_name}',
        )
        from adare.hypervisor.qemu.vm_creator.gui_creator import create_gui_vm

        return create_gui_vm(
            iso_path=iso_path,
            record=gui.record,
            relearn=gui.relearn,
            display=gui.display,
            template=gui.template,
            **hostable,
        )

    if os_def.install_mode == 'playbook':
        from adare.hypervisor.qemu.vm_creator.playbook_creator import create_playbook_vm

        return create_playbook_vm(iso_path=iso_path, **common)

    # 2. Seed-file modes, keyed on platform.
    if os_def.platform == 'linux':
        from adare.hypervisor.qemu.vm_creator.linux_creator import create_linux_vm

        return create_linux_vm(iso_path=iso_path, **hostable)

    if os_def.platform == 'windows':
        _require_iso(
            iso_path, os_def,
            title=f'Windows ISO required for {os_def.display_name}',
            extra_steps=['Download from Microsoft (requires a valid license)'],
        )
        from adare.hypervisor.qemu.vm_creator.windows_creator import create_windows_vm

        return create_windows_vm(iso_path=iso_path, **hostable)

    raise UnsupportedInstallTarget(
        title=f'Unsupported platform: {os_def.platform}',
        next_steps=['Pick a profile with platform linux or windows: adare vm profiles'],
    )


def _require_iso(iso_path: Path | None, os_def: OsDefinition, *, title: str,
                 extra_steps: list[str] | None = None) -> None:
    if iso_path is not None:
        return
    raise InstallerIsoRequired(
        title=title,
        next_steps=[
            f'Provide the ISO: adare vm create {os_def.name} --iso /path/to/installer.iso',
            *(extra_steps or []),
        ],
    )
