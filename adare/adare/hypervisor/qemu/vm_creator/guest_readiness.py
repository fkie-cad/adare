"""Prove — and where needed finish — that a freshly built disk is ADARE-ready.

An unattended install (autoinstall, preseed, kickstart, AutoYaST, autounattend)
reports success when its installer powers off. Nothing used to boot the result,
so an image whose guest agent never starts, whose autologin is broken, or whose
desktop locks after five idle minutes passed ``vm create`` and only failed later,
in ``vm test`` or an experiment — or, for the lock, produced black screenshots.

:func:`make_guest_ready` closes that gap for every creator that does not do it
itself. It reuses the recipe build's provisioning machinery
(:func:`provision_creator.run_provision`): boot the disk on a throwaway overlay
with a guest-agent channel, run :func:`readiness_commands` one ``guest-exec`` at a
time, reboot, and require the agent and an automatic-login session to come back,
then shut down cleanly and flatten. The installed disk is only replaced on full
success; on failure it stays where it is and the error says so.

The commands only fill what the answer files leave out, and leave alone what
they set on purpose (some force an X11 session, so autologin is checked, not
rewritten). Windows answer files already disable the lock screen, OOBE and
updates, so Windows gets the checks only.

The desktop steps are shared with the playbook path (see playbook_provision),
which applies them inside its own install session.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.vm_creator.base_creator import VMCreationError
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
from adare.types.environment import ProvisionCommand

log = logging.getLogger(__name__)

# The account every ADARE answer file and playbook profile creates.
GUEST_USER = 'adare'
GUEST_PASSWORD = 'adare'


class GuestNotReadyError(VMCreationError):
    """The OS installed, but the disk failed the ADARE readiness pass."""


# An idle desktop otherwise locks and blanks after a few minutes, and the host
# screendump then captures a black frame. GNOME reads the system dconf db,
# Plasma the /etc/xdg defaults (5: powermanagementprofilesrc, 6: powerdevilrc).
# Xfce keeps its settings per user in xfconf, so a login hook sets them.
NO_LOCK = ProvisionCommand(
    name='no screen lock or blanking',
    shell='bash',
    timeout_minutes=5,
    command=f"""set -e
if command -v gnome-shell >/dev/null; then
  mkdir -p /etc/dconf/profile /etc/dconf/db/local.d
  [ -f /etc/dconf/profile/user ] || printf 'user-db:user\\n' > /etc/dconf/profile/user
  grep -qx 'system-db:local' /etc/dconf/profile/user || echo 'system-db:local' >> /etc/dconf/profile/user
  cat > /etc/dconf/db/local.d/00-adare <<'EOF'
[org/gnome/desktop/session]
idle-delay=uint32 0

[org/gnome/desktop/screensaver]
lock-enabled=false

[org/gnome/settings-daemon/plugins/power]
sleep-inactive-ac-type='nothing'
EOF
  dconf update
fi
if command -v plasmashell >/dev/null; then
  mkdir -p /etc/xdg
  printf '[Daemon]\\nAutolock=false\\nLockOnResume=false\\nTimeout=0\\n' > /etc/xdg/kscreenlockerrc
  printf '[AC][DPMSControl]\\nidleTime=0\\n\\n[AC][DimDisplay]\\nidleTime=0\\n\\n[AC][SuspendSession]\\nidleTime=0\\nsuspendType=0\\n' \\
    > /etc/xdg/powermanagementprofilesrc
  printf '[AC][Display]\\nDimDisplayWhenIdle=false\\nTurnOffDisplayWhenIdle=false\\n\\n[AC][SuspendAndShutdown]\\nAutoSuspendAction=0\\n' \\
    > /etc/xdg/powerdevilrc
fi
if command -v xfce4-session >/dev/null; then
  home=$(getent passwd {GUEST_USER} | cut -d: -f6)
  install -d -o {GUEST_USER} -g {GUEST_USER} "$home/.config" "$home/.config/autostart"
  cat > "$home/.config/autostart/adare-no-blank.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=ADARE: no screen blanking
Exec=sh -c 'xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled -n -t bool -s false; xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/blank-on-ac -n -t int -s 0; xfconf-query -c xfce4-screensaver -p /saver/enabled -n -t bool -s false; xfconf-query -c xfce4-screensaver -p /lock/enabled -n -t bool -s false; xset s off; xset s noblank; xset -dpms'
EOF
  for entry in /etc/xdg/autostart/light-locker.desktop /etc/xdg/autostart/xfce4-screensaver.desktop; do
    if [ -e "$entry" ]; then
      printf '[Desktop Entry]\\nHidden=true\\n' > "$home/.config/autostart/$(basename "$entry")"
    fi
  done
  chown -R {GUEST_USER}:{GUEST_USER} "$home/.config/autostart"
fi""",
)

# gnome-initial-setup ("Welcome to Ubuntu"), GNOME Tour and Plasma Welcome open
# over the desktop on every login until finished, so every experiment would start
# behind them. The done marker plus a hiding user autostart override covers them.
# Ubuntu 26.04 adds a per-release "welcome / what's new" mode
# (gnome-initial-setup-upgrade-login.service, a systemd user unit, not autostart):
# it runs once the done marker exists and until
# ~/.config/gnome-initial-setup/upgrade-<VERSION_ID>-done does, so the done marker
# alone would arm it. Stamp the guest's own release too.
NO_WELCOME = ProvisionCommand(
    name='no first-login welcome wizard',
    shell='bash',
    timeout_minutes=5,
    command=f"""set -e
home=$(getent passwd {GUEST_USER} | cut -d: -f6)
install -d -o {GUEST_USER} -g {GUEST_USER} "$home/.config" "$home/.config/autostart" \\
    "$home/.config/gnome-initial-setup"
printf 'yes' > "$home/.config/gnome-initial-setup-done"
chown {GUEST_USER}:{GUEST_USER} "$home/.config/gnome-initial-setup-done"
release=$(. /etc/os-release && printf '%s' "${{VERSION_ID:-}}")
if [ -n "$release" ]; then
  : > "$home/.config/gnome-initial-setup/upgrade-$release-done"
  chown {GUEST_USER}:{GUEST_USER} "$home/.config/gnome-initial-setup/upgrade-$release-done"
fi
for entry in /etc/xdg/autostart/*initial-setup*.desktop /etc/xdg/autostart/*welcome*.desktop \\
             /etc/xdg/autostart/*gnome-tour*.desktop; do
  [ -e "$entry" ] || continue
  override="$home/.config/autostart/$(basename "$entry")"
  printf '[Desktop Entry]\\nHidden=true\\n' > "$override"
  chown {GUEST_USER}:{GUEST_USER} "$override"
done""",
)

# Lets the guest finish its boot and log the user in again before the check.
REBOOT = ProvisionCommand(name='reboot', shell='bash', command='true', reboot=True, timeout_minutes=2)
REBOOT_WINDOWS = ProvisionCommand(name='reboot', shell='powershell', command='exit 0', reboot=True, timeout_minutes=2)

# An automatic-login session for the guest user proves the greeter is gone
# without reading the screen. Polled in the guest: the desktop session starts a
# little after the agent does.
AUTOLOGIN_CHECK_LINUX = f"loginctl list-sessions --no-legend | awk '{{print $3}}' | grep -qx {GUEST_USER}"
AUTOLOGIN_LINUX = ProvisionCommand(
    name='automatic login works',
    shell='bash',
    timeout_minutes=5,
    command=(
        f'for i in $(seq 36); do {AUTOLOGIN_CHECK_LINUX} && exit 0; sleep 5; done; '
        f"echo 'no login session for {GUEST_USER} 3 minutes after boot: automatic login is not working' >&2; "
        'loginctl list-sessions >&2; exit 1'
    ),
)
AUTOLOGIN_WINDOWS = ProvisionCommand(
    name='automatic login works',
    shell='powershell',
    timeout_minutes=5,
    command=(
        'for ($i = 0; $i -lt 36; $i++) { '
        '$user = (Get-CimInstance Win32_ComputerSystem).UserName; '
        f"if ($user -like '*\\{GUEST_USER}') {{ exit 0 }}; Start-Sleep -Seconds 5 }}; "
        f"[Console]::Error.WriteLine(\"no console session for {GUEST_USER} 3 minutes after boot "
        '(logged on: $user): AutoLogon is not working"); exit 1'
    ),
)


# virtiofs.exe mounts the ADARE shares through WinFsp; without it every share is empty.
WINFSP_WINDOWS = ProvisionCommand(
    name='WinFsp installed (virtio-fs shares)',
    shell='powershell',
    timeout_minutes=1,
    command=(
        "if (Test-Path 'C:\\Program Files (x86)\\WinFsp\\bin\\winfsp-x64.dll') { exit 0 }; "
        "[Console]::Error.WriteLine('WinFsp is not installed: virtiofs.exe cannot mount the ADARE shares'); exit 1"
    ),
)
# The agent runs in this env; first logon creates it, and a failed `conda create`
# there leaves an empty folder that ADARE would otherwise only notice at run time.
PYTHON_ENV_WINDOWS = ProvisionCommand(
    name='pyadare Python environment works',
    shell='powershell',
    timeout_minutes=2,
    command=(
        f"$py = 'C:\\Users\\{GUEST_USER}\\.miniforge3\\envs\\pyadare\\python.exe'; "
        "if (-not (Test-Path $py)) { "
        "[Console]::Error.WriteLine(\"no ${py}: creating the pyadare conda env at first logon failed\"); exit 1 }; "
        "& $py -c 'import sys; print(sys.version)'; exit $LASTEXITCODE"
    ),
)


def readiness_commands(os_def: OsDefinition, setup_level: SetupLevel) -> list[ProvisionCommand]:
    """The readiness pass for an unattended install; empty for ``bare``."""
    if setup_level < SetupLevel.BASE:
        return []
    if os_def.platform == 'windows':
        commands = [REBOOT_WINDOWS, AUTOLOGIN_WINDOWS]
        # The x86_64 answer files install WinFsp and a conda env; aarch64 uses SMB
        # shares and a system Python, so these checks do not apply there.
        if os_def.architecture == 'x86_64':
            commands.append(WINFSP_WINDOWS)
            if setup_level >= SetupLevel.FULL:
                commands.append(PYTHON_ENV_WINDOWS)
        return commands
    return [NO_LOCK, NO_WELCOME, REBOOT, AUTOLOGIN_LINUX]


def _package_list_collector(disk_path: Path):
    """A run_provision hook that stores the guest's package list next to *disk_path*."""

    def collect(qga_sock: Path) -> None:
        from adare.backend.vm.image_record import PACKAGE_LIST_COMMAND, write_packages
        from adare.hypervisor.qemu.vm_creator.qga_utils import QgaError, qga_exec

        try:
            returncode, stdout, _ = qga_exec(qga_sock, PACKAGE_LIST_COMMAND, shell='bash', timeout=120)
        except QgaError as e:
            log.warning(f'Could not read the guest package list: {e}')
            return
        if returncode == 0:
            write_packages(disk_path, stdout)

    return collect


def make_guest_ready(
    disk_path: Path,
    os_def: OsDefinition,
    setup_level: SetupLevel,
    ram_mb: int,
    cpus: int,
    allow_emulation: bool = False,
    compress: bool = True,
) -> Path:
    """Run the readiness pass on *disk_path* and replace it with the result.

    Raises:
        GuestNotReadyError: The pass failed. *disk_path* is left untouched.
    """
    from adare.hypervisor.qemu.vm_creator.provision_creator import run_provision

    commands = readiness_commands(os_def, setup_level)
    if not commands:
        return disk_path
    ready = disk_path.with_name(f'{disk_path.stem}.ready.qcow2')
    build_log = disk_path.with_name(f'{disk_path.stem}_readiness.log')
    try:
        run_provision(
            base_disk=disk_path,
            dest_disk=ready,
            commands=commands,
            os_def=os_def,
            ram_mb=ram_mb,
            cpus=cpus,
            build_log_path=build_log,
            allow_emulation=allow_emulation,
            compress=compress,
            title='ADARE readiness check',
            after_commands=_package_list_collector(disk_path) if os_def.platform == 'linux' else None,
        )
    except HypervisorException as e:
        # RecipeProvisionError for a failed step; overlay/boot errors are plain ones.
        if ready.exists():
            ready.unlink()
        raise GuestNotReadyError(
            f'the OS installed, but the disk is not ADARE-ready: {e}\n'
            f'  The installed disk is kept at {disk_path} for inspection; do not register it. '
            f'Log: {build_log}'
        ) from e
    os.replace(ready, disk_path)
    log.info('Readiness pass passed; %s replaced with the checked disk', disk_path)
    return disk_path
